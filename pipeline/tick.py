#!/usr/bin/env python3
"""meta-os autonomous pipeline — one tick.

    tick.py --config CFG [--state DIR] [--metaos-config FILE] plan   [--out plan.json]
    tick.py --config CFG [--state DIR] [--metaos-config FILE] record --results results.json
    tick.py --config CFG [--state DIR] [--metaos-config FILE] report [--out report.md]
    tick.py --config CFG [--state DIR] [--metaos-config FILE] run    --inbox DIR [--work DIR]
    tick.py --config CFG [--state DIR] [--metaos-config FILE] control lease take --reason R

The record goes to the clone of `swarm.record_repository` when the estate config
(`meta-os.config.json`, found above CFG or named by --metaos-config) sets it, and to the plain
directory --state otherwise; the run line on stderr says which (`pipeline/record.md`).

`plan` reads the vault and the ledger, runs the regulator and the reflection, and emits what
the harness must do: which lane slots start a run (with their prompts), which sessions to check,
which to interrupt. The slots (`swarm.lanes` of them, `metaos_pipeline/slots.py`) are created at
the first pass; a chosen slot is `working` from the plan on, so a second `plan` before `record`
cannot double-assign. `record` takes the harness's results (session ids, statuses, usage, PRs),
updates the slots, files every finished run as `runs/run-<n>.json`, transitions items through the backlog CLI (the pipeline is the single
writer of item status), and commits the vault. `report` renders the window for the human.

`run` is the event-driven runner (`metaos_pipeline/runner.py`): it takes the lease, blocks on
the inbox and runs one pass (record, plan, start steps, record) per batch of events. While a
runner holds the lease, `plan` and `record` refuse. `control lease take` is the human's move of
the lease to this machine; a runner never takes a lease held on another host by itself.
"""
from __future__ import annotations

import argparse
import functools
import glob
import json
import os
import signal
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml  # type: ignore

from metaos_pipeline import admission, controller, readyset, reflect, runner, slots, speculate
from metaos_pipeline import ledger as record
from metaos_pipeline.ledger import Ledger, usage_delta

ACTIVE = ("running", "spawning")
# `swarm.lanes` when the estate config does not set it: the default of its schema.
DEFAULT_LANES = 5


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    base = os.path.dirname(os.path.abspath(path))
    for key in ("vault", "backlog_cli", "model_path", "metaos_config"):
        if cfg.get(key) and not os.path.isabs(cfg[key]):
            cfg[key] = os.path.normpath(os.path.join(base, cfg[key]))
    return cfg


def find_metaos_config(cfg: dict, explicit: str | None) -> str | None:
    """The estate config: --metaos-config, else the pipeline config's `metaos_config`, else the nearest above it."""
    if explicit or cfg.get("metaos_config"):
        return os.path.abspath(explicit or cfg["metaos_config"])
    d = os.path.dirname(cfg["_config_path"])
    while True:
        cand = os.path.join(d, "meta-os.config.json")
        if os.path.isfile(cand):
            return cand
        if os.path.dirname(d) == d:
            return None
        d = os.path.dirname(d)


def load_estate(cfg: dict, metaos_config: str | None) -> tuple[str | None, dict]:
    path = find_metaos_config(cfg, metaos_config)
    if not path:
        return None, {}
    with open(path, encoding="utf-8") as fh:
        return path, json.load(fh)


def swarm_lanes(estate: dict) -> int:
    """The number of lane slots, `swarm.lanes`; a value that is not a positive integer stops the run."""
    n = (estate.get("swarm") or {}).get("lanes", DEFAULT_LANES)
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise SystemExit(f"tick: swarm.lanes must be a positive integer, not {n!r}")
    return n


def open_ledger(cfg: dict, state_dir: str | None, metaos_config: str | None) -> Ledger:
    """The ledger over the record repository's clone when `swarm.record_repository` is set, else over --state."""
    path, estate = load_estate(cfg, metaos_config)
    rr = (estate.get("swarm") or {}).get("record_repository") or {}
    if not rr.get("url"):
        if not state_dir:
            raise SystemExit("tick: no record: swarm.record_repository is unset and --state was not given")
        return Ledger(state_dir)
    if not rr.get("path"):
        raise SystemExit("tick: swarm.record_repository.url is set without its .path")
    clone = rr["path"]
    for name, value in (estate.get("vars") or {}).items():
        clone = clone.replace("${" + name + "}", str(value))
    clone = os.path.normpath(os.path.join(os.path.dirname(path), clone))
    record.check_not_nested(clone, os.path.dirname(cfg["_config_path"]),
                            bool((cfg.get("record_repository") or {}).get("allow_nested")))
    return Ledger(clone, remote=rr["url"])


def visibility_probe(cfg: dict) -> tuple:
    """(probe, key pattern) from the public-repo gate when `visibility_probe` is on, else (None, None).

    The probe runs once per repository per tick; the pattern is the instance's `publicRepoGate`
    one, so a public branch slug drops exactly the keys the gate would refuse.
    """
    if not cfg.get("visibility_probe"):
        return None, None
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import public_repo_gate  # noqa: E402  (scripts/ sits beside pipeline/ in the framework and every instance)
    try:
        gate_cfg = public_repo_gate.load_config(None)
    except public_repo_gate.GateError as exc:
        raise SystemExit(f"tick: public-repo gate configuration: {exc}") from None
    return functools.lru_cache(maxsize=None)(public_repo_gate.repo_visibility), gate_cfg.key_re


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


def planner_order(cfg: dict) -> list[str] | None:
    """The planner port's order, or None without a planner (the default order then holds).

    The hook only: `planner.order_file` names a JSON document with the planner's `next` and
    `queue`, written by whatever planner the instance runs. Admission still decides.
    """
    pc = cfg.get("planner") or {}
    if not pc.get("order_file"):
        return None
    path = pc["order_file"]
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(cfg.get("_config_path", ".")), path)
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return [str(k) for k in (doc.get("next") or []) + (doc.get("queue") or [])]


def emit(text: str, out_path: str | None) -> None:
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        print(text)


def slot_record(led: Ledger) -> tuple[list[dict], str | None]:
    """The slots, or an empty record and the reason when `lanes.json` is the prototype's per-run rows.

    The old rows are not migrated (the instance's record migration archives them); in a plain
    directory they are first copied aside to `lanes.prototype.json`, once, so nothing is lost.
    """
    lanes = led.lanes()
    if slots.is_slot_record(lanes):
        return lanes, None
    aside = os.path.join(led.dir, "lanes.prototype.json")
    if not led.remote and not os.path.exists(aside):
        with open(aside, "w", encoding="utf-8") as fh:
            json.dump(lanes, fh, indent=1, sort_keys=True)
    return [], (f"lanes.json holds {len(lanes)} row(s) of schema 1 or without slots: the slot record starts empty"
                + ("" if led.remote else "; the rows are kept in lanes.prototype.json"))


def cost(row: dict) -> float:
    return float((row.get("usage") or [{}])[-1].get("cost_usd", 0.0))


# ---------------------------------------------------------------- plan
def cmd_plan(cfg: dict, led: Ledger, out_path: str | None) -> int:
    plan = plan_pass(cfg, led)
    emit(json.dumps(plan, indent=1), out_path)
    return 2 if plan.get("refused") else 0


def plan_pass(cfg: dict, led: Ledger, now: float | None = None) -> dict:
    """One plan phase; its document (with `refused` when the admission gate refused the plan)."""
    reg = cfg.get("regulator") or {}
    defaults = {"N": int(reg.get("N0", 3)), "tick": 0, "paused": [], "spent": 0.0,
                "calibration": dict(cfg.get("calibration") or {}),
                "window_start": time.time(), "last_tick_ts": None}
    with led.locked("plan"):
        state = led.state(defaults)
        lanes, note = slot_record(led)
        if note:
            print(f"tick plan: {note}", file=sys.stderr)
        slots.check_invariant(lanes, state.get("sessions"))
        rows, hist = slots.run_rows(lanes), slots.history_rows(lanes)
        n_lanes = int(cfg.get("_swarm_lanes", DEFAULT_LANES))
        now = now or time.time()
        tick = int(state["tick"]) + 1
        hours = ((now - state["last_tick_ts"]) / 3600.0) if state.get("last_tick_ts") else float(cfg.get("tick_hours", 1.0))
        hours = max(hours, 1e-3)

        # ---- sensor: burn is the sum over lanes of (cost delta / elapsed) between each lane's
        # last two usage snapshots (or since its start when it has one), so a record step that
        # carried no usage cannot shrink the interval and inflate the reading.
        burn = 0.0
        for l in rows:
            snaps = l.get("usage") or []
            if not snaps:
                continue
            d_cost = usage_delta(l)[0]
            t1 = float(snaps[-1].get("ts", now))
            t0 = float(snaps[-2].get("ts", t1)) if len(snaps) > 1 else float(l.get("started") or l.get("planned_ts") or t1)
            dt_h = max((t1 - t0) / 3600.0, 1.0 / 60.0)
            if l.get("status") in ACTIVE or (now - t1) < 3600 * float(cfg.get("tick_hours", 1.0)):
                burn += d_cost / dt_h
        spent = float(state.get("spent_finished", 0.0)) + sum(cost(l) for l in rows)
        # Rate status is read only from snapshots taken at the latest record step: a rejection
        # seen last tick must not freeze the pipeline forever once the limit has reset.
        latest_ts = max((float(s.get("ts", 0)) for l in rows for s in (l.get("usage") or [])), default=0.0)
        rate_status = severity([s.get("rate_status", "allowed") for l in rows for s in (l.get("usage") or [])
                                if float(s.get("ts", 0)) >= latest_ts - 60])
        # The harness may report the account's own status at record time (needed when no lane
        # is running to observe it through); the fresher reading wins.
        acct = state.get("account_rate_status") or {}
        if acct and float(acct.get("ts", 0)) >= latest_ts:
            rate_status = severity([acct.get("status", "allowed")])

        # ---- admission (the ready set) and saturation; a stale index refuses the whole plan
        try:
            adm = admission.admit(cfg["vault"], cfg, lanes, state.get("retries") or {}, *visibility_probe(cfg),
                                  planner_order=planner_order(cfg))
        except admission.Refused as exc:
            led.run({"phase": "plan", "tick": tick, "ts": now, "refused": str(exc)})
            return {"tick": tick, "ts": now, "refused": str(exc)}
        if note:
            led.event("slot_record_reset", reason=note)
        lanes = slots.ensure(lanes, n_lanes, led.event)
        ready = adm.admitted
        active = rows
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
        check = [{"lane_id": l["lane_id"], "run_id": l["run_id"], "session_id": l.get("session_id"), "branch": l.get("branch"),
                  "repo": l.get("repo"), "kind": l.get("kind")} for l in active if l.get("session_id")]
        cap = float(reg.get("lane_cap", 0.0))
        interrupt = [l["lane_id"] for l in active
                     if controller.over_cap(cost(l), cap)]

        # ---- review-queue guard (reflection level 1): pause spaces whose pipeline output waits
        review_cap = int(cfg.get("review_cap_per_space", 4))
        paused: list[str] = []
        for space in (cfg.get("spaces") or {}):
            n_review = len([l for l in hist if l.get("space") == space and l.get("status") == "in_review"])
            if n_review >= review_cap:
                paused.append(space)

        # ---- speculation first (it reserves its tokens), then work assignment
        spawn: list[dict] = []
        spec_spawn: list[dict] = []
        free = min(max(0, N - len(rows)), len([s for s in lanes if slots.eligible(s, n_lanes)]))
        if not freeze and free > 0:
            spec_cfg = cfg.get("speculation") or {}
            cfg_dir = os.path.dirname(os.path.abspath(cfg.get("_config_path", ".")))
            for plan in speculate.plan_speculation(spec_cfg.get("decisions") or [], rows + hist, N, free,
                                                   float(spec_cfg.get("share", 0.34)), float(spec_cfg.get("latency_days", 0.5))):
                led.event("speculation_considered", decision=plan.decision_id, go=plan.go, reason=plan.reason, tick=tick)
                if not plan.go:
                    continue
                for br in plan.branches:
                    prompt = br.get("prompt") or ""
                    if br.get("prompt_file"):
                        with open(os.path.join(cfg_dir, br["prompt_file"]), encoding="utf-8") as fh:
                            prompt = fh.read()
                    slot = slots.pick(lanes, br["repo"], n_lanes)
                    if slot is None:
                        break
                    run = slots.start(slot, br["repo"], tick, now, led.event, kind="spec", decision=plan.decision_id,
                                      branch_key=br["key"], space=br.get("space", ""), branch=br["outcome_branch"],
                                      primary_tag=f"spec:{plan.decision_id}", retries=0)
                    spec_spawn.append({"lane_id": slot["lane_id"], "run_id": run["run_id"], "repo": slot["project"],
                                       **{k: run[k] for k in ("kind", "decision", "branch_key", "branch")}, "prompt": prompt})
                free -= len(plan.branches)
            rows = slots.run_rows(lanes)
            cfg_for_assign = dict(cfg); cfg_for_assign["regulator"] = dict(reg, N=N)
            chosen = readyset.assign(slots.prefer_bound(ready, lanes, n_lanes), rows, free, cfg_for_assign, paused) if free > 0 else []
            for it in chosen:
                slot = slots.pick(lanes, it.repo, n_lanes)
                if slot is None:
                    break
                ref = record.item_ref(cfg["vault"], it.path)
                run = slots.start(slot, it.repo, tick, now, led.event, kind="work", item=it.id, space=it.space,
                                  branch=it.branch, primary_tag=it.primary_tag, points=it.points, item_ref=ref,
                                  retries=int((state.get("retries") or {}).get(it.id, 0)))
                # The repository's visibility, probed or declared, decides the note and the title rule.
                prompt = render(cfg.get("lane_prompt", ""), id=it.id, title=it.title, repo=it.repo, branch=it.branch,
                                space=it.space, item_body=item_body(it.path, int(cfg.get("item_body_limit", 12000))),
                                public_note=(cfg.get("public_repo_note", "") if it.public else ""),
                                pr_title_prefix=("" if it.public else f"{it.id}: "), lane_id=slot["lane_id"],
                                project=slot["project"], vault_sha=ref["vault_sha"] or "", item_sha256=ref["sha256"])
                spawn.append({"lane_id": slot["lane_id"], "run_id": run["run_id"], "repo": slot["project"],
                              **{k: run[k] for k in ("kind", "item", "space", "branch", "item_ref")},
                              "title": it.title, "prompt": prompt})
            rows = slots.run_rows(lanes)
            slots.check_invariant(lanes, state.get("sessions"))

        # ---- reflection
        model = reflect.load_model(cfg["model_path"])
        m_cfg = int(reg.get("N_max", 4))
        predicted = reflect.predict(model, m_cfg, N, state["calibration"])
        measured = reflect.measure(cfg["vault"], rows + hist, led.runs(), burn, spent)
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
                "ready_set": [i.id for i in ready], **adm.as_plan(), "paused_spaces": paused, "spawn": spawn, "spec_spawn": spec_spawn,
                "check": check, "interrupt": interrupt, "reflection": refl,
                "lanes": [{k: s.get(k) for k in ("lane_id", "project", "actual")} for s in lanes]}
        led.run({"phase": "plan", **({"slot_record": note} if note else {}),
                 **{k: v for k, v in plan.items() if k not in ("spawn", "spec_spawn", "reflection", "lanes")},
                 "spawn_ids": [s["lane_id"] for s in spawn], "spec_ids": [s["lane_id"] for s in spec_spawn]})
        if led.remote:  # the record keeps the plan without its prompts: an item is named by item_ref
            led.write_pass_file("plan", tick, now, {**plan, "spawn": [{k: v for k, v in s.items() if k != "prompt"} for s in spawn],
                                                    "spec_spawn": [{k: v for k, v in s.items() if k != "prompt"} for s in spec_spawn]})
    return plan


# ---------------------------------------------------------------- record
def backlog(cfg: dict, *args: str) -> tuple[int, str]:
    cli = cfg.get("backlog_cli")
    if not cli:
        return 0, "no backlog_cli configured (dry run)"
    # A replayed record phase must not repeat a transition: the vault's status decides.
    if args[:1] == ("transition",) and len(args) >= 3 and vault_status(cfg["vault"], args[1]) == args[2]:
        return 0, f"{args[1]} is already {args[2]}: not transitioned again"
    # The backlog CLI finds the vault through METAOS_VAULT. The second name is a deprecated
    # alias, still exported so an instance CLI that reads it keeps working; drop it once
    # every instance CLI reads METAOS_VAULT.
    env = dict(os.environ, METAOS_VAULT=cfg["vault"], MOVA_VAULT=cfg["vault"])
    r = subprocess.run([sys.executable, cli, *args], cwd=cfg["vault"], env=env, capture_output=True, text=True, timeout=120)
    return r.returncode, (r.stdout + r.stderr).strip()


def vault_status(vault: str, key: str) -> str | None:
    """The item's status in the vault now (its file carries its id), or None when it is not found."""
    for tier in ("raw", "wiki", "output"):
        for path in glob.glob(os.path.join(glob.escape(vault), "*", tier, glob.escape(key) + ".md")):
            return str(readyset.front_matter(path).get("status") or "") or None
    return None


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
    # Stage only the spaces this pipeline writes to (directories, not shell globs: there is
    # no shell here and git's own glob would not expand `*/raw` reliably).
    spaces = [s for s in (cfg.get("spaces") or {}) if os.path.isdir(os.path.join(v, s))]
    g("add", "-A", "--", *spaces)
    c = g("commit", "-q", "-m", message)
    if c.returncode != 0:
        return "commit failed: " + (c.stdout + c.stderr)[-300:]
    p = g("push", "-q", "origin", "main")
    return "pushed" if p.returncode == 0 else "push failed: " + p.stderr[-300:]


def cmd_record(cfg: dict, led: Ledger, results_path: str) -> int:
    with open(results_path, encoding="utf-8") as fh:
        res = json.load(fh)
    out = record_pass(cfg, led, res)
    out["vault"] = record_vault(cfg, out)
    print(json.dumps(out, indent=1))
    return 0


def record_vault(cfg: dict, out: dict) -> str:
    """Commit the vault after a record phase that transitioned something."""
    if not out["transitions"]:
        return "no transitions"
    msg = "pipeline tick %s: %s" % (out["tick"], "; ".join(out["transitions"]))
    return vault_commit(cfg, msg + "\n\nWritten by the autonomous pipeline's record step; lanes and usage in the instance ledger.")


def record_pass(cfg: dict, led: Ledger, res: dict, now: float | None = None) -> dict:
    """One record phase over the harness's (or the runner's) results; the tick, spend and transitions."""
    now = now or time.time()
    transitions: list[str] = []
    with led.locked("record"):
        state = led.state({"N": 1, "tick": 0, "spent": 0.0})
        lanes, note = slot_record(led)
        if note:
            print(f"tick record: {note}", file=sys.stderr)
        index = state.setdefault("sessions", {})
        slots.check_invariant(lanes, index)
        by_id = {l["lane_id"]: l for l in lanes}

        def current(r: dict) -> dict | None:
            """The slot a result is about, when it still holds the run the result names."""
            slot = by_id.get(r.get("lane_id"))
            if not slot or not slot["run"] or (r.get("run_id") and r["run_id"] != slot["run"]["run_id"]):
                return None
            return slot

        def end(slot: dict, outcome: str, pr: dict | None = None, **extra) -> None:
            final = cost(slot["run"])
            doc = slots.finish(slot, outcome, now, pr)
            slots.index_sessions(index, doc)
            n = led.finished_run(state, {**doc, **extra})
            state["spent_finished"] = float(state.get("spent_finished", 0.0)) + final
            led.event("lane_ended", lane_id=slot["lane_id"], run_id=doc["run_id"], status=outcome, item=doc.get("item"), run=n)
            slots.settle(slot, led.event)

        if res.get("account_rate_status"):
            state["account_rate_status"] = {"status": res["account_rate_status"], "ts": now}
            led.event("account_rate_status", status=res["account_rate_status"])
        for s in res.get("spawned") or []:
            slot = current(s)
            if not slot:
                continue
            run = slot["run"]
            if s.get("ok"):
                run.update({k: s[k] for k in ("pid", "log") if s.get(k)})  # the runner's step process
                slots.spawned(slot, s.get("session_id"), now, index)
                led.event("lane_started", lane_id=slot["lane_id"], run_id=run["run_id"], session_id=s.get("session_id"), item=run.get("item"))
                if run["kind"] == "work":
                    rc, msg = backlog(cfg, "transition", run["item"], "IN PROGRESS")
                    led.event("transition", item=run["item"], to="IN PROGRESS", rc=rc, msg=msg[-200:])
                    if rc == 0:
                        transitions.append(f"{run['item']} → IN PROGRESS (lane {slot['lane_id']}, session {s.get('session_id')}, branch {run['branch']})")
            else:
                led.event("lane_failed_spawn", lane_id=slot["lane_id"], run_id=run["run_id"], error=s.get("error"))
                end(slot, "failed_spawn", error=s.get("error"))
        for c in res.get("checks") or []:
            slot = current(c)
            if not slot:
                continue
            run = slot["run"]
            u = c.get("usage") or {}
            run.setdefault("usage", []).append({"ts": now, "cost_usd": float(u.get("cost_usd", 0.0)),
                                                "tokens": float(u.get("tokens", 0.0)),
                                                "rate_status": c.get("rate_status", "allowed")})
            # The session's own last activity when the harness reports it, else the moment it was read.
            slots.heartbeat(slot, float(c.get("activity_ts") or now))
            st = (c.get("status") or "").lower()
            pr = c.get("pr")
            if pr:
                run["pr"] = pr
            if st in ("idle", "failed", "archived", "completed", "review_ready", "blocked") or c.get("ended"):
                if run["kind"] == "spec":
                    outcome = "done" if c.get("branch_pushed") else "failed"
                elif pr:
                    outcome = "in_review"
                    rc, msg = backlog(cfg, "transition", run["item"], "IN REVIEW")
                    led.event("transition", item=run["item"], to="IN REVIEW", rc=rc, msg=msg[-200:])
                    if rc == 0:
                        transitions.append(f"{run['item']} → IN REVIEW (PR {pr.get('url', pr)})")
                elif c.get("branch_pushed"):
                    outcome = "ended_no_pr"
                else:
                    outcome = c.get("outcome") or ("failed" if st == "failed" else "ended_empty")
                    # Nothing was produced: hand the item back to the ready set (single writer),
                    # counting the attempt so a broken item cannot be retried forever.
                    if run.get("item"):
                        tries = int((state.get("retries") or {}).get(run["item"], 0)) + 1
                        rc, msg = backlog(cfg, "transition", run["item"], "REFINED")
                        led.event("transition", item=run["item"], to="REFINED", rc=rc, msg=msg[-200:], reason=c.get("reason"))
                        if rc == 0:
                            transitions.append(f"{run['item']} → REFINED (lane {slot['lane_id']} {outcome}; retry {tries}"
                                               + (f"; {c['reason']}" if c.get("reason") else "") + ")")
                        state.setdefault("retries", {})[run["item"]] = tries
                end(slot, outcome, pr, **({"reason": c["reason"]} if c.get("reason") else {}))
        for lid in res.get("interrupted") or []:
            slot = current({"lane_id": lid})
            if slot:
                led.event("lane_interrupted", lane_id=lid, run_id=slot["run"]["run_id"])
                end(slot, "interrupted")
        slots.check_invariant(lanes, index)
        spent = float(state.get("spent_finished", 0.0)) + sum(cost(l) for l in slots.run_rows(lanes))
        state.update({"last_tick_ts": now, "spent": spent})
        led.save_lanes(lanes)
        led.save_state(state)
        if led.remote:
            led.write_pass_file("results", int(state.get("tick") or 0), now, res)
        led.run({"phase": "record", "tick": state.get("tick"), "spent": round(spent, 3),
                 "transitions": transitions, "n_checks": len(res.get("checks") or []),
                 "n_spawned_ok": len([s for s in (res.get("spawned") or []) if s.get("ok")]),
                 **({"slot_record": note} if note else {})})
    return {"tick": state.get("tick"), "spent": round(spent, 3), "transitions": transitions}


# ---------------------------------------------------------------- report
def cmd_report(cfg: dict, led: Ledger, out_path: str | None) -> int:
    state = led.state({"N": 0, "tick": 0, "spent": 0.0})
    lanes, note = led.lanes(), None
    if not slots.is_slot_record(lanes):
        lanes, note = [], "lanes.json holds no slots yet: the next plan starts the slot record"
    rows, hist = slots.run_rows(lanes), slots.history_rows(lanes)
    runs = led.runs()
    refl = led.reflections()
    reg = cfg.get("regulator") or {}
    L = ["# Pipeline window report", "",
         f"Ticks: {state.get('tick')} · N now {state.get('N')} (bounds {reg.get('N_min')}–{reg.get('N_max')}) · "
         f"spent {state.get('spent', 0):.2f} of budget {reg.get('budget')} · window {reg.get('window_hours')} h", ""]
    L += ["## Lanes", ""] + ([f"_{note}_", ""] if note else [])
    L += ["| lane | project | state | run | item / decision | branch | cost | last runs |", "|---|---|---|---|---|---|---|---|"]
    for sl in lanes:
        run = sl.get("run") or {}
        past = "; ".join(f"{h.get('item') or h.get('decision')} {h.get('outcome')}" for h in sl.get("history") or [])
        L.append(f"| {sl['lane_id']} | {sl.get('project') or '—'} | {sl['actual']} | {run.get('run_id', '')} | "
                 f"{run.get('item') or run.get('decision') or ''} | `{run.get('branch', '')}` | {cost(run):.2f} | {past} |")
    L += ["", "## Regulator trace", "", "| tick | N | burn/h | setpoint/h | rate | freeze | reason |", "|---|---|---|---|---|---|---|"]
    for r in runs:
        if r.get("phase") == "plan" and not r.get("refused"):
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
    spec = [l for l in rows + hist if l.get("kind") == "spec"]
    if spec:
        L += ["## Speculative branches (read first, pick one)", ""]
        for l in spec:
            L.append(f"- {l['decision']} / **{l.get('branch_key', '')}** → `{l.get('branch', '')}` on {l.get('repo', l['lane_id'])} — {l['status']}")
        L.append("")
    last = next((r for r in reversed(runs) if r.get("phase") == "plan"), None)
    if last and (last.get("refused") or last.get("excluded") or last.get("orphans")):
        L += ["## Not admitted (last plan)", ""]
        if last.get("refused"):
            L.append(f"- the plan refused: {last['refused']}")
        for k, why in (last.get("excluded") or {}).items():
            L.append(f"- {k}: {why}")
        for k in last.get("orphans") or []:
            L.append(f"- {k}: orphan, IN PROGRESS with no lane holding it (for the watchdog)")
        L.append("")
    L += ["## For the human round", ""]
    seen = set()
    for rr in refl:
        for e in rr.get("escalations") or []:
            if e not in seen:
                seen.add(e); L.append(f"- [ ] {e}")
    for l in hist:
        if l["status"] == "in_review":
            L.append(f"- [ ] Review {l.get('item')}: {l.get('pr') or l.get('run_id')}")
        if l["status"] in ("ended_no_pr", "ended_empty", "failed", "failed_spawn", "interrupted"):
            L.append(f"- [ ] Lane {l['lane_id']} run {l.get('run_id')} for {l.get('item') or l.get('decision')} ended `{l['status']}` — decide: retry, re-refine, or drop")
    text = "\n".join(L) + "\n"
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        print(text)
    return 0


# ---------------------------------------------------------------- run, control
def cmd_run(cfg: dict, led: Ledger, inbox: str, work: str | None) -> int:
    swarm = cfg["_swarm"]
    r = runner.Runner(cfg, led, os.path.abspath(inbox), os.path.abspath(work or os.path.join(os.path.dirname(os.path.abspath(inbox)), "runner-work")),
                      plan=plan_pass, record=record_pass, vault=record_vault,
                      stall_minutes=float(swarm.get("stall_minutes", runner.STALL_MINUTES)))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, r.stop)  # finish the pass in progress, release the lease, exit
    return r.run()


def cmd_control(cfg: dict, led: Ledger, a: argparse.Namespace) -> int:
    """`control lease take`: move the lease to this host (human only); its runner takes it at its next start."""
    with led.locked("control"):
        state = led.state()
        old = state.get("loop") or {}
        state["loop"] = {"holder": None, "host": socket.gethostname(), "pid": None, "started": time.time(),
                         "epoch": int(old.get("epoch") or 0) + 1}
        led.event("lease_moved", by="control", **{"from": old.get("host")}, to=state["loop"]["host"],
                  epoch=state["loop"]["epoch"], reason=a.reason)
        led.save_state(state)
    print(json.dumps({"lease": state["loop"]}, indent=1))
    return 0


def lease_holder(led: Ledger) -> dict | None:
    loop = led.state().get("loop") or {}
    return loop if loop.get("holder") else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--state", help="the plain record directory, used when swarm.record_repository is unset")
    ap.add_argument("--metaos-config", help="the estate config (default: the nearest meta-os.config.json above --config)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("--out")
    r = sub.add_parser("record"); r.add_argument("--results", required=True)
    q = sub.add_parser("report"); q.add_argument("--out")
    u = sub.add_parser("run"); u.add_argument("--inbox", required=True); u.add_argument("--work")
    c = sub.add_parser("control"); c.add_argument("target", choices=["lease"]); c.add_argument("action", choices=["take"])
    c.add_argument("--reason", required=True)
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    cfg["_config_path"] = os.path.abspath(a.config)
    estate = load_estate(cfg, a.metaos_config)[1]
    cfg["_swarm_lanes"] = swarm_lanes(estate)
    cfg["_swarm"] = estate.get("swarm") or {}
    try:
        led = open_ledger(cfg, a.state, a.metaos_config)
        print(f"tick {a.cmd}: record in {led.describe()}", file=sys.stderr)
        if a.cmd in ("plan", "record") and lease_holder(led):
            held = lease_holder(led)
            raise SystemExit(f"tick: {a.cmd} refused: the runner {held['holder']} on {held.get('host')} holds the lease, "
                             "and it alone runs passes")
        if a.cmd == "run":
            return cmd_run(cfg, led, a.inbox, a.work)
        if a.cmd == "control":
            return cmd_control(cfg, led, a)
        if a.cmd == "plan":
            return led.replay(lambda: cmd_plan(cfg, led, a.out))
        if a.cmd == "record":
            return led.replay(lambda: cmd_record(cfg, led, a.results))
        return cmd_report(cfg, led, a.out)
    except record.LedgerError as exc:
        raise SystemExit(f"tick: stopped: {exc}") from None


if __name__ == "__main__":
    sys.exit(main())
