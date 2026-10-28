"""Lane slots: durable lanes, one project each, one run at a time.

A slot (`lanes.json`, one record per slot `lane-1 … lane-<swarm.lanes>`) outlives its runs:

- `project` is the one repository it serves; `desired` is the control plane's, `actual` one of
  `idle | working | draining | paused | stopped | stale`; `run` is null or the current run;
  `history[]` keeps the last five finished runs, and each finished run is filed whole as
  `runs/run-<n>.json` with its outcome and PR.
- A slot rebinds to another project only while idle, with no run and no open session, and the
  rebind is a `lane_rebound` event. A rebind asked for mid-run drains first: no new item, the
  run ends, its sessions are archived, then the slot is idle and rebinds.
- A session serves one project, ever: `check_invariant` refuses a record where a `session_id`
  appears under two projects, under a slot of another project, or where two slots hold one item.

This module decides and mutates slot dicts; the ledger writes them. It never starts or polls a
session; the heartbeat is stamped from the activity the harness reports in its results.
"""
from __future__ import annotations

import re
import uuid
from typing import Callable, Iterable

from .ledger import LedgerError

ACTUAL = ("idle", "working", "draining", "paused", "stopped", "stale")
HOLDING = ("working", "draining", "paused", "stale")
HISTORY = 5
SLOT_ID = re.compile(r"^lane-([1-9][0-9]*)$")

Emit = Callable[..., None]


class InvariantBroken(LedgerError):
    """The record contradicts a slot invariant; the message names the session or item."""


def index(slot: dict) -> int:
    return int(SLOT_ID.match(slot["lane_id"]).group(1))


def is_slot_record(lanes: list[dict]) -> bool:
    """True for a slot record of schema 2 (or an empty one); False for the prototype's per-run rows."""
    return all(l.get("schema", 1) >= 2 and "actual" in l and SLOT_ID.match(str(l.get("lane_id", ""))) for l in lanes)


def new_slot(n: int) -> dict:
    return {"lane_id": f"lane-{n}", "project": None, "desired": "running", "actual": "idle", "run": None, "history": []}


def ensure(slots: list[dict], lanes: int, emit: Emit) -> list[dict]:
    """Create the missing slots up to `lanes`; drain every working slot above it (never delete one)."""
    have = {index(s) for s in slots}
    for n in range(1, lanes + 1):
        if n not in have:
            slots.append(new_slot(n))
    slots.sort(key=index)
    for s in slots:
        if index(s) > lanes and s["run"] and s["actual"] == "working":
            drain(s, f"swarm.lanes lowered to {lanes}", emit)
    return slots


def drained(slot: dict) -> bool:
    return slot["actual"] == "idle" and slot["run"] is None


def eligible(slot: dict, lanes: int) -> bool:
    """Free to take a run: idle, drained, wanted running, and inside `swarm.lanes`."""
    return drained(slot) and slot.get("desired", "running") == "running" and index(slot) <= lanes


def rebind(slot: dict, project: str, reason: str, emit: Emit) -> None:
    if not drained(slot):
        raise InvariantBroken(f"{slot['lane_id']} cannot rebind while {slot['actual']}: drain it first")
    if slot["project"] and slot["project"] != project:
        emit("lane_rebound", lane_id=slot["lane_id"], **{"from": slot["project"]}, to=project, reason=reason)
    slot["project"] = project


def drain(slot: dict, reason: str, emit: Emit, to: str | None = None) -> None:
    """Take nothing new; when the run ends the slot goes idle (and rebinds to `to`, if given)."""
    if slot["run"] is None:
        if to:
            rebind(slot, to, reason, emit)
        return
    slot["actual"] = "draining"
    slot["drain"] = {"reason": reason, "to": to}
    emit("lane_draining", lane_id=slot["lane_id"], run_id=slot["run"]["run_id"], reason=reason, to=to)


def pick(slots: list[dict], project: str, lanes: int) -> dict | None:
    """The slot a run of `project` takes: one bound to it, else an unbound one, else one to rebind."""
    free = [s for s in slots if eligible(s, lanes)]
    for want in (lambda s: s["project"] == project, lambda s: s["project"] is None, lambda s: True):
        for s in free:
            if want(s):
                return s
    return None


def prefer_bound(ready: list, slots: list[dict], lanes: int) -> list:
    """The ready order with, per project, as many of its items first as it has idle slots bound to it."""
    quota: dict[str, int] = {}
    for s in slots:
        if eligible(s, lanes) and s["project"]:
            quota[s["project"]] = quota.get(s["project"], 0) + 1
    first = []
    for it in ready:
        if quota.get(it.repo, 0) > 0:
            quota[it.repo] -= 1
            first.append(it)
    return first + [it for it in ready if it not in first]


def start(slot: dict, project: str, tick: int, now: float, emit: Emit, **fields) -> dict:
    """Bind the slot (a rebind if it served another project) and give it a new run, not yet spawned."""
    rebind(slot, project, "assignment", emit)
    run = {"run_id": f"r-{tick}-{uuid.uuid4().hex[:6]}", "sessions": [], "started": None, "heartbeat": None,
           "usage": [], "planned_ts": now, **fields}
    slot.update({"actual": "working", "run": run})
    return run


def spawned(slot: dict, session_id: str, now: float) -> None:
    run = slot["run"]
    run["sessions"].append({"session_id": session_id, "project": slot["project"], "started": now, "ended": None})
    run["started"] = run["started"] or now
    run["heartbeat"] = now


def heartbeat(slot: dict, activity_ts: float) -> None:
    run = slot["run"]
    run["heartbeat"] = max(float(run.get("heartbeat") or 0.0), float(activity_ts))


def finish(slot: dict, outcome: str, now: float, pr: dict | None = None) -> dict:
    """End the run: archive its sessions, return the run record to file, keep it in `history[]`.

    The slot goes idle; a draining slot keeps its pending rebind for `settle`, after the run is filed.
    """
    run = slot["run"]
    for sess in run["sessions"]:
        sess["ended"] = sess.get("ended") or now
    doc = {**run, "lane_id": slot["lane_id"], "project": slot["project"], "outcome": outcome, "ended": now,
           "pr": pr if pr is not None else run.get("pr")}
    entry = {k: doc.get(k) for k in ("run_id", "kind", "item", "decision", "space", "outcome", "ended")}
    entry["pr"] = (doc["pr"] or {}).get("url") if isinstance(doc["pr"], dict) else doc["pr"]
    slot["history"] = (slot.get("history") or [])[-(HISTORY - 1):] + [entry]
    slot["run"] = None
    slot["actual"] = "idle"
    return doc


def settle(slot: dict, emit: Emit) -> None:
    """A drained slot takes the rebind its drain asked for."""
    pending = slot.pop("drain", None)
    if pending and pending.get("to"):
        rebind(slot, pending["to"], pending["reason"], emit)


def check_invariant(slots: Iterable[dict]) -> None:
    """Every pass: a session under exactly one project, a run's project its slot's, one slot per item."""
    projects: dict[str, set] = {}
    items: dict[str, str] = {}
    for s in slots:
        if s.get("actual") not in ACTUAL:
            raise InvariantBroken(f"{s.get('lane_id')}: actual state {s.get('actual')!r} is not one of {ACTUAL}")
        run = s.get("run")
        if run is None:
            continue
        if not isinstance(run, dict):
            raise InvariantBroken(f"{s['lane_id']} holds {type(run).__name__} as its run: a slot holds one run")
        key = run.get("item") if run.get("kind") != "spec" else None  # a decision's two branches share it
        if key:
            if key in items:
                raise InvariantBroken(f"item {key} is held by both {items[key]} and {s['lane_id']}")
            items[key] = s["lane_id"]
        for sess in run.get("sessions") or []:
            projects.setdefault(sess["session_id"], set()).add(sess.get("project"))
            if sess.get("project") != s.get("project"):
                raise InvariantBroken(f"session {sess['session_id']} serves {sess.get('project')} under "
                                      f"{s['lane_id']}, which is bound to {s.get('project')}")
    for sid, ps in sorted(projects.items()):
        if len(ps) > 1:
            raise InvariantBroken(f"session {sid} appears under {len(ps)} projects: {', '.join(sorted(map(str, ps)))}")


def run_rows(slots: Iterable[dict]) -> list[dict]:
    """Each current run as the flat lane row the regulator, assignment and reflection read."""
    out = []
    for s in slots:
        run = s.get("run")
        if run:
            sess = run.get("sessions") or []
            out.append({**run, "lane_id": s["lane_id"], "repo": s["project"],
                        "status": "running" if run.get("started") else "spawning",
                        "session_id": sess[-1]["session_id"] if sess else None})
    return out


def history_rows(slots: Iterable[dict]) -> list[dict]:
    """Each kept finished run as a row whose `status` is its outcome."""
    return [{**h, "lane_id": s["lane_id"], "status": h.get("outcome")} for s in slots for h in s.get("history") or []]
