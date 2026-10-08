#!/usr/bin/env python3
"""Adopt a pre-existing instance: the first merge of the framework into a repository
that has its own history (systems/distribution.md, "Adopting an existing instance").

Run through `scripts/upgrade.sh --adopt`; it reads this file from the fetched framework
commit, so an instance that does not carry the framework's scripts yet can run it:

    git remote get-url upstream          # must be the framework you mean to trust
    git fetch upstream
    git show upstream/main:scripts/upgrade.sh | bash -s -- --adopt --dry-run

What it does, in order, and only to paths the framework tracks at TARGET:

  1. the instance contract: a root CLAUDE.md that is not the framework's moves to
     .claude/CLAUDE.md (a symlinked one moves as a link to the same file);
  2. mounts: a symlink where the framework has a FOLDER, pointing into a framework
     checkout's same-named folder (or at nothing), is removed — the framework's real
     folder takes its place; a symlink to anything else is instance content (step 4);
  3. extension points: an instance git hook the framework now dispatches moves to
     .githooks.d/<hook>/ (a symlinked hook moves as a link), and the root .gitignore's
     instance-only rules move to .gitignore.instance — so neither is lost;
  4. everything else at a framework path whose content differs is LISTED, and the
     adoption refuses unless --yes; with --yes the framework's version wins (tracked
     content stays in the pre-adoption commit, untracked content is backed up). A
     path that differs from a framework path only by case is refused outright;
  5. one preparatory commit, then the merge with --allow-unrelated-histories — which
     cannot conflict, because steps 1-4 left no differing file at a framework path.

A failure in step 5 rolls everything back. --dry-run prints the plan and writes nothing.
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
SYMLINK = "120000"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], check=check, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL)


def tree(ref: str) -> dict[str, tuple[str, str]]:
    """path -> (mode, blob sha) for every file in REF (a missing HEAD: empty)."""
    r = git("ls-tree", "-r", "-z", "--full-tree", ref, check=False)
    out: dict[str, tuple[str, str]] = {}
    if r.returncode != 0:
        return out
    for entry in r.stdout.split("\0"):
        if entry:
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
        self.contract_move: str | None = None            # None, or "file" / the link to recreate
        self.contract_create = False
        self.mounts: list[tuple[str, str]] = []          # tracked symlinks: (path, link text)
        self.links: list[tuple[str, str]] = []           # untracked symlinks: (path, link text)
        self.hooks: list[tuple[str, str, str | None]] = []   # (from, to, link to recreate or None)
        self.ignore_moved: list[str] = []
        self.ignore_disabled: list[str] = []
        self.ignore_drop_file = False
        self.replaced: list[str] = []                    # tracked, framework's version wins
        self.backed_up: list[str] = []                   # untracked, framework's version wins
        self.identical: list[str] = []                   # untracked, byte-identical to the framework's
        self.case_clash: list[tuple[str, str]] = []      # (framework path, instance path)

    def empty(self) -> bool:
        return not any((self.contract_move, self.contract_create, self.mounts, self.links,
                        self.hooks, self.ignore_drop_file, self.replaced, self.backed_up,
                        self.identical, self.case_clash))


def exact_on_disk(root: Path, rel: str) -> bool:
    """True if REL exists under that exact spelling, without crossing a symlinked parent."""
    for p in prefixes(rel):
        if (root / p).is_symlink() or ((root / p).exists() and not (root / p).is_dir()):
            return False
    if not os.path.lexists(root / rel):
        return False
    parent = (root / rel).parent
    return Path(rel).name in os.listdir(parent)        # a case variant on a case-insensitive disk is not REL


def is_framework_mount(root: Path, rel: str) -> bool:
    """A symlink that leads into a framework checkout's folder of the same name, or nowhere."""
    full = root / rel
    if not os.path.exists(full):
        return True                                       # dangling: it shows nothing, holds nothing
    real, parts = Path(os.path.realpath(full)), Path(rel).parts
    if not real.is_dir() or real.parts[-len(parts):] != parts:
        return False
    fwroot = Path(*real.parts[:-len(parts)])
    return all(((fwroot / "CLAUDE.md").is_file(), (fwroot / "skills").is_dir(),
                (fwroot / "systems").is_dir()))


def relink(root: Path, src: str, dest: str) -> str | None:
    """The link text that makes DEST point where the symlink SRC points, or None if dangling."""
    full = root / src
    if not os.path.exists(full):
        return None
    return os.path.relpath(os.path.realpath(full), (root / dest).parent)


def instance_only_ignore_lines(head_text: str, fw_text: str) -> list[str]:
    """Rules the framework's .gitignore lacks, each with the comments that introduce it.

    A comment block travels with the rule after it: comments describing a rule the
    framework already carries are left behind with that rule.
    """
    fw = {ln.rstrip() for ln in fw_text.splitlines()}
    out: list[str] = []
    comments: list[str] = []
    for raw in head_text.splitlines():
        ln = raw.rstrip()
        if not ln.strip():
            continue
        if ln.lstrip().startswith("#"):
            comments.append(ln)
            continue
        if ln not in fw:
            out += [c for c in comments if c not in fw] + [ln]
        comments = []
    return out + [c for c in comments if c not in fw]


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
    fw_all = set(fw) | fw_dirs
    plan = Plan()
    handled: set[str] = set()
    is_link = {p for p, (mode, _) in head.items() if mode == SYMLINK}

    # 0. case-only collisions (a case-insensitive disk holds one file for both names)
    clashed: set[str] = set()
    if git("config", "--bool", "core.ignorecase", check=False).stdout.strip() == "true":
        head_all = set(head) | {d for p in head for d in prefixes(p)}
        fold: dict[str, str] = {}
        for p in sorted(head_all):
            fold.setdefault(p.lower(), p)
        for p in sorted(fw_all):
            other = fold.get(p.lower())
            if p not in head_all and other and other != p and not any(q in clashed for q in prefixes(p)):
                plan.case_clash.append((p, other))
                clashed.add(p)
        handled |= {p for p in head if any(p.lower() == c.lower() or p.lower().startswith(c.lower() + "/")
                                           for c in clashed)}

    def under_clash(p: str) -> bool:
        return p in clashed or any(q in clashed for q in prefixes(p))

    # 1. the instance contract
    if not (INSTANCE_CONTRACT in head or os.path.lexists(root / INSTANCE_CONTRACT)):
        if CONTRACT in head and head[CONTRACT] != fw.get(CONTRACT):
            plan.contract_move = "file" if CONTRACT not in is_link else relink(root, CONTRACT, INSTANCE_CONTRACT)
            if plan.contract_move:
                handled.add(CONTRACT)                     # a dangling link is listed in step 4
        plan.contract_create = not plan.contract_move

    # 2. mounts: a symlink where the framework has a folder, leading into a framework checkout
    for path in sorted(is_link):
        if path in fw_dirs and not under_clash(path) and is_framework_mount(root, path):
            plan.mounts.append((path, os.readlink(root / path) if os.path.islink(root / path)
                                else git("cat-file", "blob", head[path][1]).stdout))
            handled.add(path)
    mounted = {p for p, _ in plan.mounts}
    for path in sorted(fw_all):
        if path in head or under_clash(path) or any(p in mounted for p in prefixes(path)):
            continue
        if exact_on_disk(root, path) and (root / path).is_symlink() and is_framework_mount(root, path):
            plan.links.append((path, os.readlink(root / path)))
    linked = {p for p, _ in plan.links}

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
            link = relink(root, path, dest) if path in is_link else None
            if path in is_link and link is None:
                continue                                  # a dangling hook link: listed in step 4
            plan.hooks.append((path, dest, link))
            handled.add(path)

    # 3b. instance-only ignore rules (read through a symlinked .gitignore)
    if GITIGNORE in head and GITIGNORE in fw and head[GITIGNORE] != fw[GITIGNORE]:
        ign = root / GITIGNORE
        text = (ign.read_text() if ign.is_file() else "") if GITIGNORE in is_link else blob("HEAD", GITIGNORE)
        lines = instance_only_ignore_lines(text, blob(target, GITIGNORE))
        bad = rules_matching(lines, sorted(fw))
        plan.ignore_moved = [r for r in lines if r not in bad]
        plan.ignore_disabled = [r for r in lines if r in bad]
        plan.ignore_drop_file = True
        handled.add(GITIGNORE)

    # 4. everything else at a framework path
    for path, entry in sorted(head.items()):
        if path in handled:
            continue
        if path in fw and entry != fw[path]:
            plan.replaced.append(path)                      # differing content, mode, or a foreign link
        elif path in fw_dirs or any(p in fw for p in prefixes(path)):
            plan.replaced.append(path)                      # file where the framework has a folder, or the reverse
    for path in sorted(fw_all):
        if path in head or path in linked or under_clash(path) \
                or any(p in mounted or p in linked for p in prefixes(path)):
            continue
        if not exact_on_disk(root, path):
            continue
        full = root / path
        if path in fw_dirs and full.is_dir() and not full.is_symlink():
            continue                                        # a folder where the framework has one
        if path in fw and full.is_file() and not full.is_symlink() \
                and git("hash-object", "--", path).stdout.strip() == fw[path][1]:
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
        how = "" if plan.contract_move == "file" else f" (a link, kept as a link to {plan.contract_move})"
        say(f"  instance contract: {CONTRACT} -> {INSTANCE_CONTRACT}{how} (the root {CONTRACT} becomes the framework's)")
    if plan.contract_create:
        say(f"  instance contract: no {INSTANCE_CONTRACT} — instantiated from {TEMPLATE_CONTRACT}")
    for path, dest in plan.mounts:
        say(f"  mount removed: {path} -> {dest} (the framework's folder takes its place)")
    for path, dest in plan.links:
        say(f"  generated link removed: {path} -> {dest}")
    for path in plan.identical:
        say(f"  untracked copy removed: {path} (identical to the framework's)")
    for src, dest, link in plan.hooks:
        how = f" (a link, kept as a link to {link})" if link else ""
        say(f"  hook moved: {src} -> {dest}{how} (the framework's {src} runs it)")
    if plan.ignore_drop_file:
        n = sum(1 for r in plan.ignore_moved if not r.lstrip().startswith("#"))
        say(f"  ignore rules: {n} instance rule(s) of {GITIGNORE}, with their comments -> {INSTANCE_IGNORE}"
            f" (scripts/packs.sh sync applies them)")
        for r in plan.ignore_moved:
            say(f"    moved:    {r}")
        for r in plan.ignore_disabled:
            say(f"    disabled: {r}   (matches framework files; kept commented out in {INSTANCE_IGNORE})")
    if plan.replaced or plan.backed_up:
        say("  instance content at framework paths — the framework's version replaces it:")
        for p in plan.replaced:
            say(f"    replaced: {p}   (stays in the pre-adoption commit)")
        for p in plan.backed_up:
            say(f"    replaced: {p}   (untracked — backed up under $GIT_DIR/{BACKUP_DIR}/)")
        say("    move what you want to keep to an instance path or an extension point first"
            " (systems/distribution.md), or accept with --yes")
    for fw_path, mine in plan.case_clash:
        say(f"  case clash: {mine} (this instance) vs {fw_path} (the framework) — one file on a"
            f" case-insensitive disk; rename yours first")


def fill_template(text: str, name: str, ref: str) -> str:
    return (text.replace("{{instance-name}}", name)
                .replace("{{bootstrapped}}", _dt.date.today().isoformat())
                .replace("{{template-ref}}", ref))


class Undo:
    """What execute() changed outside git's index and HEAD, to put back on failure."""

    def __init__(self, root: Path, pre: str) -> None:
        self.root, self.pre = root, pre
        self.links: list[tuple[str, str]] = []           # removed untracked links: (path, text)
        self.files: list[tuple[str, bytes]] = []         # removed identical copies: (path, bytes)
        self.moved: list[tuple[str, Path]] = []          # backed-up files: (path, backup)

    def rollback(self) -> list[str]:
        problems: list[str] = []
        git("merge", "--abort", check=False)
        if git("reset", "-q", "--hard", self.pre, check=False).returncode != 0:
            problems.append(f"git reset --hard {self.pre[:12]}")
        for path, text in self.links:
            try:
                os.symlink(text, self.root / path)
            except OSError:
                problems.append(f"ln -s {text} {path}")
        for path, data in self.files:
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_bytes(data)
        for path, backup in self.moved:
            try:
                (self.root / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(backup), str(self.root / path))
            except OSError:
                problems.append(f"mv {backup} {path}")
        return problems


def execute(root: Path, plan: Plan, target: str, new: str, name: str) -> None:
    pre = git("rev-parse", "HEAD").stdout.strip()
    stamp = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    gitdir = Path(git("rev-parse", "--absolute-git-dir").stdout.strip())
    undo = Undo(root, pre)
    try:
        _apply(root, plan, target, new, name, gitdir / BACKUP_DIR / stamp, undo)
    except BaseException as err:                          # noqa: BLE001 — every failure rolls back
        detail = err.stderr if isinstance(err, subprocess.CalledProcessError) else str(err)
        problems = undo.rollback()
        if problems:
            sys.exit(f"adopt: failed ({detail.strip()}) and could not roll back fully — finish by hand:\n  "
                     + "\n  ".join(problems))
        sys.exit(f"adopt: failed — rolled back to {pre[:12]}, nothing changed; fix the cause and re-run:\n"
                 f"  {detail.strip()}")
    print(f"  merged: {pre[:12]}..{git('rev-parse', '--short', 'HEAD').stdout.strip()} "
          f"— undo the whole adoption with `git reset --hard {pre[:12]}`")
    if undo.moved:
        print(f"  untracked content that was replaced is in {gitdir / BACKUP_DIR / stamp}")


def _apply(root: Path, plan: Plan, target: str, new: str, name: str, backup: Path, undo: Undo) -> None:
    for path, text in plan.links:
        (root / path).unlink()
        undo.links.append((path, text))
    for path in plan.identical:
        undo.files.append((path, (root / path).read_bytes()))
        (root / path).unlink()
    for path in plan.backed_up:
        dst = backup / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(root / path), str(dst))
        undo.moved.append((path, dst))
    for path, _ in plan.mounts:
        git("rm", "-q", "--", path)
    if plan.replaced:
        git("rm", "-q", "-r", "--", *plan.replaced)

    def relocate(src: str, dest: str, link: str | None) -> None:
        (root / dest).parent.mkdir(parents=True, exist_ok=True)
        if link is None:
            os.replace(root / src, root / dest)
        else:
            os.symlink(link, root / dest)
            (root / src).unlink()
        git("rm", "-q", "--cached", "--", src)
        git("add", "-f", "--", dest)

    if plan.contract_move:
        relocate(CONTRACT, INSTANCE_CONTRACT, None if plan.contract_move == "file" else plan.contract_move)
    if plan.contract_create:
        dest = root / INSTANCE_CONTRACT
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(fill_template(blob(target, TEMPLATE_CONTRACT), name, new))
        git("add", "-f", "--", INSTANCE_CONTRACT)
    for src, dest, link in plan.hooks:
        relocate(src, dest, link)
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
        git("commit", "-q", "--no-verify", "-m", "chore(adopt): move instance files off the framework's paths",
            "-m", "Move the instance's files off the paths the framework tracks, so the first\n"
                  "merge of the framework replaces no instance content silently.")
        print(f"  committed the preparation: {git('rev-parse', '--short', 'HEAD').stdout.strip()}")
    git("merge", "-q", "--no-verify", "--allow-unrelated-histories", "--no-edit", "-m",
        f"Merge the framework at {new[:12]} (adoption: first merge)", target)


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
        print("dry run — nothing changed"
              + ("; the real run refuses until the case clashes are renamed" if plan.case_clash else
                 "; the real run needs --yes for the content listed above" if needs_yes else ""))
        return
    if plan.case_clash:
        sys.exit("adopt: refusing — rename the paths that clash with the framework's by case, then re-run")
    if needs_yes and not args.yes:
        sys.exit("adopt: refusing — the instance content listed above would be replaced; move it "
                 "first, or re-run with --yes")
    execute(root, plan, args.target, new, args.name or root.name)


if __name__ == "__main__":
    main()
