"""Which paths the framework gate judges: the instance paths, and the framework's own scope.

Split out of `validate_framework.py`, which owns the checks and the report. A checkout is
the framework itself or a bootstrapped instance of it; this module answers which, and which
tracked files are the framework's to judge (see the module docstring there).
"""
from __future__ import annotations

import functools
import os
import subprocess
from pathlib import Path

from framework_findings import Finding

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Instance paths — derived, not declared. Every top-level entry of the instance
# template's payload lands at the same path under the repository root when an
# instance is bootstrapped, and from then on that path is the instance's. The
# framework may not track one; the gate may not judge one. Two paths the payload
# does not carry but the mount mechanism creates are added explicitly: the pack
# mounts and the submodule manifest `git submodule add` writes.
# ---------------------------------------------------------------------------
INSTANCE_TEMPLATE_ROOT = ROOT / "instance-template" / "root"
INSTANCE_ONLY_EXTRA = frozenset({".packs", ".gitmodules"})


def instance_paths() -> frozenset[str]:
    """Top-level names owned by an instance: the payload's entries plus the mounts."""
    names = set(INSTANCE_ONLY_EXTRA)
    if INSTANCE_TEMPLATE_ROOT.is_dir():
        names.update(p.name for p in INSTANCE_TEMPLATE_ROOT.iterdir())
    return frozenset(names)


def is_instance_path(rel: Path) -> bool:
    return bool(rel.parts) and rel.parts[0] in instance_paths()

# A bootstrapped checkout carries the instance contract; the framework repository
# never does. In instance mode the checks that cannot tell a framework skill from
# the instance's own are narrowed to what the catalog declares (see
# check_skill_registration) and the count assertion is skipped.
def instance_mode() -> bool:
    return (ROOT / ".claude" / "CLAUDE.md").is_file()


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                              check=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def is_own_framework() -> bool:
    """Is this checkout the framework repository itself, whatever it tracks?

    True when `origin` is the canonical framework, or when `upstream` is the same repository
    as `origin`. A clone of a local copy (`file://` or a path) is the second case only once someone
    says so with `git remote add upstream "$(git remote get-url origin)"`: it cannot be told apart
    from an instance cloned from that copy (see scripts/ci_framework_ref.py).

    A change to the framework that tracks `.claude/CLAUDE.md` must not turn its own gate into an
    instance's: scoped to `main`, every file the change adds would escape it.
    """
    from ci_framework_ref import CANONICAL_URL, normalise_url
    origin = _git("remote", "get-url", "origin")
    if origin is None:
        return False
    upstream = _git("remote", "get-url", "upstream")
    mine = normalise_url(origin)
    return mine == normalise_url(CANONICAL_URL) or (upstream is not None and mine == normalise_url(upstream))


def own_framework_tracking_contract() -> bool:
    """The framework repository itself, with `.claude/CLAUDE.md` tracked: never an instance."""
    return (_git("ls-files", "--error-unmatch", ".claude/CLAUDE.md") is not None
            and is_own_framework())


@functools.lru_cache(maxsize=None)
def framework_scope() -> tuple[str, frozenset[str], frozenset[str]] | None:
    """In an instance: (ref, files, folders) the framework tracks at the last merged commit.

    None outside an instance (everything tracked is the framework's) and when no
    framework ref is reachable (the template-derived fallback applies). An instance
    COMMITS its contract; a framework developer's checkout (`bootstrap.sh --local`)
    only has it on disk, excluded — and must keep the full scope, or a file added on
    a branch there would escape the gate whenever an `upstream` remote exists.
    """
    if not instance_mode() or _git("ls-files", "--error-unmatch", ".claude/CLAUDE.md") is None:
        return None
    if is_own_framework():
        return None
    # An override can only widen the scope: the merge base with upstream/main still counts,
    # so a stale $META_OS_FRAMEWORK_REF cannot hide a file the framework added since.
    refs = dict.fromkeys(r for r in (os.environ.get("META_OS_FRAMEWORK_REF"), "upstream/main") if r)
    bases = [b.strip() for b in (_git("merge-base", "HEAD", r) for r in refs) if b]
    names: set[str] = set()
    for base in bases:
        names.update(n for n in (_git("ls-tree", "-r", "-z", "--name-only", base) or "").split("\0") if n)
    if not names:
        return None
    files = frozenset(names)
    folders = frozenset("/".join(Path(n).parts[:i]) for n in files
                        for i in range(1, len(Path(n).parts)))
    return " + ".join(b[:12] for b in dict.fromkeys(bases)), files, folders


def tracked_files() -> list[Path]:
    """Files git tracks — the scan is about what this repo PUBLISHES.

    Untracked and gitignored tool state (`.claude-flow/` session logs, IDE
    workspace files) is full of id-shaped strings and is never published, so
    asking git is both the correct scope and the cheap one. Outside a work tree
    the walk falls back to the tree minus every dot-directory, which is the same
    scope approximately.
    """
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                             capture_output=True, check=True).stdout
        files = [ROOT / n for n in out.decode("utf-8").split("\0") if n]
    except (OSError, subprocess.CalledProcessError):
        files = [p for p in ROOT.rglob("*")
                 if p.is_file()
                 and not any(part.startswith(".") for part in p.relative_to(ROOT).parts[:-1])]
    # An instance's own files are not the framework's to scan (and in the framework
    # repository the layout check below is what catches one being tracked at all).
    scope = framework_scope()
    if scope:
        return [p for p in files if p.relative_to(ROOT).as_posix() in scope[1]]
    return [p for p in files if not is_instance_path(p.relative_to(ROOT))]


def tracked_instance_paths() -> list[str]:
    """Tracked paths that sit at an instance path — must be empty in the framework."""
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return sorted(n for n in out.decode("utf-8").split("\0")
                  if n and is_instance_path(Path(n)))


def check_instance_paths_untracked(findings: list[Finding]) -> None:
    """7. The framework tracks no file at an instance path.

    The one-repository layout works only because the two owners' path sets are
    disjoint: an upgrade is a merge of the framework's paths, and a merge cannot
    touch a path the framework never tracks. This is the check that keeps the
    sets disjoint. Skipped in an instance, where those paths are exactly what is
    tracked, but not in the framework repository itself when it tracks the instance
    contract: that is the very path this check exists to refuse.
    """
    if instance_mode() and not own_framework_tracking_contract():
        return
    for n in tracked_instance_paths():
        findings.append(Finding(
            "instance-path-tracked", n,
            f"tracked at an instance path ({Path(n).parts[0]!r} is instantiated from "
            f"instance-template/root/ and belongs to the instance from then on)"))
