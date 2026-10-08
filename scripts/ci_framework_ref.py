#!/usr/bin/env python3
"""Give a CI checkout of an instance the framework ref its gate scopes itself by.

    python3 scripts/ci_framework_ref.py            # what .github/workflows/check.yml runs
    python3 scripts/ci_framework_ref.py --url URL  # a framework other than the canonical one

Inside an instance, `scripts/validate_framework.py` judges only the paths the framework
tracks at the commit last merged: the merge base of `HEAD` with `upstream/main`. A
developer's clone has that remote (`scripts/bootstrap.sh` sets it). A CI checkout has
neither the remote nor the history, since `actions/checkout` fetches one commit, so the
gate fell back to approximating the scope and judged the instance's own files as the
framework's. This prepares the checkout the way a clone already is:

  * the framework repository itself (no tracked `.claude/CLAUDE.md`): nothing to do,
    and nothing is fetched;
  * an instance: a shallow checkout is deepened to its full history, an `upstream`
    remote is added (an existing one is kept as it is), its `main` is fetched, and the
    merge base with `HEAD` must resolve. If it does not, this fails rather than letting
    the gate run on a guessed scope.

The URL is `--url`, else `$META_OS_UPSTREAM_URL`, else the canonical framework.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANONICAL_URL = "https://github.com/meta-agentic/meta-os.git"
REMOTE, BRANCH = "upstream", "main"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                          check=check)


def is_instance() -> bool:
    """An instance commits its contract; the framework (and a developer checkout) never does."""
    return git("ls-files", "--error-unmatch", ".claude/CLAUDE.md", check=False).returncode == 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default=os.environ.get("META_OS_UPSTREAM_URL") or CANONICAL_URL,
                    help="the framework repository (default: $META_OS_UPSTREAM_URL, else the canonical one)")
    a = ap.parse_args(argv)

    if not is_instance():
        print("ci_framework_ref: the framework repository itself — the gate's scope needs no ref")
        return 0

    try:
        if git("rev-parse", "--is-shallow-repository").stdout.strip() == "true":
            print("ci_framework_ref: deepening the shallow checkout to its full history")
            git("fetch", "--quiet", "--unshallow", "--no-tags", "origin")
        if REMOTE in git("remote").stdout.split():
            print(f"ci_framework_ref: keeping the existing '{REMOTE}' remote "
                  f"({git('remote', 'get-url', REMOTE).stdout.strip()})")
        else:
            git("remote", "add", REMOTE, a.url)
            print(f"ci_framework_ref: added '{REMOTE}' -> {a.url}")
        git("fetch", "--quiet", "--no-tags", REMOTE,
            f"+refs/heads/{BRANCH}:refs/remotes/{REMOTE}/{BRANCH}")
    except subprocess.CalledProcessError as e:
        print(f"ci_framework_ref: `git {' '.join(e.cmd[3:])}` failed:\n{e.stderr.strip()}",
              file=sys.stderr)
        return 1

    base = git("merge-base", "HEAD", f"{REMOTE}/{BRANCH}", check=False)
    if base.returncode != 0:
        print(f"ci_framework_ref: HEAD shares no history with {REMOTE}/{BRANCH} — the gate "
              "could only guess which paths are the framework's (has the framework been "
              "merged here? scripts/upgrade.sh)", file=sys.stderr)
        return 1
    print(f"ci_framework_ref: the gate will scope itself to the framework at "
          f"{base.stdout.strip()[:12]} (merge base with {REMOTE}/{BRANCH})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
