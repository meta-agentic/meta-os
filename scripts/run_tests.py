#!/usr/bin/env python3
"""Run every test suite in this repository: the one command CI runs and a contributor runs.

A suite is a directory holding a `test_*.py` (unittest's default pattern) that git tracks
or would track (untracked but not ignored). Suites are found, not registered, so a new one
is in CI the moment it is committed; a suite that CI never runs decays unseen, which is
how the pipeline's own suite sat outside the build.

Each suite runs in its own interpreter (`python -m unittest discover -s <dir>`) because
suites put different directories on `sys.path` and must not shadow each other's modules.
Anything under a `fixtures/` directory is test data, never a suite.

Inside an instance (its `.claude/CLAUDE.md` tracked) only the instance's own suites run:
a suite in a folder the framework tracks (`tests/`, `pipeline/tests/`) is skipped, with
one line saying so. Those suites build their fixtures from the working tree, which in an
instance holds the instance's files too; they run in the framework's own CI, and the gate
checks the instance has not edited a framework path. "The framework's folders" is read
exactly as the gate reads it, by `validate_framework.framework_scope()` (the tree at the
merge base with `upstream/main`, which `scripts/ci_framework_ref.py` provides in CI). If
no framework ref resolves, nothing is skipped: running too much is the safe failure.

    python3 scripts/run_tests.py          # every suite; exit 1 if any fails
    python3 scripts/run_tests.py -v       # with each case named
    python3 scripts/run_tests.py --list   # the suites, one per line, without running them
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def suites(root: Path = ROOT) -> list[str]:
    """Repository-relative directories that hold a test_*.py git tracks or would track, sorted."""
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard",
         "--", "*test_*.py"],
        check=True, capture_output=True, text=True,
    ).stdout
    found = set()
    for path in filter(None, out.split("\0")):
        p = Path(path)
        if p.name.startswith("test_") and "fixtures" not in p.parts:
            found.add(p.parent.as_posix())
    return sorted(found)


def framework_suites(found: list[str]) -> tuple[list[str], str]:
    """The suites in folders the framework tracks, and the framework commit, in an instance.

    ([], "") in the framework repository, and whenever the gate's scope cannot be read.
    """
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from validate_framework import framework_scope
        scope = framework_scope()
    except (ImportError, SystemExit):   # no gate here, or its dependencies missing
        return [], ""
    finally:
        sys.path.pop(0)
    if scope is None:
        return [], ""
    ref, _, folders = scope
    return [s for s in found if s in folders], ref


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-v", "--verbose", action="store_true", help="name each test case")
    ap.add_argument("--list", action="store_true", help="print the suites and exit")
    a = ap.parse_args(argv)

    found = suites()
    skipped, ref = framework_suites(found)
    if skipped:
        print(f"run_tests: skipped the framework's suites {', '.join(skipped)} (framework at {ref}): "
              "framework suites run in the framework's CI; integrity is checked by the gate",
              file=sys.stderr)
        found = [s for s in found if s not in skipped]
    if not found and not skipped:
        # A runner that finds nothing is broken, not green.
        print("run_tests: no test suite found (no test_*.py outside fixtures/)", file=sys.stderr)
        return 1
    if a.list:
        print("\n".join(found))
        return 0

    results = []
    for suite in found:
        print(f"\n=== {suite}", flush=True)
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", suite]
        if a.verbose:
            cmd.append("-v")
        results.append((suite, subprocess.run(cmd, cwd=ROOT).returncode))

    failed = [s for s, rc in results if rc != 0]
    print("\n" + "\n".join(f"{'FAIL' if rc else 'ok  '}  {s}" for s, rc in results))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Test suites\n\n| Suite | Result |\n|---|---|\n")
            fh.writelines(f"| `{s}` | {'failed' if rc else 'passed'} |\n" for s, rc in results)
            fh.writelines(f"| `{s}` | skipped (the framework's suite) |\n" for s in skipped)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
