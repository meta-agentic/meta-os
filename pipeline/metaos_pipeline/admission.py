"""Admission gate: which items a lane may start now, and why every other ready item may not.

The rules, in order; an excluded item carries the reason of the first rule it fails:

0. **Executable space.** Its space is one the instance declares executable, with an active
   sprint: *not executable*, *no active sprint in S*.
1. **Status.** A configured ready status (default `REFINED`); an epic never.
2. **Blockers, from the graph index.** Every blocker the vault's dependency index lists for
   it is `DONE`: *blocked by X (status)*, *in pipeline behind X (status)* for a blocker in a
   lane or in review, *blocked by epic X (status), which is not finished*, and a `NO GO`
   blocker excludes the item and everything behind it (*its premise is gone*). The gate
   refuses to run on a missing or stale index (`Refused`).
3. **Held by a lane.** An item a lane holds (`spawning`, `running`, `paused`, `in_review`)
   is never admitted again; neither is one past its retry cap. An item `IN PROGRESS` with
   no lane holding it is an orphan, reported for the watchdog, never admitted.
4. **Holding labels and parked work.** The instance's `blocking_labels`, the parked label on
   the item or on any ancestor epic, and the instance's title exclusion.
5. **Project.** A repository resolves for it.

The one rule (same space, repository and primary tag run in sequence) stays in
`readyset.assign`. Among the admitted, the order is the planner's when one is given, else
committed-first, priority, points ascending; the planner never widens the admitted set.
"""
from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass, field

from . import readyset
from .readyset import Item

EDGE = re.compile(r"^\[\[([^\[\]]+)\]\]\s*->\s*\[\[([^\[\]]+)\]\]")
TIERS = ("raw", "wiki", "output")
PIPELINE = ("IN PROGRESS", "IN REVIEW")
FINISHED = ("DONE", "NO GO")
# Lane rows that hold their item: the current per-run rows and the slot record's actual states.
HOLDING = ("spawning", "running", "paused", "in_review")
SLOT_HOLDING = ("working", "draining", "paused", "stale")


class Refused(Exception):
    """The gate will not decide on this vault; the message is the reason."""


@dataclass
class Admission:
    admitted: list[Item]
    excluded: dict[str, str] = field(default_factory=dict)
    orphans: list[str] = field(default_factory=list)
    planner_ignored: dict[str, str] = field(default_factory=dict)

    def as_plan(self) -> dict:
        return {"admitted": [i.id for i in self.admitted], "excluded": dict(sorted(self.excluded.items())),
                "orphans": self.orphans, "planner_ignored": dict(sorted(self.planner_ignored.items()))}


def all_spaces(vault: str) -> list[str]:
    return sorted({os.path.basename(os.path.dirname(d)) for t in TIERS for d in glob.glob(os.path.join(vault, "*", t))
                   if os.path.isdir(d)})


def read_index(vault: str, name: str) -> set[tuple[str, str]]:
    path = os.path.join(vault, name)
    if not os.path.isfile(path):
        raise Refused(f"the dependency index {name} is missing: regenerate it in the vault before planning")
    with open(path, encoding="utf-8") as fh:
        return {(m.group(1).strip(), m.group(2).strip()) for m in map(EDGE.match, fh) if m}


def check_index(items: dict[str, Item], edges: set[tuple[str, str]], name: str) -> None:
    """Refuse when the index's edges differ from the items' own `dependencies`."""
    expected = {(i.id, d) for i in items.values() for d in i.dependencies}
    missing, extra = sorted(expected - edges), sorted(edges - expected)
    if missing or extra:
        sample = "; ".join([f"missing {s} -> {d}" for s, d in missing[:3]] + [f"extra {s} -> {d}" for s, d in extra[:3]])
        raise Refused(f"the dependency index {name} is stale ({len(missing)} edge(s) missing, {len(extra)} extra: "
                      f"{sample}): regenerate it in the vault before planning")


def premise_gone(items: dict[str, Item], blockers: dict[str, list[str]]) -> dict[str, str]:
    """Every open item behind a NO GO blocker, directly or through other open items."""
    root: dict[str, str] = {}
    for s, ds in blockers.items():
        if s in items and items[s].status not in FINISHED:
            for d in ds:
                if d in items and items[d].status == "NO GO":
                    root[s] = d
                    break
    gone = {s: f"blocked by {d} (NO GO): its premise is gone" for s, d in root.items()}
    changed = True
    while changed:
        changed = False
        for s, ds in sorted(blockers.items()):
            if s in gone or s not in items or items[s].status in FINISHED:
                continue
            for d in ds:
                if d in gone:
                    root[s] = root[d]
                    gone[s] = f"behind {d}, blocked by {root[d]} (NO GO): its premise is gone"
                    changed = True
                    break
    return gone


def blocker_reason(it: Item, items: dict[str, Item], blockers: dict[str, list[str]], gone: dict[str, str]) -> str | None:
    if it.id in gone:
        return gone[it.id]
    for d in blockers.get(it.id, ()):
        b = items.get(d)
        if b is None:
            return f"blocked by {d}, which is not an item"
        if b.status == "DONE":
            continue
        if b.kind == "epic":
            return f"blocked by epic {d} ({b.status}), which is not finished"
        if b.status in PIPELINE:
            return f"in pipeline behind {d} ({b.status})"
        return f"blocked by {d} ({b.status})"
    return None


def parked_reason(it: Item, items: dict[str, Item], label: str) -> str | None:
    if label in it.labels:
        return f"label {label}"
    seen: set[str] = set()
    epic = it.epic
    while epic and epic not in seen and epic in items:
        seen.add(epic)
        if label in items[epic].labels:
            return f"epic {epic} is {label}"
        epic = items[epic].epic
    return None


def holders(lanes: list[dict]) -> dict[str, str]:
    """item id -> the lane holding it, as `lane L (status)`."""
    out: dict[str, str] = {}
    for l in lanes:
        run = l.get("run") or {}
        if l.get("item") and l.get("status") in HOLDING:
            out.setdefault(str(l["item"]), f"lane {l.get('lane_id')} ({l['status']})")
        elif run.get("item") and l.get("actual") in SLOT_HOLDING:
            out.setdefault(str(run["item"]), f"lane {l.get('lane_id')} ({l['actual']})")
    return out


def apply_planner(admitted: list[Item], excluded: dict[str, str], order: list[str] | None):
    """The planner's order among the admitted; an id it lists that the gate rejects is ignored
    with the reason, and an admitted id it does not list follows in the default order."""
    if order is None:
        return admitted, {}
    by_id = {i.id: i for i in admitted}
    out: list[Item] = []
    ignored: dict[str, str] = {}
    for k in order:
        if k in by_id:
            if by_id[k] not in out:
                out.append(by_id[k])
        else:
            ignored[k] = f"listed by the planner, not admitted: {excluded.get(k, 'not a ready item')}"
    return out + [i for i in admitted if i not in out], ignored


def admit(vault: str, cfg: dict, lanes: list[dict], retries: dict | None = None, visibility=None, key_re=None,
          planner_order: list[str] | None = None) -> Admission:
    spaces_cfg: dict = cfg.get("spaces") or {}
    executable = {s for s, c in spaces_cfg.items() if (c or {}).get("executable", True)}
    index_name = cfg.get("graph_index", "_graphindex.md")
    items = readyset.load_items(vault, all_spaces(vault))
    edges = read_index(vault, index_name)
    check_index(items, edges, index_name)
    blockers: dict[str, list[str]] = {}
    for s, d in sorted(edges):
        blockers.setdefault(s, []).append(d)
    gone = premise_gone(items, blockers)
    sprints = readyset.active_sprints(vault)
    ready_statuses = set(cfg.get("ready_statuses") or ["REFINED"])
    blocking = set(cfg.get("blocking_labels") or ["blocked", "needs-po"])
    parked = str(cfg.get("parked_label", "parked"))
    title_rx = re.compile(cfg["exclude_title_regex"]) if cfg.get("exclude_title_regex") else None
    held = holders(lanes)
    retries = retries or {}
    max_retries = int(cfg.get("max_retries", 2))

    def reason(it: Item) -> str | None:
        if it.space not in executable:
            return "not executable"
        if it.space not in sprints:
            return f"no active sprint in {it.space}"
        if it.kind == "epic":
            return "an epic is never lane work"
        why = blocker_reason(it, items, blockers, gone)
        if why:
            return why
        if it.id in held:
            return f"held by {held[it.id]}"
        if int(retries.get(it.id, 0)) >= max_retries:
            return f"held after {int(retries.get(it.id, 0))} retries (cap {max_retries})"
        if blocking & set(it.labels):
            return f"label {', '.join(sorted(blocking & set(it.labels)))}"
        why = parked_reason(it, items, parked)
        if why:
            return why
        if title_rx and title_rx.search(it.title):
            return "excluded by the instance config (title)"
        if not readyset.bind(it, spaces_cfg.get(it.space, {}), visibility, key_re):
            return "project does not resolve"
        return None

    admitted: list[Item] = []
    excluded: dict[str, str] = {}
    for it in items.values():
        if it.status not in ready_statuses:
            continue
        why = reason(it)
        if why:
            excluded[it.id] = why
        else:
            admitted.append(it)
    admitted.sort(key=lambda i: i.order)
    orphans = sorted(i.id for i in items.values()
                     if i.space in executable and i.status == "IN PROGRESS" and i.kind != "epic" and i.id not in held)
    ordered, ignored = apply_planner(admitted, excluded, planner_order)
    return Admission(ordered, excluded, orphans, ignored)
