#!/usr/bin/env python3
"""Adopting an instance made from the retired instance template, end to end.

    python3 -m unittest discover -s tests -p test_adopt_submodule.py

That layout carries the framework as a git submodule (`.meta-os`), mounts the framework's
folders as symlinks into it, and commits the discovery links in `skills/` and
`.claude/skills/`. What must hold beyond tests/test_adopt.py: the framework submodule is
removed, but only when it is the framework by URL and holds nothing its remote lacks;
otherwise it is listed, needs --yes, and is kept, with its repository, in a backup that
works on its own. Committed links are untracked, an instance's own linked skill is never
dropped silently, and a failed run rolls back to exactly the state it started from,
submodule checkout included.
"""
from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

import test_adopt as base
from test_instance_lifecycle import git, run


class TemplateLayoutTest(base.AdoptTest):

    def make_template_instance(self) -> Path:
        old = self.tmp / "old-framework"                     # the framework as the template pinned it
        git(self.tmp, "clone", "-q", str(self.upstream), str(old))
        self.write(old, "skills/old-skill/SKILL.md", "---\nname: old-skill\ndescription: retired\n---\n")
        git(old, "add", "-A"); git(old, "commit", "-q", "-m", "a skill the framework later dropped")
        inst = self.tmp / "tmpl"
        self.write(inst, "CLAUDE.md", "# tmpl — the instance contract\n")
        self.write(inst, "memory/wiki/note.md", "a note\n")
        git(inst, "init", "-q", "-b", "main")
        git(inst, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(old), ".meta-os")
        # the template recorded the public framework's URL; the checkout came from a local copy
        git(inst, "config", "-f", ".gitmodules", "submodule..meta-os.url", base.CANONICAL)
        for name in ("agents", "systems", "templates"):
            (inst / name).symlink_to(Path(".meta-os") / name)
        (inst / "skills").mkdir()
        (inst / ".claude" / "skills").mkdir(parents=True)
        for name in ("graphify", "old-skill", "_index.md"):
            (inst / "skills" / name).symlink_to(Path("..") / ".meta-os" / "skills" / name)
        for name in ("graphify", "old-skill"):
            (inst / ".claude" / "skills" / name).symlink_to(Path("..") / ".." / "skills" / name)
        git(inst, "add", "-A"); git(inst, "commit", "-q", "-m", "from the instance template")
        git(inst, "remote", "add", "upstream", str(self.upstream))
        git(inst, "fetch", "-q", "upstream")
        (inst / "scratch.txt").write_text("the operator's untracked file\n")   # not the adoption's dirt
        return inst

    def test_the_template_layout_drops_the_framework_submodule_and_its_committed_links(self):
        inst = self.make_template_instance()
        out = self.adopt(inst, "--dry-run").stdout
        self.assertIn("framework submodule removed: .meta-os", out)
        self.assertIn("mount removed: skills/graphify -> ../.meta-os/skills/graphify", out)
        self.assertIn("mount removed: skills/_index.md", out)
        self.assertIn("committed discovery links untracked: 1 in skills/, 2 in .claude/skills/", out)
        self.assertIn("(1): old-skill", out)
        r = self.adopt(inst)                                 # nothing here needs --yes
        self.assertIn("done — adopted", r.stdout)
        self.assertEqual("?? scratch.txt", git(inst, "status", "--porcelain"))
        tracked = git(inst, "ls-files").splitlines()
        self.assertFalse(any(p == ".meta-os" or p.startswith(".claude/skills/") for p in tracked))
        self.assertNotIn(".gitmodules", tracked)
        self.assertFalse(os.path.lexists(inst / ".meta-os"))
        self.assertFalse((inst / ".git" / "modules" / ".meta-os").exists())
        self.assertNotIn(".meta-os", git(inst, "config", "--local", "--list"))
        self.assertTrue((inst / "skills" / "graphify" / "SKILL.md").is_file())
        self.assertFalse((inst / "skills" / "graphify").is_symlink())
        self.assertFalse(os.path.lexists(inst / "skills" / "old-skill"))
        self.assertTrue((inst / ".claude" / "skills" / "graphify").is_symlink())   # regenerated, ignored
        self.assertEqual("# tmpl — the instance contract\n", (inst / ".claude" / "CLAUDE.md").read_text())
        r = run(["python3", "scripts/validate_framework.py"], inst, check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("0 commit(s) behind", run(["scripts/upgrade.sh", "--check"], inst).stdout)


    def state(self, inst: Path) -> dict[str, str]:
        out = self.fingerprint(inst)
        out["submodules"] = git(inst, "submodule", "status")
        out["meta-os"] = " ".join(sorted(os.listdir(inst / ".meta-os")))
        out["mounts"] = " ".join(str((inst / n / "_index.md").is_file()) for n in ("agents", "systems"))
        return out

    def test_a_failed_run_restores_the_submodule_checkout_exactly(self):
        inst = self.make_template_instance()
        git(inst, "config", "commit.gpgsign", "true")
        git(inst, "config", "gpg.program", "false")
        before = self.state(inst)
        r = self.adopt(inst, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("rolled back", r.stderr)
        self.assertIn("verified unchanged", r.stderr)
        self.assertEqual(before, self.state(inst))
        self.assertFalse(os.path.lexists(inst / ".meta-os" / ".meta-os"))
        self.assertTrue((inst / "agents" / "_index.md").is_file())       # the mounts resolve again
        self.assertFalse((inst / ".git" / "meta-os-adopt").exists())    # no empty backup left behind
        git(inst, "config", "--unset", "commit.gpgsign")
        self.assertIn("done — adopted", self.adopt(inst).stdout)

    def test_work_that_exists_only_in_the_framework_submodule_is_kept(self):
        inst = self.make_template_instance()
        sub = inst / ".meta-os"
        recorded = git(sub, "rev-parse", "HEAD")
        git(sub, "switch", "-q", "-c", "wip")
        (sub / "MYFIX.md").write_text("a local framework fix, never pushed\n")
        git(sub, "add", "MYFIX.md"); git(sub, "commit", "-q", "-m", "local fix")
        wip = git(sub, "rev-parse", "HEAD")
        git(sub, "switch", "-q", "--detach", recorded)
        with (sub / "README.md").open("a") as fh:
            fh.write("stashed\n")
        git(sub, "stash", "-q")
        self.assertEqual("", git(sub, "status", "--porcelain"))       # looks clean, HEAD == the gitlink
        out = self.adopt(inst, "--dry-run").stdout
        self.assertIn("needs --yes: 1 commit(s) on no remote-tracking branch; a stash", out)
        r = self.adopt(inst, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("refusing", r.stderr)
        r = self.adopt(inst, "--yes")
        self.assertIn("done — adopted", r.stdout)
        homes = list((inst / ".git" / "meta-os-adopt").glob("*/.meta-os"))
        self.assertEqual(1, len(homes))
        home = homes[0]
        self.assertEqual("commit", git(home, "cat-file", "-t", wip))     # the backup works on its own
        self.assertIn("stash", git(home, "stash", "list"))
        self.assertEqual("", git(home, "status", "--porcelain"))

    def test_a_submodule_shaped_like_the_framework_but_from_elsewhere_needs_yes(self):
        inst = self.make_template_instance()
        other = self.tmp / "other-instance"
        git(self.tmp, "clone", "-q", str(self.upstream), str(other))
        git(inst, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(other), "vendor/other")
        git(inst, "commit", "-q", "-m", "vendor another instance")
        out = self.adopt(inst, "--dry-run").stdout
        self.assertIn("framework submodule removed: vendor/other", out)
        self.assertIn("its URL is not the framework's", out)
        r = self.adopt(inst, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue((inst / "vendor" / "other" / "CLAUDE.md").is_file())
        self.assertIn("vendor/other", git(inst, "ls-files", "-s"))

    def test_an_instance_skill_linked_into_skills_is_not_dropped_silently(self):
        inst = self.make_template_instance()
        self.write(inst, "memory/skills/my-skill/SKILL.md", "---\nname: my-skill\ndescription: mine\n---\n")
        (inst / "skills" / "my-skill").symlink_to(Path("..") / "memory" / "skills" / "my-skill")
        git(inst, "add", "-A"); git(inst, "commit", "-q", "-m", "an instance skill, linked in")
        out = self.adopt(inst, "--dry-run").stdout
        self.assertIn("instance skill linked into skills/: skills/my-skill -> ../memory/skills/my-skill", out)
        self.assertNotIn("my-skill,", out.split("no longer discovered")[-1].split("\n")[0])
        r = self.adopt(inst, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("refusing", r.stderr)

    def test_an_upgrade_beside_the_operators_untracked_files_succeeds(self):
        inst = self.clone_instance()
        self.bootstrap(inst, "--commit")
        self.write(inst, "newdir/mine.md", "the operator's own, untracked\n")
        self.upstream_commit("framework adds newdir", {"newdir/_index.md": "---\ntype: index\ntags: [x]\n---\n"})
        r = run(["scripts/upgrade.sh"], inst, check=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("framework self-check", r.stdout)
        self.assertIn("done", r.stdout)


# The inherited cases run in their own modules, not again here.
for _name in [n for n in dir(base.AdoptTest) if n.startswith("test_")]:
    if _name not in TemplateLayoutTest.__dict__:
        setattr(TemplateLayoutTest, _name, None)


if __name__ == "__main__":
    unittest.main()
