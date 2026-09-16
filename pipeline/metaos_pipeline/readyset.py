"""Ready set and lane assignment.

An item is *ready* when: it lives in an executable space with an active sprint, its status is
one of the configured ready statuses, it is not an epic, every dependency is DONE, and it
carries no blocking marker. Assignment applies the swarm harness's one rule as a heuristic:
two ready items with the same (space, repo, primary tag) are the same lane, sequential — so at
most one of them may be in flight at a time.
"""
from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass, field
from typing import Iterable

try:
    import yaml  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required (pip install pyyaml)") from exc

FRONT = re.compile(r"^---\n(.*?)\n---", re.S)
TAG = re.compile(r"^\s*'?\[([A-Z][A-Z0-9-]*)\]")


@dataclass
class Item:
    id: str
    space: str
    kind: str
    status: str
    title: str
    points: float
    priority: str
    labels: list[str]
    dependencies: list[str]
    committed: bool
    path: str
    primary_tag: str = ""
    repo: str = ""
    branch: str = ""
    order: tuple = field(default_factory=tuple)


def front_matter(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = FRONT.match(text)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def active_sprints(vault: str) -> dict[str, dict]:
    """space -> {sprintId, committed[]} for every space with a `state: active` sprint file."""
    out: dict[str, dict] = {}
    for path in glob.glob(os.path.join(vault, "*", "sprints", "*.md")):
        fm = front_matter(path)
        if fm.get("state") == "active":
            space = os.path.basename(os.path.dirname(os.path.dirname(path)))
            out[space] = {
                "sprintId": fm.get("sprintId") or os.path.basename(path)[:-3],
                "committed": [str(k) for k in (fm.get("committed") or [])],
            }
    return out


def load_items(vault: str, spaces: Iterable[str]) -> dict[str, Item]:
    items: dict[str, Item] = {}
    sprints = active_sprints(vault)
    for space in spaces:
        committed = set(sprints.get(space, {}).get("committed", []))
        for tier in ("raw", "wiki", "output"):
            for path in glob.glob(os.path.join(vault, space, tier, "*.md")):
                if path.endswith("_index.md"):
                    continue
                fm = front_matter(path)
                if not fm.get("id") or fm.get("kind") in (None, "adr", "sprint"):
                    continue
                title = str(fm.get("title") or "")
                tag = TAG.match(title)
                pts = fm.get("storyPoints")
                items[str(fm["id"])] = Item(
                    id=str(fm["id"]),
                    space=space,
                    kind=str(fm.get("kind")),
                    status=str(fm.get("status") or ""),
                    title=title,
                    points=float(pts) if isinstance(pts, (int, float)) else 0.0,
                    priority=str(fm.get("priority") or "P9"),
                    labels=[str(x) for x in (fm.get("labels") or [])],
                    dependencies=[str(x) for x in (fm.get("dependencies") or [])],
                    committed=str(fm["id"]) in committed,
                    path=path,
                    primary_tag=tag.group(1) if tag else "",
                )
    return items


def resolve_repo(item: Item, space_cfg: dict) -> str:
    """Pick the repository a lane for this item works in.

    `space_cfg["repo_by_tag"]` maps a primary title tag (e.g. INF, SPA) to a repository;
    `space_cfg["repo_by_label"]` maps a label to one; `space_cfg["repo"]` is the default.
    """
    by_tag = space_cfg.get("repo_by_tag") or {}
    if item.primary_tag in by_tag:
        return by_tag[item.primary_tag]
    by_label = space_cfg.get("repo_by_label") or {}
    for label in item.labels:
        if label in by_label:
            return by_label[label]
    return space_cfg.get("repo", "")


def slug(title: str, n: int = 4) -> str:
    words = re.findall(r"[a-z0-9]+", re.sub(r"^\s*'?(\[[A-Z0-9-]+\]\s*)+", "", title.lower()))
    return "-".join(words[:n]) or "item"


def ready_items(vault: str, cfg: dict) -> list[Item]:
    """Ordered ready set: committed-to-sprint first, then priority, then points ascending."""
    spaces_cfg: dict = cfg.get("spaces") or {}
    executable = [s for s, c in spaces_cfg.items() if c.get("executable", True)]
    sprints = active_sprints(vault)
    items = load_items(vault, executable)
    ready_statuses = set(cfg.get("ready_statuses") or ["REFINED"])
    blockers = set(cfg.get("blocking_labels") or ["blocked", "needs-po"])
    exclude_title = re.compile(cfg["exclude_title_regex"]) if cfg.get("exclude_title_regex") else None
    out: list[Item] = []
    for it in items.values():
        if it.space not in sprints or it.kind == "epic" or it.status not in ready_statuses:
            continue
        if blockers & set(it.labels):
            continue
        if exclude_title and exclude_title.search(it.title):
            continue
        if any(items.get(d, Item(d, "", "", "", "", 0, "", [], [], False, "")).status != "DONE" for d in it.dependencies):
            continue
        scfg = spaces_cfg.get(it.space, {})
        it.repo = resolve_repo(it, scfg)
        if not it.repo:
            continue
        # A public repository must not carry tracker ids in branch names, commits or PRs
        # (the framework's public-safety rule); the lane prompt says the same.
        prefix = scfg.get("branch_prefix", it.space.upper() + "/")
        it.branch = f"{prefix}{slug(it.title, 5)}" if scfg.get("public") else f"{prefix}{it.id}-{slug(it.title)}"
        it.order = (0 if it.committed else 1, it.priority, it.points, it.id)
        out.append(it)
    out.sort(key=lambda i: i.order)
    return out


def in_flight_keys(lanes: Iterable[dict]) -> set[tuple[str, str, str]]:
    return {(l["space"], l["repo"], l.get("primary_tag", "")) for l in lanes if l.get("status") in ("running", "spawning")}


def assign(ready: list[Item], lanes: list[dict], free_tokens: int, cfg: dict,
           paused_spaces: Iterable[str] = ()) -> list[Item]:
    """Choose which ready items start now.

    Constraints, in order: free tokens; the one rule (same space+repo+primary tag as a
    running lane, or as an item already chosen, waits); the fairness cap (no space may hold
    more than `fairness_share` of the total tokens); paused spaces are skipped.
    """
    if free_tokens <= 0:
        return []
    total = int(cfg.get("regulator", {}).get("N", 0)) or (free_tokens + len([l for l in lanes if l.get("status") in ("running", "spawning")]))
    share = float(cfg.get("fairness_share", 0.5))
    cap_per_space = max(1, int(total * share + 1e-9))
    held: dict[str, int] = {}
    for l in lanes:
        if l.get("status") in ("running", "spawning"):
            held[l["space"]] = held.get(l["space"], 0) + 1
    busy = in_flight_keys(lanes)
    paused = set(paused_spaces)
    chosen: list[Item] = []
    for it in ready:
        if len(chosen) >= free_tokens:
            break
        if it.space in paused:
            continue
        key = (it.space, it.repo, it.primary_tag)
        if key in busy:
            continue
        if held.get(it.space, 0) >= cap_per_space:
            continue
        chosen.append(it)
        busy.add(key)
        held[it.space] = held.get(it.space, 0) + 1
    return chosen
