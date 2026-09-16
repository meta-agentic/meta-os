#!/usr/bin/env python3
"""meta-os autonomous pipeline — one tick.

    tick.py --config CFG --state DIR plan   [--out plan.json]
    tick.py --config CFG --state DIR record --results results.json
    tick.py --config CFG --state DIR report [--out report.md]

`plan` reads the vault and the ledger, runs the regulator and the reflection, and emits what
the harness must do: which lanes to start (with their prompts), which sessions to check, which
to interrupt. It marks chosen lanes `spawning` so a second `plan` before `record` cannot
double-assign. `record` takes the harness's results (session ids, statuses, usage, PRs),
updates the ledger, transitions items through the backlog CLI (the pipeline is the single
writer of item status), and commits the vault. `report` renders the window for the human.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml  # type: ignore

from metaos_pipeline import controller, readyset, reflect, speculate
from metaos_pipeline.ledger import Ledger, usage_delta

ACTIVE = ("running", "spawning")


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    base = os.path.dirname(os.path.abspath(path))
    for key in ("vault", "backlog_cli", "model_path"):
        if cfg.get(key) and not os.path.isabs(cfg[key]):
            cfg[key] = os.path.normpath(os.path.join(base, cfg[key]))
    return cfg


def item_body(path: str, limit: int) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return ""
    return text[:limit] + ("\n…[truncated]" if len(text) > limit else "")


def render(template: str, **fields: str) -> str:
    out = template
    for k, v in fields.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def severity(statuses: list[str]) -> str:
    order = ["allowed", "allowed_warning", "warning", "rejected", "exceeded"]
    worst = "allowed"
    for s in statuses:
        s = (s or "allowed").lower()
        if s in order and order.index(s) > order.index(worst):
            worst = s
    return worst


# ---------------------------------------------------------------- plan
def cmd_plan(cfg: dict, led: Ledger, out_path: str | None) -> int:
    reg = cfg.get("regulator") or {}
    defaults = {"N": int(reg.get("N0", 3)), "tick": 0, "paused": [], "spent": 0.0,
                "calibration": dict(cfg.get("calibration") or {}),
                "window_start": time.time(), "last_tick_ts": None}
    with led.locked():
        state = led.state(defaults)
        lanes = led.lanes()
        now = time.time()
        tick = int(state["tick"]) + 1
        hours = ((now - state["last_tick_ts"]) / 3600.0) if state.get("last_tick_ts") else float(cfg.get("tick_hours", 1.0))
        hours = max(hours, 1e-3)

        # ---- sensor
        d_cost = sum(usage_delta(l)[0] for l in lanes)
        spent = sum(float((l.get("usage") or [{}])[-1].get("cost_usd", 0.0)) for l in lanes)
        burn = d_cost / hours
        rate_status = severity([(l.get("usage") or [{}])[-1].get("rate_status", "allowed") for l in lanes])

        # ---- ready set and saturation
        ready = readyset.ready_items(cfg["vault"], cfg)
        active = [l for l in lanes if l.get("status") in ACTIVE]
        lanes_saturated = len(active) >= int(state["N"]) and bool(ready)

        # ---- regulator
        target = controller.setpoint(float(reg.get("budget", 0.0)), float(reg.get("window_hours", 8.0)),
                                     float(reg.get("reserve_fraction", 0.15)), float(reg.get("shape", 1.0)))
        decision = controller.regulate(int(state["N"]), burn, target, rate_status, lanes_saturated,
                                       int(reg.get("N_min", 1)), int(reg.get("N_max", 4)), float(reg.get("eps", 0.15)),
                                       reg.get("warn_cap"), len(active))
        freeze = decision.freeze
        if controller.budget_exhausted(spent, float(reg.get("budget", 0.0))):
            freeze = True
            decision.reason += f"; window budget {reg.get('budget')} exhausted (spent {spent:.2f}): freeze"
        N = decision.N_new

        # ---- reap / interrupt lists
        check = [{"lane_id": l["lane_id"], "session_id": l.get("session_id"), "branch": l.get("branch"),
                  "repo": l.get("repo"), "kind": l.get("kind")} for l in active if l.get("session_id")]
        cap = float(reg.get("lane_cap", 0.0))
        interrupt = [l["lane_id"] for l in active
                     if controller.over_cap(float((l.get("usage") or [{}])[-1].get("cost_usd", 0.0)), cap)]

        # ---- review-queue guard (reflection level 1): pause spaces whose pipeline output waits
        review_cap = int(cfg.get("review_cap_per_space", 4))
        paused: list[str] = []
        for space in (cfg.get("spaces") or {}):
            n_review = len([l for l in lanes if l.get("space") == space and l.get("status") == "in_review"])
            if n_review >= review_cap:
                paused.append(space)

        # ---- speculation first (it reserves its tokens), then work assignment
        spawn: list[dict] = []
        spec_spawn: list[dict] = []
        free = max(0, N - len([l for l in lanes if l.get("status") in ACTIVE]))
        if not freeze and free > 0:
            spec_cfg = cfg.get("speculation") or {}
            cfg_dir = os.path.dirname(os.path.abspath(cfg.get("_config_path", ".")))
            for plan in speculate.plan_speculation(spec_cfg.get("decisions") or [], lanes, N, free,
                                                   float(spec_cfg.get("share", 0.34)), float(spec_cfg.get("latency_days", 0.5))):
                led.event("speculation_considered", decision=plan.decision_id, go=plan.go, reason=plan.reason, tick=tick)
                if not plan.go:
                    continue
                for br in plan.branches:
                    prompt = br.get("prompt") or ""
                    if br.get("prompt_file"):
                        with open(os.path.join(cfg_dir, br["prompt_file"]), encoding="utf-8") as fh:
                            prompt = fh.read()
                    lane_id = f"S{tick}-{uuid.uuid4().hex[:6]}"
                    lane = {"lane_id": lane_id, "kind": "spec", "decision": plan.decision_id, "branch_key": br["key"],
                            "space": br.get("space", ""), "repo": br["repo"], "branch": br["outcome_branch"],
                            "primary_tag": f"spec:{plan.decision_id}", "status": "spawning", "planned_tick": tick,
                            "planned_ts": now, "usage": []}
                    lanes.append(lane)
                    spec_spawn.append({**{k: lane[k] for k in ("lane_id", "kind", "decision", "branch_key", "repo", "branch")},
                                       "prompt": prompt})
                free -= len(plan.branches)
            cfg_for_assign = dict(cfg); cfg_for_assign["regulator"] = dict(reg, N=N)
            chosen = readyset.assign(ready, lanes, free, cfg_for_assign, paused) if free > 0 else []
            for it in chosen:
                lane_id = f"L{tick}-{uuid.uuid4().hex[:6]}"
                public = bool((cfg.get("spaces") or {}).get(it.space, {}).get("public"))
                prompt = render(cfg.get("lane_prompt", ""), id=it.id, title=it.title, repo=it.repo, branch=it.branch,
                                space=it.space, item_body=item_body(it.path, int(cfg.get("item_body_limit", 12000))),
                                public_note=(cfg.get("public_repo_note", "") if public else ""))
                lane = {"lane_id": lane_id, "kind": "work", "item": it.id, "space": it.space, "repo": it.repo,
                        "branch": it.branch, "primary_tag": it.primary_tag, "status": "spawning",
                        "planned_tick": tick, "planned_ts": now, "usage": [], "points": it.points}
                lanes.append(lane)
                spawn.append({**{k: lane[k] for k in ("lane_id", "kind", "item", "space", "repo", "branch")},
                              "title": it.title, "prompt": prompt})

        # ---- reflection
        model = reflect.load_model(cfg["model_path"])
        m_cfg = int(reg.get("N_max", 4))
        predicted = reflect.predict(model, m_cfg, N, state["calibration"])
        measured = reflect.measure(cfg["vault"], lanes, led.runs(), burn, spent)
        attribution, esc = reflect.attribute(predicted, measured, decision.reason, N, m_cfg)
        if freeze and rate_status != "allowed":
            esc.append(f"rate-limit status '{rate_status}' froze spawning; nothing starts until it clears")
        window = f"{time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime(state['window_start']))}+{reg.get('window_hours', 8)}h"
        refl = reflect.record(tick, window, predicted, measured, decision, state["calibration"], paused, esc, attribution)
        led.reflection(refl)

        # ---- persist
        state.update({"N": N, "tick": tick, "paused": paused, "spent": spent, "last_plan_ts": now})
        led.save_state(state)
        led.save_lanes(lanes)
        plan = {"tick": tick, "ts": now, "N": N, "N_old": decision.N_old, "freeze": freeze, "burn_per_hour": round(burn, 3),
                "setpoint_per_hour": round(target, 3), "rate_status": rate_status, "spent": round(spent, 3),
                "ready_set": [i.id for i in ready], "paused_spaces": paused, "spawn": spawn, "spec_spawn": spec_spawn,
                "check": check, "interrupt": interrupt, "reflection": refl}
        led.run({"phase": "plan", **{k: v for k, v in plan.items() if k not in ("spawn", "spec_spawn", "reflection")},
                 "spawn_ids": [s["lane_id"] for s in spawn], "spec_ids": [s["lane_id"] for s in spec_spawn]})
    text = json.dumps(plan, indent=1)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        print(text)
    return 0


# ---------------------------------------------------------------- record
def backlog(cfg: dict, *args: str) -> tuple[int, str]:
    cli = cfg.get("backlog_cli")
    if not cli:
        return 0, "no backlog_cli configured (dry run)"
    env = dict(os.environ, MOVA_VAULT=cfg["vault"])
    r = subprocess.run([sys.executable, cli, *args], cwd=cfg["vault"], env=env, capture_output=True, text=True, timeout=120)
    return r.returncode, (r.stdout + r.stderr).strip()


def vault_commit(cfg: dict, message: str) -> str:
    if not cfg.get("vault_autocommit"):
        return "autocommit off"
    v = cfg["vault"]
    def g(*a: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", v, *a], capture_output=True, text=True, timeout=180)
    g("fetch", "-q", "origin", "main")
    g("pull", "-q", "--ff-only", "origin", "main")
    status = g("status", "--porcelain").stdout
    if not status.strip():
        return "nothing to commit"
    gate = subprocess.run([sys.executable, os.path.join(v, "scripts", "validate_items.py")], cwd=v, capture_output=True, text=True)
    if gate.returncode != 0:
        return "gate failed: " + gate.stdout[-400:] + gate.stderr[-400:]
    g("add", "-A", "--", "*/raw", "*/wiki", "*/output", "*/_index.md", "*/_backlog-meta.yaml")
    c = g("commit", "-q", "-m", message)
    if c.returncode != 0:
        return "commit failed: " + c.stderr[-300:]
    p = g("push", "-q", "origin", "main")
    return "pushed" if p.returncode == 0 else "push failed: " + p.stderr[-300:]


def cmd_record(cfg: dict, led: Ledger, results_path: str) -> int:
    with open(results_path, encoding="utf-8") as fh:
        res = json.load(fh)
    now = time.time()
    transitions: list[str] = []
    with led.locked():
        state = led.state({"N": 1, "tick": 0, "spent": 0.0})
        lanes = led.lanes()
        by_id = {l["lane_id"]: l for l in lanes}
        for s in res.get("spawned") or []:
            lane = by_id.get(s["lane_id"])
            if not lane:
                continue
            if s.get("ok"):
                lane.update({"status": "running", "session_id": s.get("session_id"), "started": now})
                led.event("lane_started", lane_id=lane["lane_id"], session_id=s.get("session_id"), item=lane.get("item"))
                if lane["kind"] == "work":
                    rc, msg = backlog(cfg, "transition", lane["item"], "IN PROGRESS")
                    led.event("transition", item=lane["item"], to="IN PROGRESS", rc=rc, msg=msg[-200:])
                    if rc == 0:
                        transitions.append(f"{lane['item']} → IN PROGRESS (lane {lane['lane_id']}, session {s.get('session_id')}, branch {lane['branch']})")
            else:
                lane.update({"status": "failed_spawn", "ended": now, "error": s.get("error")})
                led.event("lane_failed_spawn", lane_id=lane["lane_id"], error=s.get("error"))
        for c in res.get("checks") or []:
            lane = by_id.get(c["lane_id"])
            if not lane:
                continue
            u = c.get("usage") or {}
            lane.setdefault("usage", []).append({"ts": now, "cost_usd": float(u.get("cost_usd", 0.0)),
                                                 "tokens": float(u.get("tokens", 0.0)),
                                                 "rate_status": c.get("rate_status", "allowed")})
            st = (c.get("status") or "").lower()
            pr = c.get("pr")
            if pr:
                lane["pr"] = pr
            if st in ("idle", "failed", "archived", "completed", "review_ready", "blocked") or c.get("ended"):
                lane["ended"] = now
                if lane["kind"] == "spec":
                    lane["status"] = "done" if c.get("branch_pushed") else "failed"
                elif pr:
                    lane["status"] = "in_review"
                    rc, msg = backlog(cfg, "transition", lane["item"], "IN REVIEW")
                    led.event("transition", item=lane["item"], to="IN REVIEW", rc=rc, msg=msg[-200:])
                    if rc == 0:
                        transitions.append(f"{lane['item']} → IN REVIEW (PR {pr.get('url', pr)})")
                elif c.get("branch_pushed"):
                    lane["status"] = "ended_no_pr"
                else:
                    lane["status"] = "failed" if st == "failed" else "ended_empty"
                led.event("lane_ended", lane_id=lane["lane_id"], status=lane["status"], item=lane.get("item"))
        for lid in res.get("interrupted") or []:
            lane = by_id.get(lid)
            if lane:
                lane.update({"status": "interrupted", "ended": now})
                led.event("lane_interrupted", lane_id=lid)
        spent = sum(float((l.get("usage") or [{}])[-1].get("cost_usd", 0.0)) for l in lanes)
        state.update({"last_tick_ts": now, "spent": spent})
        led.save_lanes(lanes)
        led.save_state(state)
        led.run({"phase": "record", "tick": state.get("tick"), "spent": round(spent, 3),
                 "transitions": transitions, "n_checks": len(res.get("checks") or []),
                 "n_spawned_ok": len([s for s in (res.get("spawned") or []) if s.get("ok")])})
    msg = "pipeline tick %s: %s" % (state.get("tick"), "; ".join(transitions) if transitions else "no transitions")
    out = vault_commit(cfg, msg + "\n\nWritten by the autonomous pipeline's record step; lanes and usage in the instance ledger.") if transitions else "no transitions"
    print(json.dumps({"tick": state.get("tick"), "spent": round(spent, 3), "transitions": transitions, "vault": out}, indent=1))
    return 0


# ---------------------------------------------------------------- report
def cmd_report(cfg: dict, led: Ledger, out_path: str | None) -> int:
    state = led.state({"N": 0, "tick": 0, "spent": 0.0})
    lanes = led.lanes()
    runs = led.runs()
    refl = led.reflections()
    reg = cfg.get("regulator") or {}
    L = ["# Pipeline window report", "",
         f"Ticks: {state.get('tick')} · N now {state.get('N')} (bounds {reg.get('N_min')}–{reg.get('N_max')}) · "
         f"spent {state.get('spent', 0):.2f} of budget {reg.get('budget')} · window {reg.get('window_hours')} h", ""]
    L += ["## Lanes", "", "| lane | kind | item / decision | status | branch | PR | cost |", "|---|---|---|---|---|---|---|"]
    for l in lanes:
        cost = float((l.get("usage") or [{}])[-1].get("cost_usd", 0.0))
        pr = l.get("pr") or {}
        L.append(f"| {l['lane_id']} | {l['kind']} | {l.get('item') or l.get('decision')} | {l['status']} | `{l.get('branch','')}` | {pr.get('url','') } | {cost:.2f} |")
    L += ["", "## Regulator trace", "", "| tick | N | burn/h | setpoint/h | rate | freeze | reason |", "|---|---|---|---|---|---|---|"]
    for r in runs:
        if r.get("phase") == "plan":
            L.append(f"| {r['tick']} | {r['N_old']}→{r['N']} | {r['burn_per_hour']} | {r['setpoint_per_hour']} | {r['rate_status']} | {r['freeze']} | {r['reflection_reason'] if 'reflection_reason' in r else ''} |")
    L += ["", "## Reflections and escalations", ""]
    for rr in refl:
        L.append(f"**Tick {rr['tick']}** — predicted X {rr['predicted']['X']}/day, W {rr['predicted']['W']} d; "
                 f"measured lanes {rr['measured']['lanes_active']}, in review {rr['measured']['in_review_by_pipeline']}, "
                 f"burn {rr['measured']['burn_per_hour']}/h, spent {rr['measured']['spent']}.")
        L.append("")
        L.append(rr["attribution"])
        for e in rr.get("escalations") or []:
            L.append(f"- ⚠ {e}")
        L.append("")
    spec = [l for l in lanes if l["kind"] == "spec"]
    if spec:
        L += ["## Speculative branches (read first, pick one)", ""]
        for l in spec:
            L.append(f"- {l['decision']} / **{l['branch_key']}** → `{l['branch']}` on {l['repo']} — {l['status']}")
        L.append("")
    L += ["## For the human round", ""]
    seen = set()
    for rr in refl:
        for e in rr.get("escalations") or []:
            if e not in seen:
                seen.add(e); L.append(f"- [ ] {e}")
    for l in lanes:
        if l["status"] == "in_review":
            L.append(f"- [ ] Review {l.get('item')}: {((l.get('pr') or {}).get('url')) or l.get('branch')}")
        if l["status"] in ("ended_no_pr", "ended_empty", "failed", "failed_spawn", "interrupted"):
            L.append(f"- [ ] Lane {l['lane_id']} for {l.get('item') or l.get('decision')} ended `{l['status']}` — decide: retry, re-refine, or drop")
    text = "\n".join(L) + "\n"
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--state", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("--out")
    r = sub.add_parser("record"); r.add_argument("--results", required=True)
    q = sub.add_parser("report"); q.add_argument("--out")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    cfg["_config_path"] = os.path.abspath(a.config)
    led = Ledger(a.state)
    if a.cmd == "plan":
        return cmd_plan(cfg, led, a.out)
    if a.cmd == "record":
        return cmd_record(cfg, led, a.results)
    return cmd_report(cfg, led, a.out)


if __name__ == "__main__":
    sys.exit(main())
