#!/usr/bin/env python3
"""Run every test suite in this repository: the one command CI runs and a contributor runs.

A suite is a directory holding a `test_*.py` (unittest's default pattern) that git tracks
or would track (untracked but not ignored). Suites are found, not registered, so a new one
is in CI the moment it is committed; a suite that CI never runs decays unseen, which is
how the pipeline's own suite sat outside the build.

Each suite runs in its own interpreter (`python -m unittest discover -s <dir>`) because
suites put different directories on `sys.path` and must not shadow each other's modules.
Anything under a `fixtures/` directory is test data, never a suite.

Inside an instance (its `.claude/CLAUDE.md` tracked) only the instance's own tests run:
a test file the framework tracks is skipped, and a suite made only of such files
(`tests/`, `pipeline/tests/`) is skipped whole, with one line saying so. A test file the
instance added runs even inside a framework folder, on its own. Those suites build their fixtures from the working tree, which in an
instance holds the instance's files too; they run in the framework's own CI, and the gate
checks the instance has not edited a framework path. "The framework's folders" is read
exactly as the gate reads it, by `validate_framework.framework_scope()` (the tree at the
merge base with `upstream/main`, which `scripts/ci_framework_ref.py` provides in CI). If
no framework ref resolves, nothing is skipped: running too much is the safe failure. In
the framework repository itself nothing is ever skipped, even if it wrongly tracks an
instance path: the gate refuses to narrow there (see `framework_scope()`).

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


def test_files(root: Path = ROOT) -> dict[str, list[str]]:
    """Each suite (a directory holding a test_*.py git tracks or would track) -> its test files."""
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard",
         "--", "*test_*.py"],
        check=True, capture_output=True, text=True,
    ).stdout
    found: dict[str, list[str]] = {}
    for path in filter(None, out.split("\0")):
        p = Path(path)
        if p.name.startswith("test_") and "fixtures" not in p.parts:
            found.setdefault(p.parent.as_posix(), []).append(p.as_posix())
    return {d: sorted(found[d]) for d in sorted(found)}


def suites(root: Path = ROOT) -> list[str]:
    """Repository-relative directories that hold a test_*.py git tracks or would track, sorted."""
    return list(test_files(root))


def framework_files() -> tuple[frozenset[str], str] | None:
    """In an instance: the files the framework tracks, and its commit, as the gate reads them.

    None in the framework repository, and whenever the gate's scope cannot be read.
    """
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from validate_framework import framework_scope
        scope = framework_scope()
    except (ImportError, SystemExit):   # no gate here, or its dependencies missing
        return None
    finally:
        sys.path.pop(0)
    return None if scope is None else (scope[1], scope[0])


def plan(files: dict[str, list[str]]) -> tuple[list[tuple[str, str | None]], list[str], str]:
    """(runs, skipped, framework commit). A run is (label, None) for a whole suite, or
    (label, file name) for an instance's own file in a folder that also holds the
    framework's: a test file is skipped only if the framework tracks that very file."""
    scope = framework_files()
    if scope is None:
        return [(d, None) for d in files], [], ""
    tracked, ref = scope
    runs: list[tuple[str, str | None]] = []
    skipped: list[str] = []
    for suite, names in files.items():
        own = [f for f in names if f not in tracked]
        if len(own) == len(names):
            runs.append((suite, None))
        elif not own:
            skipped.append(suite)
        else:
            skipped.append(f"{suite} (its framework files)")
            runs += [(f, Path(f).name) for f in own]
    return runs, skipped, ref


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-v", "--verbose", action="store_true", help="name each test case")
    ap.add_argument("--list", action="store_true", help="print the suites and exit")
    a = ap.parse_args(argv)

    runs, skipped, ref = plan(test_files())
    if skipped:
        print(f"run_tests: skipped the framework's suites {', '.join(skipped)} (framework at {ref}): "
              "framework suites run in the framework's CI; integrity is checked by the gate",
              file=sys.stderr)
    if not runs and not skipped:
        # A runner that finds nothing is broken, not green.
        print("run_tests: no test suite found (no test_*.py outside fixtures/)", file=sys.stderr)
        return 1
    if a.list:
        print("\n".join(label for label, _ in runs))
        return 0

    results = []
    for label, name in runs:
        print(f"\n=== {label}", flush=True)
        suite = label if name is None else Path(label).parent.as_posix()
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", suite]
        if name is not None:
            cmd += ["-p", name]
        if a.verbose:
            cmd.append("-v")
        results.append((label, subprocess.run(cmd, cwd=ROOT).returncode))

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
