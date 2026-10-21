#!/usr/bin/env python3
"""Public-repo instance-data gate: no tracker keys or machine paths in what a public repo receives.

The framework's public-safety scan (validate_framework.py, check 5) keeps instance data out of
this repository. A lane also writes to other public repositories, so the same primitives run
there, at the three moments a key can leave: the branch name, the commit message, the pull
request. Every repository counts as public until the probe proves it private.

    public_repo_gate.py visibility OWNER/NAME           prints public | private
    public_repo_gate.py setup [-C CLONE]                 lane setup: probe; if public, install the
                                                         commit-msg hook and check the branch name
    public_repo_gate.py commit-msg FILE [-C CLONE]       the hook: reject a message carrying a key
    public_repo_gate.py pre-pr [-C CLONE] [--base REF] [--title T] [--body-file F]
                                                         before a PR: branch, messages, file names,
                                                         added lines, and the PR's title and body

Configuration is the instance's: the `publicRepoGate` object of meta-os.config.json (from
--config, else the repository this script sits in). Every key is optional:

    keyPattern     regex of the instance's tracker keys (default: the framework's key shape)
    allowedTokens  exact tokens that look like keys and are not, added to the framework's list
    exemptRepos    OWNER/NAME whose public text carries keys by design; paths are still checked
    pathPrefixes   absolute path prefixes that are instance data, besides any /Users/<name>

An unknown key or a wrong type is an error, never a silent fallback to the defaults.

The hook is not the whole gate. `git commit --no-verify`, and every operation that never runs
`commit-msg` (cherry-pick, rebase, am, commit-tree), write commits it never sees; `pre-pr` is
the backstop that reads every commit on the branch. `setup` exiting 2 means no hook could be
installed (a foreign hook, or a clone that sets core.hooksPath): the lane stops, or calls
`commit-msg "$1"` from the repository's own hook. The installed hook names this script by its
absolute path, so removing that checkout breaks every later commit, closed.

Exit: 0 clean or not public, 1 a finding, 2 a usage, configuration or git error.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_framework import (  # noqa: E402  (path set up immediately above)
    ABS_HOME_RE,
    PUBLIC_SAFETY_ALLOWED_TOKENS,
    TRACKER_KEY_RE,
)

ROOT = Path(__file__).resolve().parent.parent
HOOK_MARK = "# meta-os public-repo gate"
GITHUB_RE = re.compile(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")


SCHEMA = {"keyPattern": str, "allowedTokens": list, "exemptRepos": list, "pathPrefixes": list}


class GateError(Exception):
    """A configuration or git failure: exit 2, never a pass."""


class Config:
    def __init__(self, data: dict):
        for key, value in data.items():
            if key not in SCHEMA:
                raise GateError(f"publicRepoGate: unknown key {key!r} (known: {', '.join(SCHEMA)})")
            if not isinstance(value, SCHEMA[key]) or (
                    isinstance(value, list) and not all(isinstance(v, str) for v in value)):
                raise GateError(f"publicRepoGate: {key} must be "
                                f"{'a string' if SCHEMA[key] is str else 'a list of strings'}")
        try:
            self.key_re = re.compile(data["keyPattern"]) if data.get("keyPattern") else TRACKER_KEY_RE
        except re.error as exc:
            raise GateError(f"publicRepoGate: keyPattern is not a valid regex: {exc}") from None
        self.allowed = PUBLIC_SAFETY_ALLOWED_TOKENS | set(data.get("allowedTokens") or ())
        self.exempt = {r.lower() for r in data.get("exemptRepos") or ()}
        prefixes = [re.escape(p) for p in data.get("pathPrefixes") or ()]
        self.path_re = re.compile("|".join([ABS_HOME_RE.pattern, *prefixes]))


def load_config(path: str | None) -> Config:
    p = Path(path) if path else ROOT / "meta-os.config.json"
    if not p.is_file():
        if path:
            raise GateError(f"no config at {p}")
        return Config({})
    try:
        data = json.loads(p.read_text(encoding="utf-8")).get("publicRepoGate") or {}
    except (OSError, ValueError, AttributeError) as exc:
        raise GateError(f"unreadable config {p}: {exc}") from None
    if not isinstance(data, dict):
        raise GateError(f"publicRepoGate in {p} is not an object")
    return Config(data)


def git(clone: str, *args: str) -> str:
    """Best effort: '' on failure. Only for reads whose absence fails closed on its own."""
    r = subprocess.run(["git", "-C", clone, *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def git_strict(clone: str, *args: str) -> str:
    r = subprocess.run(["git", "-C", clone, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise GateError(f"git {' '.join(args)} failed: {r.stderr.strip() or r.returncode}")
    return r.stdout


def added_lines(diff: str) -> list[str]:
    """Added lines of a diff, read by hunk, so a content line starting '++' is never a header."""
    out, in_hunk = [], False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            in_hunk = False
        elif line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line.startswith("+"):
            out.append(line[1:])
    return out


def repo_slug(clone: str) -> str:
    m = GITHUB_RE.search(git(clone, "remote", "get-url", "origin"))
    return f"{m.group(1)}/{m.group(2)}" if m else ""


def repo_visibility(slug: str) -> str:
    """'private' only when the host says so; anything else, an error included, is 'public'."""
    if slug:
        try:
            r = subprocess.run(["gh", "api", f"repos/{slug}", "--jq", ".visibility"],
                               capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and r.stdout.strip() in ("private", "internal"):
                return "private"
            if r.returncode == 0 and r.stdout.strip() == "public":
                return "public"
        except (OSError, subprocess.TimeoutExpired):
            pass
    print(f"public-repo gate: visibility of {slug or 'this clone'} unknown; treated as public",
          file=sys.stderr)
    return "public"


def scan(text: str, cfg: Config, where: str, keys: bool = True) -> list[str]:
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if keys:
            for m in cfg.key_re.finditer(line):
                if m.group(0) not in cfg.allowed:
                    out.append(f"{where}:{n}: tracker key {m.group(0)!r}")
        for m in cfg.path_re.finditer(line):
            out.append(f"{where}:{n}: machine path {m.group(0)!r}")
    return out


def gated(clone: str, cfg: Config) -> tuple[bool, bool]:
    """(public, keys checked) for the clone's repository."""
    slug = repo_slug(clone)
    if repo_visibility(slug) == "private":
        return False, False
    return True, slug.lower() not in cfg.exempt


def report(found: list[str], what: str) -> int:
    if not found:
        return 0
    print(f"public-repo gate: {what} would publish instance data to a public repository:",
          file=sys.stderr)
    for f in found:
        print(f"  {f}", file=sys.stderr)
    return 1


def cmd_commit_msg(a, cfg: Config) -> int:
    public, keys = gated(a.C, cfg)
    if not public:
        return 0
    # Every line, comment-looking ones included: `git commit -m` cleans up whitespace only, so a
    # '#' line or a scissors line is recorded as written. A key in an editor comment is a false
    # reject, which errs safe.
    text = Path(a.file).read_text(encoding="utf-8")
    return report(scan(text, cfg, "commit message", keys), "this commit message")


def cmd_pre_pr(a, cfg: Config) -> int:
    public, keys = gated(a.C, cfg)
    if not public:
        print("public-repo gate: private repository, nothing to check")
        return 0
    base = a.base or git(a.C, "symbolic-ref", "--short", "refs/remotes/origin/HEAD") or "origin/main"
    git_strict(a.C, "rev-parse", "--verify", f"{base}^{{commit}}")
    git_strict(a.C, "merge-base", base, "HEAD")      # an orphan or shallow branch is not judged
    found = []
    if a.title is not None:
        found += scan(a.title, cfg, "PR title", keys)
    if a.body_file:
        found += scan(Path(a.body_file).read_text(encoding="utf-8"), cfg, "PR body", keys)
    found += scan(git_strict(a.C, "rev-parse", "--abbrev-ref", "HEAD"), cfg, "branch name", keys)
    for sha in git_strict(a.C, "rev-list", f"{base}..HEAD").split():
        found += scan(git_strict(a.C, "log", "-1", "--format=%B", sha), cfg, f"commit {sha[:12]}", keys)
    found += scan(git_strict(a.C, "diff", "--name-only", f"{base}...HEAD"), cfg, "file name", keys)
    diff = git_strict(a.C, "diff", "--unified=0", "--no-color", "--no-ext-diff", f"{base}...HEAD")
    found += scan("\n".join(added_lines(diff)), cfg, "added line", keys)
    return report(found, "this branch")


def install_hook(clone: str, config: str | None) -> int:
    if git(clone, "config", "core.hooksPath"):
        print("public-repo gate: this clone sets core.hooksPath; call `public_repo_gate.py "
              "commit-msg \"$1\"` from that commit-msg hook instead", file=sys.stderr)
        return 2
    hook = Path(clone, git(clone, "rev-parse", "--git-path", "hooks"), "commit-msg")
    if hook.exists() and HOOK_MARK not in hook.read_text(encoding="utf-8", errors="replace"):
        print(f"public-repo gate: {hook} exists and is not this gate's; not replaced", file=sys.stderr)
        return 2
    cfg = Path(config).resolve() if config else ROOT / "meta-os.config.json"
    cfg_arg = f"--config {shlex.quote(str(cfg))} " if cfg.is_file() else ""
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(f'#!/bin/sh\n{HOOK_MARK}, installed by `public_repo_gate.py setup`\n'
                    f'exec python3 {shlex.quote(str(Path(__file__).resolve()))} {cfg_arg}'
                    f'commit-msg "$1"\n', encoding="utf-8")
    hook.chmod(0o755)
    return 0


def cmd_setup(a, cfg: Config) -> int:
    public, keys = gated(a.C, cfg)
    if not public:
        print("private: tracker keys allowed in branch names; no hook installed")
        return 0
    rc = install_hook(a.C, a.config)
    if rc:
        return rc
    print("public: branch names carry no tracker key (<prefix><slug of the title>); "
          "commit-msg hook installed")
    return report(scan(git(a.C, "rev-parse", "--abbrev-ref", "HEAD"), cfg, "branch name", keys),
                  "this branch name")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", help="the instance's meta-os.config.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("visibility"); v.add_argument("repo")
    for name in ("setup", "commit-msg", "pre-pr"):
        p = sub.add_parser(name); p.add_argument("-C", default=".", help="the clone (default: .)")
        if name == "commit-msg":
            p.add_argument("file")
        if name == "pre-pr":
            p.add_argument("--base", help="default: origin/HEAD, else origin/main")
            p.add_argument("--title", help="the pull request's title")
            p.add_argument("--body-file", help="a file holding the pull request's body")
    a = ap.parse_args(argv)
    try:
        cfg = load_config(a.config)
        if a.cmd == "visibility":
            print(repo_visibility(a.repo))
            return 0
        return {"setup": cmd_setup, "commit-msg": cmd_commit_msg, "pre-pr": cmd_pre_pr}[a.cmd](a, cfg)
    except (GateError, OSError) as exc:
        print(f"public-repo gate: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
