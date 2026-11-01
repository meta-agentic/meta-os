"""A finding, which classes the baseline may silence, and the baseline file itself.

Split out of `validate_framework.py`; the ratchet it describes is explained there.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "scripts" / "framework-baseline.txt"

# Which classes may be silenced by the baseline. `public-safety` may not: a
# public-repo leak is the one failure mode with no undo, so it fails the gate on
# sight and its findings are never written to a committed file (that file would
# then carry the very string being flagged).
BASELINEABLE = {
    "skill-provenance": True,
    "skill-index": True,
    "index-phantom": True,
    "index-pack-table": True,
    # An unreadable registry is not debt anyone should accept: it switches the check off.
    "pack-registry": False,
    "systems-front-matter": True,
    "folder-index": True,
    "count-assertion": True,
    "public-safety": False,
    # The framework tracking an instance path is the one way an upgrade can collide
    # with an instance's files. Structural, so never tolerated as debt.
    "instance-path-tracked": False,
}


class Finding:
    __slots__ = ("check", "path", "detail")

    def __init__(self, check: str, path: str, detail: str):
        self.check, self.path, self.detail = check, path, detail

    @property
    def key(self) -> str:
        """Stable, greppable identity used by the baseline file."""
        return f"{self.check}\t{self.path}\t{self.detail}"

    def __str__(self) -> str:
        return f"{self.path}: {self.detail}  [{self.check}]"


def read_baseline() -> set[str]:
    if not BASELINE.is_file():
        return set()
    return {ln.rstrip("\n") for ln in BASELINE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")}


def write_baseline(findings: list[Finding]) -> int:
    keys = sorted({f.key for f in findings if BASELINEABLE.get(f.check, False)})
    header = (
        "# meta-os framework self-check — accepted debt (the ratchet).\n"
        "#\n"
        "# Each line is one KNOWN violation, recorded so it warns instead of failing\n"
        "# the gate. A violation NOT listed here is an error: debt can be paid down,\n"
        "# never grown. Removing a line is how debt gets retired — do that in the same\n"
        "# commit that fixes it. Regenerate with:\n"
        "#     python3 scripts/validate_framework.py --update-baseline\n"
        "# Format: <check>\\t<path>\\t<detail>\n"
        "# public-safety findings are never recorded here — see BASELINEABLE.\n"
    )
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(header + "\n".join(keys) + "\n", encoding="utf-8")
    return len(keys)

