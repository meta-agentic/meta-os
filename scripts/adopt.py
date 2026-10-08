#!/usr/bin/env python3
"""Adopt a pre-existing instance: the first merge of the framework into a repository
that has its own history (systems/distribution.md, "Adopting an existing instance").

Run through `scripts/upgrade.sh --adopt`, which fetches the framework first; it reads
this file from the fetched framework commit, so an instance that does not carry the
framework's scripts yet can run it:

    git fetch upstream
    git show upstream/main:scripts/upgrade.sh | bash -s -- --adopt --dry-run

What it does, in order, and only to paths the framework tracks at TARGET:

  1. the instance contract: a root CLAUDE.md that is not the framework's moves to
     .claude/CLAUDE.md (where the one-repository layout keeps it);
  2. mounts: a symlink at a framework path (a whole framework folder linked from a
     sibling checkout, or a generated skill link) is removed — the framework's real
     folder takes its place;
  3. extension points: an instance git hook the framework now dispatches moves to
     .githooks.d/<hook>/, and the root .gitignore's instance-only rules move to
     .gitignore.instance — so neither is lost when the framework's file arrives;
  4. everything else at a framework path whose content differs is LISTED, and the
     adoption refuses unless --yes; with --yes the framework's version wins (tracked
     content stays in the pre-adoption commit, untracked content is backed up);
  5. one preparatory commit, then the merge with --allow-unrelated-histories — which
     cannot conflict, because step 1-4 left no differing file at a framework path.

--dry-run prints the plan and changes nothing.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CONTRACT, INSTANCE_CONTRACT = "CLAUDE.md", ".claude/CLAUDE.md"
GITIGNORE, INSTANCE_IGNORE = ".gitignore", ".gitignore.instance"
HOOKS_DIR, INSTANCE_HOOKS_DIR = ".githooks", ".githooks.d"
TEMPLATE_CONTRACT = "instance-template/root/.claude/CLAUDE.md"
BACKUP_DIR = "meta-os-adopt"          # under $GIT_DIR: untracked content replaced with --yes


def git(*args: str, check: bool = True, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], check=check, capture_output=True, text=text,
                          stdin=subprocess.DEVNULL)


def tree(ref: str) -> dict[str, tuple[str, str]]:
    """path -> (mode, blob sha) for every file in REF ('' or a missing HEAD: empty)."""
    r = git("ls-tree", "-r", "-z", "--full-tree", ref, check=False)
    out: dict[str, tuple[str, str]] = {}
    if r.returncode != 0:
        return out
    for entry in r.stdout.split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        mode, _kind, sha = meta.split()
        out[path] = (mode, sha)
    return out


def prefixes(path: str) -> list[str]:
    parts = path.split("/")
    return ["/".join(parts[:i]) for i in range(1, len(parts))]


def blob(ref: str, path: str) -> str:
    return git("show", f"{ref}:{path}").stdout


class Plan:
    def __init__(self) -> None:
        self.contract_move = False
        self.contract_create = False
        self.mounts: list[tuple[str, str]] = []          # tracked symlinks: (path, link target)
        self.links: list[str] = []                       # untracked symlinks (generated)
        self.hooks: list[tuple[str, str]] = []           # (from, to)
        self.ignore_moved: list[str] = []
        self.ignore_disabled: list[str] = []
        self.ignore_drop_file = False
        self.replaced: list[str] = []                    # tracked, framework's version wins
        self.backed_up: list[str] = []                   # untracked, framework's version wins
        self.identical: list[str] = []                   # untracked, byte-identical to the framework's

    def empty(self) -> bool:
        return not any((self.contract_move, self.contract_create, self.mounts, self.links,
                        self.hooks, self.ignore_drop_file, self.replaced, self.backed_up,
                        self.identical))


def lexists_plain(root: Path, rel: str) -> bool:
    """True if REL exists on disk without crossing a symlinked parent."""
    for p in prefixes(rel):
        if (root / p).is_symlink() or ((root / p).exists() and not (root / p).is_dir()):
            return False
    return os.path.lexists(root / rel)


def instance_only_ignore_rules(head_text: str, fw_text: str) -> list[str]:
    fw = {ln.rstrip() for ln in fw_text.splitlines()}
    return [ln.rstrip() for ln in head_text.splitlines() if ln.strip() and ln.rstrip() not in fw]


def rules_matching(rules: list[str], paths: list[str]) -> set[str]:
    """The ignore rules that would ignore at least one of PATHS (a framework file)."""
    hit: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="meta-os-adopt-") as tmp:
        subprocess.run(["git", "init", "-q", tmp], check=True, capture_output=True)
        for rule in rules:
            if rule.lstrip().startswith("#"):
                continue
            Path(tmp, ".gitignore").write_text(rule + "\n")
            r = subprocess.run(["git", "-C", tmp, "check-ignore", "--no-index", "--stdin"],
                               input="\n".join(paths) + "\n", capture_output=True, text=True)
            if r.stdout.strip():
                hit.add(rule)
    return hit


def make_plan(root: Path, target: str) -> Plan:
    fw, head = tree(target), tree("HEAD")
    fw_dirs = {d for p in fw for d in prefixes(p)}
    plan = Plan()
    handled: set[str] = set()

    # 1. the instance contract
    if CONTRACT in head and head[CONTRACT] != fw.get(CONTRACT):
        if INSTANCE_CONTRACT not in head and not os.path.lexists(root / INSTANCE_CONTRACT):
            plan.contract_move = True
            handled.add(CONTRACT)
    elif INSTANCE_CONTRACT not in head and not os.path.lexists(root / INSTANCE_CONTRACT):
        plan.contract_create = True

    # 2. symlink mounts at framework paths (tracked, then generated ones on disk)
    for path, (mode, sha) in head.items():
        if mode == "120000" and (path in fw or path in fw_dirs):
            plan.mounts.append((path, git("cat-file", "blob", sha).stdout))
            handled.add(path)
    mounted = {p for p, _ in plan.mounts}
    for path in sorted(set(fw) | fw_dirs):
        if path in head or any(p in mounted for p in prefixes(path)):
            continue
        if lexists_plain(root, path) and (root / path).is_symlink():
            plan.links.append(path)
    linked = set(plan.links)

    # 3a. instance hooks the framework now dispatches
    for path in sorted(head):
        parts = path.split("/")
        if len(parts) != 2 or parts[0] != HOOKS_DIR or path in handled:
            continue
        if path in fw and head[path] != fw[path] and f"{INSTANCE_HOOKS_DIR}/" in blob(target, path):
            dest = f"{INSTANCE_HOOKS_DIR}/{parts[1]}/instance"
            n = 1
            while dest in head or os.path.lexists(root / dest):
                n += 1
                dest = f"{INSTANCE_HOOKS_DIR}/{parts[1]}/instance-{n}"
            plan.hooks.append((path, dest))
            handled.add(path)

    # 3b. instance-only ignore rules
    if GITIGNORE in head and GITIGNORE in fw and head[GITIGNORE] != fw[GITIGNORE]:
        rules = instance_only_ignore_rules(blob("HEAD", GITIGNORE), blob(target, GITIGNORE))
        bad = rules_matching(rules, sorted(fw))
        plan.ignore_moved = [r for r in rules if r not in bad]
        plan.ignore_disabled = [r for r in rules if r in bad]
        plan.ignore_drop_file = True
        handled.add(GITIGNORE)

    # 4. everything else at a framework path
    for path, entry in sorted(head.items()):
        if path in handled:
            continue
        if path in fw and entry != fw[path]:
            plan.replaced.append(path)                      # differing content or mode
        elif path in fw_dirs or any(p in fw for p in prefixes(path)):
            plan.replaced.append(path)                      # file where the framework has a folder, or the reverse
    for path in sorted(set(fw) | fw_dirs):
        if path in head or path in linked or any(p in mounted or p in linked for p in prefixes(path)):
            continue
        if not lexists_plain(root, path) or (root / path).is_symlink():
            continue
        full = root / path
        if path in fw_dirs and full.is_dir():
            continue                                        # a folder where the framework has one
        if path in fw and full.is_file() and git("hash-object", "--", path).stdout.strip() == fw[path][1]:
            plan.identical.append(path)                     # the merge would refuse to overwrite it
        else:
            plan.backed_up.append(path)
    return plan


def report(plan: Plan, target: str, short: str) -> None:
    say = print
    say(f"adopt — first merge of the framework at {short} ({target})")
    if plan.empty():
        say("  nothing at the framework's paths differs — the merge takes the framework as is")
    if plan.contract_move:
        say(f"  instance contract: {CONTRACT} -> {INSTANCE_CONTRACT} (the root {CONTRACT} becomes the framework's)")
    if plan.contract_create:
        say(f"  instance contract: no {INSTANCE_CONTRACT} — instantiated from {TEMPLATE_CONTRACT}")
    for path, dest in plan.mounts:
        say(f"  mount removed: {path} -> {dest} (the framework's folder takes its place)")
    for path in plan.links:
        say(f"  generated link removed: {path}")
    for path in plan.identical:
        say(f"  untracked copy removed: {path} (identical to the framework's)")
    for src, dest in plan.hooks:
        say(f"  hook moved: {src} -> {dest} (the framework's {src} runs it)")
    if plan.ignore_drop_file:
        say(f"  ignore rules: {len(plan.ignore_moved)} instance rule(s) of {GITIGNORE} -> {INSTANCE_IGNORE}"
            f" (scripts/packs.sh sync applies them)")
        for r in plan.ignore_moved:
            say(f"    moved:    {r}")
        for r in plan.ignore_disabled:
            say(f"    disabled: {r}   (matches framework files; kept commented out in {INSTANCE_IGNORE})")
    if plan.replaced or plan.backed_up:
        say(f"  instance content at framework paths — the framework's version replaces it:")
        for p in plan.replaced:
            say(f"    replaced: {p}   (stays in the pre-adoption commit)")
        for p in plan.backed_up:
            say(f"    replaced: {p}   (untracked — backed up under $GIT_DIR/{BACKUP_DIR}/)")
        say("    move what you want to keep to an instance path or an extension point first"
            " (systems/distribution.md), or accept with --yes")


def fill_template(text: str, name: str, ref: str) -> str:
    return (text.replace("{{instance-name}}", name)
                .replace("{{bootstrapped}}", _dt.date.today().isoformat())
                .replace("{{template-ref}}", ref))


def execute(root: Path, plan: Plan, target: str, new: str, name: str) -> None:
    pre = git("rev-parse", "HEAD").stdout.strip()
    stamp = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    gitdir = Path(git("rev-parse", "--absolute-git-dir").stdout.strip())
    for path in plan.links + plan.identical:
        (root / path).unlink()
    for path in plan.backed_up:
        dst = gitdir / BACKUP_DIR / stamp / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(root / path), str(dst))
    for path, _ in plan.mounts:
        git("rm", "-q", "--", path)
    if plan.replaced:
        git("rm", "-q", "-r", "--", *plan.replaced)

    def relocate(src: str, dest: str) -> None:
        (root / dest).parent.mkdir(parents=True, exist_ok=True)
        os.replace(root / src, root / dest)
        git("rm", "-q", "--cached", "--", src)
        git("add", "-f", "--", dest)

    if plan.contract_move:
        relocate(CONTRACT, INSTANCE_CONTRACT)
    if plan.contract_create:
        dest = root / INSTANCE_CONTRACT
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(fill_template(blob(target, TEMPLATE_CONTRACT), name, new))
        git("add", "-f", "--", INSTANCE_CONTRACT)
    for src, dest in plan.hooks:
        relocate(src, dest)
    if plan.ignore_drop_file:
        ign = root / INSTANCE_IGNORE
        existing = ign.read_text().splitlines() if ign.is_file() else [
            "# Instance-only ignore rules — the root .gitignore is the framework's.",
            "# scripts/packs.sh sync copies these into $GIT_DIR/info/exclude (systems/distribution.md)."]
        add = [r for r in plan.ignore_moved if r not in existing]
        add += [f"# disabled by adoption, it matched framework files: {r}" for r in plan.ignore_disabled]
        ign.write_text("\n".join(existing + add) + "\n")
        git("add", "-f", "--", INSTANCE_IGNORE)
        git("rm", "-q", "--", GITIGNORE)

    if git("diff", "--cached", "--quiet", check=False).returncode != 0:
        body = ["Move the instance's files off the paths the framework tracks, so the first",
                "merge of the framework replaces no instance content silently."]
        git("commit", "-q", "--no-verify", "-m", "chore(adopt): move instance files off the framework's paths",
            "-m", "\n".join(body))
        print(f"  committed the preparation: {git('rev-parse', '--short', 'HEAD').stdout.strip()}")
    r = git("merge", "-q", "--no-verify", "--allow-unrelated-histories", "--no-edit", "-m",
            f"Merge the framework at {new[:12]} (adoption: first merge)", target, check=False)
    if r.returncode != 0:
        git("merge", "--abort", check=False)
        sys.exit(f"adopt: the first merge failed — nothing merged; undo the preparation with "
                 f"`git reset --hard {pre[:12]}`\n{r.stdout}{r.stderr}")
    print(f"  merged: {pre[:12]}..{git('rev-parse', '--short', 'HEAD').stdout.strip()} "
          f"— undo the whole adoption with `git reset --hard {pre[:12]}`")
    if plan.backed_up:
        print(f"  untracked content that was replaced is in {gitdir / BACKUP_DIR / stamp}")


def main() -> None:
    ap = argparse.ArgumentParser(description="adopt a pre-existing instance (first framework merge)")
    ap.add_argument("--target", required=True, help="the fetched framework ref, e.g. upstream/main")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    ap.add_argument("--yes", action="store_true", help="accept replacing the listed instance content")
    ap.add_argument("--name", default="", help="instance name for an instantiated contract")
    args = ap.parse_args()

    root = Path(git("rev-parse", "--show-toplevel").stdout.strip())
    os.chdir(root)
    new = git("rev-parse", f"{args.target}^{{commit}}").stdout.strip()
    if git("merge-base", "HEAD", new, check=False).returncode == 0:
        sys.exit(f"adopt: this repository already shares history with {args.target} — "
                 f"nothing to adopt; run scripts/upgrade.sh")
    if not args.dry_run and git("status", "--porcelain", "--untracked-files=no").stdout.strip():
        sys.exit("adopt: the working tree has uncommitted changes — commit or stash them first")

    plan = make_plan(root, args.target)
    report(plan, args.target, new[:12])
    needs_yes = bool(plan.replaced or plan.backed_up)
    if args.dry_run:
        print("dry run — nothing changed" + ("; the real run needs --yes for the content listed"
                                             " above" if needs_yes else ""))
        return
    if needs_yes and not args.yes:
        sys.exit("adopt: refusing — the instance content listed above would be replaced; move it "
                 "first, or re-run with --yes")
    execute(root, plan, args.target, new, args.name or root.name)


if __name__ == "__main__":
    main()
