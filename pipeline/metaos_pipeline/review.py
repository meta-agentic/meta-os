"""The review station's disciplines: the queue oldest first, the review-age SLA, the auto-merge tier.

* **Queue.** Every item `IN REVIEW` in the pipeline's spaces, oldest first, aged from the vault
  commit that set its status (the file's mtime when the vault is not a git repository or the
  file has uncommitted changes).
* **SLA.** `review_age_max_days` per space is the age of its oldest item in review; a space over
  `swarm.review_sla_days` takes no new work until it recovers.
* **Auto-merge tier.** A PR the pipeline opened merges without the human station only when every
  guard in `decide` passes; the classes come from `swarm.automerge_classes`, empty by default, and
  an empty or malformed list never asks GitHub anything. This is the one place the pipeline
  merges, so every doubt refuses: an unknown class, a check that is not `SUCCESS`, no checks at
  all, a draft, a `human-judgement` label on the PR or the item, a head that moved since it was
  read (`--match-head-commit`).
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import subprocess
from dataclasses import dataclass
from typing import Callable

from .readyset import front_matter

DAY = 86400.0
SLA_DAYS = 5
IN_REVIEW = "IN REVIEW"
HUMAN_FLAG = "human-judgement"
TIERS = ("raw", "wiki", "output")


# ---------------------------------------------------------------- queue and SLA
@dataclass(frozen=True)
class Waiting:
    id: str
    space: str
    title: str
    since: float
    days: int
    source: str  # "git" or "mtime"


def _dirty(vault: str) -> set[str] | None:
    """Real paths with uncommitted changes or untracked; None when the vault is not in a git repository."""
    top = subprocess.run(["git", "-C", vault, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=60)
    r = subprocess.run(["git", "-C", vault, "status", "--porcelain", "--no-renames", "--untracked-files=all", "-z"],
                       capture_output=True, text=True, timeout=60)
    if top.returncode != 0 or r.returncode != 0:
        return None
    root = top.stdout.strip()
    return {os.path.realpath(os.path.join(root, e[3:])) for e in r.stdout.split("\0") if len(e) > 3}


def entered_review(vault: str, path: str, dirty: set[str] | None) -> tuple[float, str]:
    """When the item's status became IN REVIEW: the last commit adding or removing that line."""
    if dirty is not None and os.path.realpath(path) not in dirty:
        rel = os.path.relpath(path, vault)
        r = subprocess.run(["git", "-C", vault, "log", "-1", "--format=%ct", "-G", f"^status: {IN_REVIEW}$", "--", rel],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            return float(r.stdout.strip()), "git"
    return os.stat(path).st_mtime, "mtime"


def queue(vault: str, spaces: list[str], now: float) -> list[Waiting]:
    """The items in review in these spaces, oldest first."""
    dirty = _dirty(vault)
    out: list[Waiting] = []
    for space in spaces:
        for tier in TIERS:
            for path in glob.glob(os.path.join(glob.escape(vault), glob.escape(space), tier, "*.md")):
                fm = front_matter(path)
                if fm.get("status") != IN_REVIEW or not fm.get("id"):
                    continue
                since, source = entered_review(vault, path, dirty)
                out.append(Waiting(str(fm["id"]), space, str(fm.get("title") or ""), since,
                                   max(0, int((now - since) // DAY)), source))
    return sorted(out, key=lambda w: (w.since, w.id))


def age_max_days(rows: list[Waiting], spaces: list[str]) -> dict[str, int]:
    """`review_age_max_days` per space: the age of its oldest item in review, 0 when none waits."""
    return {s: max((w.days for w in rows if w.space == s), default=0) for s in spaces}


def over_sla(rows: list[Waiting], sla_days: float) -> dict[str, str]:
    """The spaces whose oldest item in review is older than the limit, each with its reason."""
    out: dict[str, str] = {}
    for w in rows:  # oldest first: the first row of a space is its oldest
        if w.space not in out and w.days > sla_days:
            out[w.space] = f"review age {w.days} d over the SLA of {sla_days:g} d (oldest in review: {w.id})"
    return out


# ---------------------------------------------------------------- auto-merge tier
def _docs_only(path: str) -> bool:
    parts = path.split("/")
    return (os.path.splitext(path)[1].lower() in (".md", ".markdown", ".rst", ".txt")
            and parts[-1] not in ("CLAUDE.md", "AGENTS.md", "SKILL.md")
            and not {".github", ".claude"} & set(parts[:-1]))


def _tests_only(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    return (bool({"tests", "test", "__tests__"} & set(parts[:-1]))
            or (name.startswith("test_") and name.endswith(".py"))
            or ".test." in name or ".spec." in name or os.path.splitext(name)[0].endswith("_test"))


# A class merges only through a classifier here; a configured name without one never matches.
CLASSES: dict[str, Callable[[str], bool]] = {"docs-only": _docs_only, "tests-only": _tests_only}


@dataclass(frozen=True)
class Decision:
    merge: bool
    reason: str
    cls: str | None = None


def enabled(classes) -> bool:
    return isinstance(classes, list) and bool(classes) and all(isinstance(c, str) for c in classes)


def _check_name(c: dict) -> str:
    return str(c.get("name") or c.get("context") or "?")


def decide(pr: dict, classes, item_labels=()) -> Decision:
    """Merge or not, and why. Every guard refuses; only a PR past all of them merges."""
    if not enabled(classes):
        return Decision(False, "auto-merge is off: swarm.automerge_classes is empty or not a list of class names")
    if pr.get("state") != "OPEN":
        return Decision(False, f"the PR is {pr.get('state') or 'in an unknown state'}, not open")
    if pr.get("isDraft") is not False:
        return Decision(False, "the PR is a draft")
    labels = {str(l.get("name") if isinstance(l, dict) else l) for l in pr.get("labels") or []}
    if HUMAN_FLAG in labels or HUMAN_FLAG in set(item_labels or ()):
        return Decision(False, f"{HUMAN_FLAG} is set on the PR or the item")
    files = [str(f.get("path") if isinstance(f, dict) else f) for f in pr.get("files") or []]
    if not files:
        return Decision(False, "the PR lists no changed files")
    cls = next((c for c in classes if c in CLASSES and all(CLASSES[c](p) for p in files)), None)
    if cls is None:
        return Decision(False, "outside the auto-merge classes " + ", ".join(classes))
    checks = pr.get("statusCheckRollup") or []
    if not checks:
        return Decision(False, "no checks reported: nothing proves the PR green")
    red = [_check_name(c) for c in checks if (c.get("conclusion") or c.get("state")) != "SUCCESS"]
    if red:
        return Decision(False, "checks not green: " + ", ".join(red))
    if pr.get("mergeable") != "MERGEABLE":
        return Decision(False, f"GitHub reports the PR {pr.get('mergeable') or 'UNKNOWN'}, not mergeable")
    if not pr.get("headRefOid"):
        return Decision(False, "no head commit to pin the merge to")
    return Decision(True, f"{cls}, every check green", cls)


class GhError(RuntimeError):
    pass


class GhCli:
    """The GitHub port over the `gh` CLI, the instance's credentials."""

    FIELDS = "state,isDraft,labels,files,statusCheckRollup,mergeable,headRefOid"

    def _gh(self, *args: str) -> str:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise GhError((r.stderr or r.stdout).strip()[-300:])
        return r.stdout

    def view(self, repo: str, number: int) -> dict:
        return json.loads(self._gh("pr", "view", str(number), "--repo", repo, "--json", self.FIELDS))

    def merge(self, repo: str, number: int, sha: str) -> None:
        self._gh("pr", "merge", str(number), "--repo", repo, "--squash", "--match-head-commit", sha)


def github() -> GhCli:
    return GhCli()


def register(state: dict, item: str, pr, repo: str, now: float) -> None:
    """Put a PR the pipeline opened in the review map the tier reads; one it could not merge is left out."""
    if isinstance(pr, dict) and isinstance(pr.get("number"), int) and repo:
        state.setdefault("review", {})[item] = {"repo": repo, "number": pr["number"], "url": pr.get("url"), "since": now}


def automerge(state: dict, classes, *, vault_status: Callable[[str], str | None], item_labels: Callable[[str], list],
              transition: Callable[[str, str], tuple[int, str]], emit: Callable[..., None]) -> list[str]:
    """One pass of the tier over the review map, oldest first; the transitions it made."""
    pending = state.get("review") or {}
    done: list[str] = []
    for item in sorted(pending, key=lambda k: (pending[k].get("since") or 0, k)):
        entry = pending[item]
        status = vault_status(item)
        if status != IN_REVIEW and not entry.get("merged"):
            emit("review_left", item=item, status=status, pr=entry.get("url"))
            del pending[item]
            continue
        if not enabled(classes):
            continue  # off: GitHub is never asked
        if not entry.get("merged"):
            try:
                pr = github().view(entry["repo"], entry["number"])
            except (GhError, ValueError, OSError, subprocess.SubprocessError) as exc:
                emit("automerge_refused", item=item, pr=entry.get("url"), reason=f"could not read the PR: {exc}")
                continue
            if pr.get("state") in ("MERGED", "CLOSED"):
                emit("review_left", item=item, status=status, pr=entry.get("url"), pr_state=pr.get("state"))
                del pending[item]
                continue
            d = decide(pr, classes, item_labels(item))
            if not d.merge:
                if entry.get("refused") != d.reason:  # one event per reason, not one per pass
                    emit("automerge_refused", item=item, pr=entry.get("url"), reason=d.reason)
                    entry["refused"] = d.reason
                continue
            try:
                github().merge(entry["repo"], entry["number"], pr["headRefOid"])
            except (GhError, OSError, subprocess.SubprocessError) as exc:
                emit("automerge_failed", item=item, pr=entry.get("url"), reason=str(exc))
                continue
            entry.update(merged=True, cls=d.cls, sha=pr["headRefOid"])
            emit("automerged", item=item, pr=entry.get("url"), cls=d.cls, sha=pr["headRefOid"])
        rc, msg = transition(item, "DONE")
        emit("transition", item=item, to="DONE", rc=rc, msg=msg[-200:], by="automerge")
        if rc == 0:  # a failed transition is retried next pass; the merge is not repeated
            done.append(f"{item} → DONE (auto-merged, {entry.get('cls')}: PR {entry.get('url')})")
            del pending[item]
    return done


def weekly_q(events: list[dict]) -> list[tuple[str, int, int, float]]:
    """(ISO week, PRs that entered review, of those auto-merged, q) per week, oldest first."""
    merged = {e.get("pr") for e in events if e.get("kind") == "automerged"}
    weeks: dict[str, list[int]] = {}
    for e in events:
        if e.get("kind") == "transition" and e.get("to") == IN_REVIEW and e.get("rc") == 0 and e.get("pr"):
            y, w, _ = dt.datetime.fromtimestamp(float(e["ts"]), dt.timezone.utc).isocalendar()
            n = weeks.setdefault(f"{y}-W{w:02d}", [0, 0])
            n[0] += 1
            n[1] += e["pr"] in merged
    return [(k, n, a, round(a / n, 2)) for k, (n, a) in sorted(weeks.items())]
