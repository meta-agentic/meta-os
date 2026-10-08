#!/usr/bin/env python3
"""Run every test suite in this repository: the one command CI runs and a contributor runs.

A suite is a directory holding a `test_*.py` (unittest's default pattern) that git tracks
or would track (untracked but not ignored). Suites are found, not registered, so a new one
is in CI the moment it is committed; a suite that CI never runs decays unseen, which is
how the pipeline's own suite sat outside the build.

Each suite runs in its own interpreter (`python -m unittest discover -s <dir>`) because
suites put different directories on `sys.path` and must not shadow each other's modules.
Anything under a `fixtures/` directory is test data, never a suite.

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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-v", "--verbose", action="store_true", help="name each test case")
    ap.add_argument("--list", action="store_true", help="print the suites and exit")
    a = ap.parse_args(argv)

    found = suites()
    if not found:
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
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
