#!/usr/bin/env python3
"""Adopting a pre-existing instance: `scripts/upgrade.sh --adopt`, end to end.

    python3 -m unittest discover -s tests -p test_adopt.py

The instance here existed before it had the framework's history, in the layout that
preceded the one-repository model: its own git history, its contract in the root
`CLAUDE.md`, framework folders mounted as symlinks into a sibling framework checkout,
its own copy of a framework script, its own `pre-commit` and `commit-msg` hooks, its
own lines in the root `.gitignore`, a workflow of its own beside where the framework
keeps its workflows, and top-level paths the framework has never heard of. The command
under test is the one systems/distribution.md documents, run from the FETCHED framework
(`git show upstream/main:scripts/upgrade.sh | bash -s -- --adopt`), because such an
instance does not carry the framework's scripts yet.

What must hold: nothing of the instance is lost (contract moved, hooks still run from
their extension point, ignore rules still effective, instance paths byte-identical),
anything the framework's version would replace is listed before it is replaced and
needs --yes, the framework's gate passes afterwards, and the next upgrade is an
ordinary merge.
"""
from __future__ import annotations

import os
import stat
import subprocess
import unittest
from pathlib import Path

import test_instance_lifecycle as lifecycle
from test_instance_lifecycle import GIT_ENV, git, run

KEY = "AB" + "C-" + "42"            # a tracker-key lookalike, assembled so this file carries none


def sh(cmd: str, cwd: Path, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", cmd], cwd=cwd, check=check, capture_output=True,
                          text=True, timeout=300, env={**os.environ, **GIT_ENV})


class AdoptTest(lifecycle.LifecycleTest):

    def write(self, root: Path, rel: str, text: str, mode: int | None = None) -> None:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        if mode:
            p.chmod(mode)

    def make_old_instance(self) -> Path:
        sibling = self.tmp / "framework"                 # the sibling checkout the mounts point into
        git(self.tmp, "clone", "-q", str(self.upstream), str(sibling))
        inst = self.tmp / "estate"
        inst.mkdir()
        exe = 0o755
        self.write(inst, "CLAUDE.md", "# estate — the instance contract\n\nOld-layout rules.\n")
        for name in ("systems", "templates", "agents"):
            (inst / name).symlink_to(Path("..") / "framework" / name)
        self.write(inst, "scripts/packs.sh", "#!/bin/sh\necho 'the vendored copy'\n", exe)
        self.write(inst, ".githooks/pre-commit",
                   '#!/bin/sh\ntouch "$(git rev-parse --show-toplevel)/.git/instance-gate-ran"\n', exe)
        self.write(inst, ".githooks/commit-msg",
                   '#!/bin/sh\nif grep -q FORBIDDEN "$1"; then echo "instance rule" >&2; exit 1; fi\n', exe)
        self.write(inst, ".gitignore", ".DS_Store\n# python bytecode\n__pycache__/\n# the old generated layout\n/skills/\n"
                                       "# local caches of the estate's automations\nlocal-cache/\n")
        self.write(inst, ".github/workflows/estate.yml", f"name: estate\n# tracks {KEY}\n")
        self.write(inst, "harness/run.md", f"# harness\nsee {KEY}\n")
        self.write(inst, "ontology.yaml", f"types: [{KEY}]\n")
        self.write(inst, "README.md", "# estate\n")
        self.write(inst, "_index.md", "# home\n")
        self.write(inst, "memory/wiki/note.md", f"a note about {KEY}\n")
        git(inst, "init", "-q", "-b", "main")
        git(inst, "add", "-A")
        git(inst, "commit", "-q", "-m", "the estate, before the framework")
        git(inst, "config", "core.hooksPath", ".githooks")
        # the old layout generated skill links into an ignored skills/
        (inst / "skills").mkdir()
        (inst / "skills" / "graphify").symlink_to(Path("..") / ".." / "framework" / "skills" / "graphify")
        git(inst, "remote", "add", "upstream", str(self.upstream))
        git(inst, "fetch", "-q", "upstream")
        return inst

    def adopt(self, inst: Path, *flags: str, check=True) -> subprocess.CompletedProcess:
        return sh("git show upstream/main:scripts/upgrade.sh | bash -s -- --adopt " + " ".join(flags),
                  inst, check=check)

    def snapshot(self, inst: Path) -> dict[str, str]:
        rels = ["harness/run.md", "ontology.yaml", ".github/workflows/estate.yml", "_index.md",
                "memory/wiki/note.md"]
        return {r: (inst / r).read_text() for r in rels}

    def test_adoption_keeps_every_instance_file_and_ends_in_an_ordinary_upgrade(self):
        inst = self.make_old_instance()
        before = self.snapshot(inst)
        head = git(inst, "rev-parse", "HEAD")

        # 1. the plan, listed before anything is replaced
        r = self.adopt(inst, "--dry-run")
        out = r.stdout
        self.assertIn("instance contract: CLAUDE.md -> .claude/CLAUDE.md", out)
        for name in ("systems", "templates", "agents"):
            self.assertIn(f"mount removed: {name} -> ../framework/{name}", out)
        self.assertIn("generated link removed: skills/graphify", out)
        self.assertIn("hook moved: .githooks/pre-commit -> .githooks.d/pre-commit/instance", out)
        self.assertIn("hook moved: .githooks/commit-msg -> .githooks.d/commit-msg/instance", out)
        self.assertIn("moved:    local-cache/", out)
        self.assertIn("disabled: /skills/", out)
        self.assertIn("replaced: README.md", out)
        self.assertIn("replaced: scripts/packs.sh", out)
        for kept in ("harness", "ontology.yaml", "estate.yml", "_index.md", "memory/"):
            self.assertNotIn(kept, out, f"{kept} is the instance's and must not be in the plan")
        self.assertIn("dry run — nothing changed", out)
        self.assertEqual(head, git(inst, "rev-parse", "HEAD"))
        self.assertEqual("", git(inst, "status", "--porcelain"))
        self.assertTrue((inst / "systems").is_symlink())

        # 2. without --yes the listed replacements are refused, and nothing moves
        r = self.adopt(inst, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("refusing", r.stderr)
        self.assertEqual(head, git(inst, "rev-parse", "HEAD"))

        # 3. the adoption
        r = self.adopt(inst, "--yes")
        self.assertIn("merged:", r.stdout)
        self.assertIn("framework self-check: ok", r.stdout)
        self.assertEqual("", git(inst, "status", "--porcelain"))
        self.assertEqual(before, self.snapshot(inst))
        self.assertIn("Old-layout rules.", (inst / ".claude" / "CLAUDE.md").read_text())
        self.assertEqual((self.upstream / "CLAUDE.md").read_text(), (inst / "CLAUDE.md").read_text())
        self.assertEqual((self.upstream / ".gitignore").read_text(), (inst / ".gitignore").read_text())
        for name in ("systems", "templates", "agents"):
            self.assertFalse((inst / name).is_symlink(), name)
            self.assertTrue((inst / name / "_index.md").is_file(), name)
        self.assertTrue((inst / "skills" / "graphify" / "SKILL.md").is_file())
        self.assertFalse((inst / "skills" / "graphify").is_symlink())
        # replaced content is recoverable from the pre-adoption commit
        self.assertEqual("# estate\n", git(inst, "show", f"{head}:README.md") + "\n")

        # the instance hooks still run, from their extension point
        moved = inst / ".githooks.d" / "pre-commit" / "instance"
        self.assertTrue(os.stat(moved).st_mode & stat.S_IXUSR)
        (inst / "memory" / "wiki" / "second.md").write_text("more\n")
        git(inst, "add", "memory/wiki/second.md")
        r = run(["git", "commit", "-q", "-m", "FORBIDDEN by the instance"], inst, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("instance rule", r.stderr)
        git(inst, "commit", "-q", "-m", "a second note")
        self.assertTrue((inst / ".git" / "instance-gate-ran").is_file())

        # the instance ignore rules still hold; the old layout's /skills/ rule does not
        (inst / "local-cache").mkdir()
        (inst / "local-cache" / "blob").write_text("x\n")
        self.assertEqual("", git(inst, "status", "--porcelain"))
        rules = (inst / ".gitignore.instance").read_text()
        self.assertIn("\nlocal-cache/\n", rules)
        self.assertIn("# disabled by adoption, it matched framework files: /skills/", rules)
        self.assertNotIn("python bytecode", rules)        # its rule is the framework's: it stays behind

        # the framework's gate, scoped to the framework's paths
        r = run(["python3", "scripts/validate_framework.py"], inst, check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("instance: checking the framework's paths", r.stdout)
        self.assertIn("mounts match", run(["scripts/packs.sh", "check"], inst).stdout)
        self.assertIn("0 commit(s) behind", run(["scripts/upgrade.sh", "--check"], inst).stdout)

        # 4. from here on, an ordinary upgrade
        self.upstream_commit("framework v2", {"systems/engine.md": "\nv2 line\n",
                                              "scripts/v2_tool.py": "# added in v2\n"})
        r = run(["scripts/upgrade.sh"], inst)
        self.assertNotIn("unrelated", r.stdout)
        self.assertIn("1 commit(s) behind", r.stdout)
        self.assertIn("v2 line", (inst / "systems" / "engine.md").read_text())
        self.assertEqual(before, self.snapshot(inst))
        # a framework file added in v2 is in scope, and a stale override cannot narrow that
        (inst / "scripts" / "v2_tool.py").write_text(f"# ask about {KEY}\n")
        for ref in (None, self.v1):
            env = {**os.environ, **GIT_ENV, **({"META_OS_FRAMEWORK_REF": ref} if ref else {})}
            r = subprocess.run(["python3", "scripts/validate_framework.py"], cwd=inst, capture_output=True,
                               text=True, env=env)
            self.assertNotEqual(r.returncode, 0, f"{ref}: {r.stdout}")
            self.assertIn("scripts/v2_tool.py:1", r.stdout)
        git(inst, "checkout", "-q", "--", "scripts/v2_tool.py")
        r = self.adopt(inst, "--dry-run")
        self.assertIn("nothing to adopt", r.stdout)

    def test_adoption_without_a_contract_instantiates_one_and_needs_no_yes(self):
        inst = self.tmp / "bare"
        inst.mkdir()
        self.write(inst, "notes/a.md", "# a\n")
        git(inst, "init", "-q", "-b", "main")
        git(inst, "add", "-A")
        git(inst, "commit", "-q", "-m", "notes")
        git(inst, "remote", "add", "upstream", str(self.upstream))
        git(inst, "fetch", "-q", "upstream")
        r = self.adopt(inst)
        self.assertIn("instantiated from instance-template/root/.claude/CLAUDE.md", r.stdout)
        self.assertIn("# bare — Agentic OS instance", (inst / ".claude" / "CLAUDE.md").read_text())
        self.assertEqual("# a\n", (inst / "notes" / "a.md").read_text())
        r = run(["python3", "scripts/validate_framework.py"], inst, check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_an_untracked_file_at_a_framework_path_is_backed_up_not_lost(self):
        inst = self.make_old_instance()
        (inst / "PROVENANCE.md").write_text("an operator's scratch notes\n")     # untracked
        r = self.adopt(inst, "--dry-run")
        self.assertIn("replaced: PROVENANCE.md   (untracked", r.stdout)
        self.adopt(inst, "--yes")
        backups = list((inst / ".git" / "meta-os-adopt").glob("*/PROVENANCE.md"))
        self.assertEqual(1, len(backups))
        self.assertEqual("an operator's scratch notes\n", backups[0].read_text())

    def test_a_snapshot_with_a_symlink_where_the_framework_has_a_folder_upgrades(self):
        # the first merge of unrelated histories meets git's <path>~HEAD conflict shape
        inst = self.tmp / "tpl"
        inst.mkdir()
        archive = subprocess.run(["git", "archive", self.v1], cwd=self.upstream, check=True,
                                 capture_output=True, env={**os.environ, **GIT_ENV}).stdout
        subprocess.run(["tar", "-xf", "-"], cwd=inst, input=archive, check=True)
        git(inst, "init", "-q", "-b", "main")
        sibling = self.tmp / "framework"
        git(self.tmp, "clone", "-q", str(self.upstream), str(sibling))
        subprocess.run(["rm", "-rf", str(inst / "agents")], check=True)
        (inst / "agents").symlink_to(Path("..") / "framework" / "agents")
        git(inst, "add", "-A"); git(inst, "commit", "-q", "-m", "Initial commit")
        self.bootstrap(inst, "--commit")
        self.upstream_commit("framework v2", {"agents/_index.md": "\nv2 roster\n"})
        r = run(["scripts/upgrade.sh"], inst)
        self.assertIn("resolved", r.stdout)
        self.assertFalse((inst / "agents").is_symlink())
        self.assertIn("v2 roster", (inst / "agents" / "_index.md").read_text())
        self.assertFalse(os.path.lexists(inst / "agents~HEAD"))
        self.assertEqual("", git(inst, "status", "--porcelain"))


    # --- review hardening ---------------------------------------------------------------

    def fingerprint(self, inst: Path) -> dict[str, str]:
        """Everything a dry run must leave alone."""
        gd = inst / ".git"
        hooks = sorted(str(p.relative_to(gd)) for p in (gd / "hooks").rglob("*")) if (gd / "hooks").is_dir() else []
        exclude = gd / "info" / "exclude"
        return {
            "head": git(inst, "rev-parse", "HEAD"),
            "refs": git(inst, "for-each-ref"),
            "index": git(inst, "ls-files", "-s"),
            "status": git(inst, "status", "--porcelain", "--ignored", "--untracked-files=all"),
            "exclude": exclude.read_text() if exclude.is_file() else "",
            "config": git(inst, "config", "--local", "--list"),
            "hooks": "\n".join(hooks),
            "backups": str((gd / "meta-os-adopt").exists()),
        }

    def test_a_dry_run_writes_nothing_in_any_state(self):
        inst = self.make_old_instance()
        before = self.fingerprint(inst)                       # unrelated histories
        self.adopt(inst, "--yes", "--dry-run")
        self.assertEqual(before, self.fingerprint(inst))
        self.adopt(inst, "--yes")
        before = self.fingerprint(inst)                       # shared history, current
        r = self.adopt(inst, "--dry-run")
        self.assertIn("nothing to adopt", r.stdout)
        self.assertEqual(before, self.fingerprint(inst))
        self.upstream_commit("framework v2", {"systems/engine.md": "\nv2 line\n"})
        git(inst, "fetch", "-q", "upstream")
        before = self.fingerprint(inst)                       # shared history, behind
        for cmd in (lambda: self.adopt(inst, "--dry-run"), lambda: self.adopt(inst, "--check"),
                    lambda: run(["scripts/upgrade.sh", "--dry-run"], inst)):
            r = cmd()
            self.assertIn("1 commit(s) behind", r.stdout)
            self.assertNotIn("merged:", r.stdout)
            self.assertEqual(before, self.fingerprint(inst))
        self.assertNotIn("v2 line", (inst / "systems" / "engine.md").read_text())

    def test_symlinked_instance_files_at_framework_file_paths_keep_their_content(self):
        inst = self.tmp / "linked"
        self.write(inst, "tools/gate.sh", "#!/bin/sh\necho INSTANCE-GATE >&2\nexit 1\n", 0o755)
        self.write(inst, "docs/contract.md", "# linked contract\n")
        self.write(inst, "ignore.txt", "local-cache/\n")
        (inst / ".githooks").mkdir()
        (inst / ".githooks" / "pre-commit").symlink_to(Path("..") / "tools" / "gate.sh")
        (inst / "CLAUDE.md").symlink_to(Path("docs") / "contract.md")
        (inst / ".gitignore").symlink_to("ignore.txt")
        git(inst, "init", "-q", "-b", "main")
        git(inst, "add", "-A"); git(inst, "commit", "-q", "-m", "linked")
        git(inst, "remote", "add", "upstream", str(self.upstream))
        git(inst, "fetch", "-q", "upstream")
        r = self.adopt(inst)                                  # nothing here needs --yes
        self.assertIn("hook moved: .githooks/pre-commit -> .githooks.d/pre-commit/instance (a link", r.stdout)
        self.assertNotIn("mount removed", r.stdout)
        self.assertEqual("# linked contract\n", (inst / ".claude" / "CLAUDE.md").read_text())
        self.assertIn("\nlocal-cache/\n", (inst / ".gitignore.instance").read_text())
        self.assertEqual("", git(inst, "status", "--porcelain"))
        git(inst, "config", "core.hooksPath", ".githooks")
        (inst / "docs" / "b.md").write_text("b\n")
        git(inst, "add", "docs/b.md")
        r = run(["git", "commit", "-q", "-m", "b"], inst, check=False)
        self.assertNotEqual(r.returncode, 0, "the instance gate must still run")
        self.assertIn("INSTANCE-GATE", r.stderr)

    def test_a_folder_link_that_is_not_a_framework_checkout_is_listed_not_dropped(self):
        inst = self.make_old_instance()
        self.write(self.tmp, "private-agents/roster.md", "mine\n")
        (inst / "agents").unlink()
        (inst / "agents").symlink_to(Path("..") / "private-agents")
        git(inst, "add", "-A"); git(inst, "commit", "-q", "-m", "own agents")
        r = self.adopt(inst, "--dry-run")
        self.assertIn("replaced: agents", r.stdout)
        self.assertNotIn("mount removed: agents", r.stdout)
        self.assertIn("mount removed: systems", r.stdout)

    def test_a_failure_while_adopting_rolls_back_and_a_rerun_works(self):
        inst = self.make_old_instance()
        (inst / "PROVENANCE.md").write_text("scratch\n")                  # untracked, backed up
        before = self.fingerprint(inst)
        git(inst, "config", "commit.gpgsign", "true")
        git(inst, "config", "gpg.program", "false")
        before["config"] = git(inst, "config", "--local", "--list")
        r = self.adopt(inst, "--yes", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("rolled back", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        after = self.fingerprint(inst)
        after["backups"] = before["backups"]                   # an empty stamp folder may remain
        self.assertEqual(before, after)
        self.assertEqual("scratch\n", (inst / "PROVENANCE.md").read_text())
        git(inst, "config", "--unset", "commit.gpgsign")
        r = self.adopt(inst, "--yes")
        self.assertIn("merged:", r.stdout)

    def test_a_case_only_clash_with_a_framework_path_is_refused(self):
        inst = self.make_old_instance()
        git(inst, "config", "core.ignorecase", "true")
        git(inst, "mv", "README.md", "readme.tmp"); git(inst, "mv", "readme.tmp", "readme.md")
        git(inst, "commit", "-q", "-m", "lower-case readme")
        r = self.adopt(inst, "--dry-run")
        self.assertIn("case clash: readme.md (this instance) vs README.md (the framework)", r.stdout)
        self.assertNotIn("replaced: README.md", r.stdout)
        head = git(inst, "rev-parse", "HEAD")
        r = self.adopt(inst, "--yes", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("by case", r.stderr)
        self.assertEqual(head, git(inst, "rev-parse", "HEAD"))
        self.assertEqual("", git(inst, "status", "--porcelain"))

    def test_the_dispatchers_run_only_run_parts_names(self):
        inst = self.clone_instance()
        self.bootstrap(inst, "--commit")
        git(inst, "config", "core.hooksPath", ".githooks")
        d = inst / ".githooks.d" / "pre-commit"
        self.write(d, "10-ok", '#!/bin/sh\ntouch "$(git rev-parse --show-toplevel)/.git/ran-10"\n', 0o755)
        for bad in ("20-gate.orig", "30-gate~", ".40-swap.swp"):
            self.write(d, bad, "#!/bin/sh\nexit 1\n", 0o755)
        self.write(d, "50-not-executable", "#!/bin/sh\nexit 1\n")
        (inst / "memory" / "raw" / "x.md").write_text("x\n")
        git(inst, "add", "memory/raw/x.md")
        r = run(["git", "commit", "-q", "-m", "x"], inst, check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((inst / ".git" / "ran-10").is_file())

    def test_the_gate_keeps_its_full_scope_in_a_framework_developer_checkout(self):
        dev = self.clone_instance("dev")
        self.bootstrap(dev, "--local")                       # contract on disk, excluded, untracked
        git(dev, "remote", "add", "upstream", str(self.upstream))
        git(dev, "fetch", "-q", "upstream")
        (dev / "scripts" / "new_tool.py").write_text(f"# ask about {KEY}\n")
        git(dev, "add", "scripts/new_tool.py")
        r = run(["python3", "scripts/validate_framework.py"], dev, check=False)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("scripts/new_tool.py:1", r.stdout)


# The lifecycle cases are inherited for the fixture, not to run twice.
for _name in [n for n in dir(lifecycle.LifecycleTest) if n.startswith("test_")]:
    setattr(AdoptTest, _name, None)


if __name__ == "__main__":
    unittest.main()
