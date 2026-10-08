#!/usr/bin/env python3
"""Adopt a pre-existing instance: the first merge of the framework into a repository
that has its own history (systems/distribution.md, "Adopting an existing instance").

Run through `scripts/upgrade.sh --adopt`; it reads this file and scripts/adopt_plan.py
(the read-only planner) from the fetched framework commit, so an instance that does not carry the framework's scripts yet can run it:

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
from pathlib import Path

from adopt_plan import (BACKUP_DIR, CONTRACT, GITIGNORE, INSTANCE_CONTRACT, INSTANCE_IGNORE,
                        TEMPLATE_CONTRACT, Plan, blob, git, make_plan, report)


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
        self.submodules: list[tuple[str, str, Path]] = []  # framework submodules moved aside

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
    local = {p for p, _n, _u, has_work in plan.submodules if has_work}
    for path, name, dst in undo.submodules:              # a clean framework copy is not kept
        if path in local:
            continue
        shutil.rmtree(dst, ignore_errors=True)
        shutil.rmtree(gitdir / "modules" / path, ignore_errors=True)
        git("config", "--remove-section", f"submodule.{name}", check=False)
        undo.moved = [(p, d) for p, d in undo.moved if p != path]
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
    for path, name, _url, _local in plan.submodules:
        git("rm", "-q", "--cached", "--", path)
        git("config", "-f", ".gitmodules", "--remove-section", f"submodule.{name}")
        if git("config", "-f", ".gitmodules", "--list", check=False).stdout.strip():
            git("add", "--", ".gitmodules")
        else:
            git("rm", "-q", "-f", "--", ".gitmodules")
        if os.path.lexists(root / path):                 # the checkout moves aside; removed once merged
            dst = backup / path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(root / path), str(dst))
            undo.moved.append((path, dst))
            undo.submodules.append((path, name, dst))
    for path, _ in plan.mounts:
        git("rm", "-q", "--", path)
    if plan.discovery:
        git("rm", "-q", "--", *plan.discovery)
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

    remote_url = git("remote", "get-url", args.target.split("/", 1)[0], check=False).stdout.strip()
    plan = make_plan(root, args.target, remote_url)
    report(plan, args.target, new[:12])
    needs_yes = bool(plan.replaced or plan.backed_up or any(local for *_, local in plan.submodules))
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
