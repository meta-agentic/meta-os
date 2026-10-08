#!/usr/bin/env python3
"""scripts/packs.sh in the one-repository layout, against local fixture packs.

    python3 -m unittest tests.test_packs_sh

Each case builds a throwaway instance in a temp dir: a minimal framework tree (a real
`skills/` folder with one framework skill, `systems/packs.yaml` as an empty registry,
the real `scripts/packs.sh`), and local pack repositories mounted over the file
transport — no network, never a real checkout. What is pinned here is the mount model
`systems/packs.md` states: pack skills are linked in BESIDE the framework's real skill
folders, a real folder always wins a name, the links are generated and excluded from
git by the script itself, and a dangling or off-pin mount is refused rather than skipped.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKS_SH = ROOT / "scripts" / "packs.sh"

PACKS = {
    "alpha": ["alpha-one", "alpha-two", "skill-builder"],   # skill-builder collides with the framework's
    "beta": ["beta-one", "alpha-two"],                       # alpha-two collides with alpha's
}

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "protocol.file.allow",
    "GIT_CONFIG_VALUE_0": "always",
    "GIT_CONFIG_NOSYSTEM": "1", "HOME": tempfile.gettempdir(),
}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True, timeout=60, env={**os.environ, **GIT_ENV}).stdout


class PacksShFixture(unittest.TestCase):
    """The throwaway instance and its local pack repositories; no cases of its own.

    A subclass changes the packs with `PACKS` and a pack's manifest with `pack_yaml`.
    """

    PACKS = PACKS

    def pack_yaml(self, name: str) -> str | None:
        """The pack's pack.yaml, or None for a pack that ships none."""
        return (f"name: {name}\nversion: 0.1.0\ndescription: fixture\nconfig:\n"
                "  profile:\n    default: light\n    one_of: light | full\n    doc: \"the profile\"\n")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="metaos-packs-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.urls = {}
        for name, skills in self.PACKS.items():
            repo = self.tmp / "src" / name
            for s in skills:
                (repo / "skills" / s).mkdir(parents=True)
                (repo / "skills" / s / "SKILL.md").write_text(f"---\nname: {s}\n---\n")
            pack_yaml = self.pack_yaml(name)
            if pack_yaml is not None:
                (repo / "pack.yaml").write_text(pack_yaml)
            git(repo, "init", "-q", "-b", "main")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "init")
            self.urls[name] = str(repo)

        self.inst = self.tmp / "inst"
        (self.inst / "scripts").mkdir(parents=True)
        shutil.copy2(PACKS_SH, self.inst / "scripts" / "packs.sh")
        (self.inst / "CLAUDE.md").write_text("# framework\n")
        (self.inst / "systems").mkdir()
        (self.inst / "systems" / "packs.yaml").write_text("packs:\n")
        (self.inst / "skills" / "skill-builder").mkdir(parents=True)
        (self.inst / "skills" / "skill-builder" / "SKILL.md").write_text("---\nname: skill-builder\n---\n")
        (self.inst / "skills" / "_index.md").write_text("# skills\n")
        (self.inst / ".gitignore").write_text(".claude/*\n!.claude/CLAUDE.md\n")
        git(self.inst, "init", "-q", "-b", "main")
        git(self.inst, "add", ".")
        git(self.inst, "commit", "-q", "-m", "framework")

    def packs(self, *args: str, check=True) -> subprocess.CompletedProcess:
        return subprocess.run(["scripts/packs.sh", *args], cwd=self.inst, check=check,
                              capture_output=True, text=True, timeout=120,
                              env={**os.environ, **GIT_ENV})

    def manifest(self, *names: str):
        text = "packs:\n" + "".join(f"  {n}:\n    repo: {self.urls[n]}\n" for n in names)
        (self.inst / ".packs.yaml").write_text(text)

    def links(self) -> dict[str, str]:
        return {p.name: os.readlink(p) for p in (self.inst / "skills").iterdir() if p.is_symlink()}

    def mount_and_commit(self, *names: str):
        self.manifest(*(names or ("alpha",)))
        self.packs("apply")
        git(self.inst, "add", ".gitmodules", ".packs", ".packs.yaml")
        git(self.inst, "commit", "-q", "-m", "mount")


class PacksShTest(PacksShFixture):

    # --- mount model --------------------------------------------------------------------

    def test_apply_links_pack_skills_beside_the_framework_skills(self):
        self.manifest("alpha")
        out = self.packs("apply").stdout
        self.assertIn("state matches", out)
        links = self.links()
        self.assertEqual(links["alpha-one"], "../.packs/alpha/skills/alpha-one")
        self.assertTrue((self.inst / "skills" / "alpha-one" / "SKILL.md").is_file())
        self.assertFalse((self.inst / "skills" / "skill-builder").is_symlink())  # framework wins
        self.assertTrue((self.inst / ".claude" / "skills" / "alpha-one").is_symlink())
        self.assertTrue((self.inst / ".claude" / "skills" / "skill-builder").is_symlink())

    def test_the_links_are_generated_and_never_tracked(self):
        self.manifest("alpha")
        self.packs("apply")
        exclude = (self.inst / ".git" / "info" / "exclude").read_text()
        self.assertIn("/skills/alpha-one", exclude)
        self.assertIn("/skills/alpha-two", exclude)
        self.assertNotIn("/skills/skill-builder", exclude)
        git(self.inst, "add", "-A")
        staged = git(self.inst, "diff", "--cached", "--name-only").splitlines()
        self.assertNotIn("skills/alpha-one", staged)
        self.assertNotIn(".claude/skills/alpha-one", staged)
        self.assertIn(".packs.yaml", staged)
        self.assertIn(".gitmodules", staged)

    def test_apply_is_idempotent_and_check_passes(self):
        self.manifest("alpha")
        self.packs("apply")
        before = self.links()
        self.packs("apply")
        self.assertEqual(before, self.links())
        self.assertIn("mounts match", self.packs("check").stdout)

    def test_later_pack_loses_a_name_to_the_earlier_one_with_a_warning(self):
        self.manifest("alpha", "beta")
        r = self.packs("apply")
        self.assertEqual(self.links()["alpha-two"], "../.packs/alpha/skills/alpha-two")
        self.assertEqual(self.links()["beta-one"], "../.packs/beta/skills/beta-one")
        self.assertIn("shadowed", r.stderr)

    def test_remove_from_the_manifest_unmounts_and_drops_the_links(self):
        self.manifest("alpha", "beta")
        self.packs("apply")
        self.manifest("alpha")
        self.packs("apply")
        self.assertFalse((self.inst / ".packs" / "beta").exists())
        self.assertNotIn("beta-one", self.links())
        self.assertNotIn("/skills/beta-one", (self.inst / ".git" / "info" / "exclude").read_text())

    # --- refusals ------------------------------------------------------------------------------

    def test_a_dangling_pack_mount_is_refused(self):
        self.manifest("alpha")
        self.packs("apply")
        shutil.rmtree(self.inst / ".packs" / "alpha")
        (self.inst / ".packs" / "alpha").symlink_to("/nowhere/alpha")
        links_before = self.links()
        # the mount itself named, not only a link into it or the recorded pin
        mount = "dangling mount: .packs/alpha -> /nowhere/alpha"
        for cmd, needle in ((("check",), mount), (("sync",), mount), (("apply",), mount),
                            (("config", "alpha"), "dangling mount (.packs/alpha -> /nowhere/alpha)")):
            with self.subTest(cmd=cmd):
                r = self.packs(*cmd, check=False)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn(needle, r.stderr)
        self.assertEqual(self.links(), links_before, "a refused sync must not rebuild the links")

    def test_check_refuses_a_stale_pin_and_apply_restores_it(self):
        self.manifest("alpha")
        self.packs("apply")
        git(self.inst, "add", "-A"); git(self.inst, "commit", "-q", "-m", "mount alpha")
        src = Path(self.urls["alpha"])
        (src / "skills" / "alpha-one" / "SKILL.md").write_text("---\nname: alpha-one\n---\nv2\n")
        git(src, "commit", "-qam", "v2")
        git(self.inst / ".packs" / "alpha", "pull", "-q", "origin", "main")
        r = self.packs("check", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("stale mount", r.stderr)
        self.packs("apply")
        self.assertIn("mounts match", self.packs("check").stdout)

    def test_pack_names_are_validated_before_they_become_paths(self):
        self.mount_and_commit("alpha", "beta")
        for cmd in (("remove", "alpha/.."), ("remove", "../x"), ("remove", "a b"),
                    ("add", "../x", "/nowhere"), ("update", "alpha/.."), ("config", "../alpha")):
            with self.subTest(cmd=cmd):
                r = self.packs(*cmd, check=False)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("invalid pack name", r.stderr)
        for name in PACKS:   # remove 'alpha/..' would have deinit -f'd every pack
            self.assertTrue(any((self.inst / ".packs" / name).iterdir()), name)

    def test_a_symlink_where_a_pin_is_recorded_is_refused(self):
        # the old hand-made layout: .packs/<pack> -> a development clone
        self.mount_and_commit()
        dev = self.tmp / "dev-alpha"
        git(self.tmp, "clone", "-q", self.urls["alpha"], str(dev))
        git(self.inst, "submodule", "deinit", "-q", "-f", ".packs/alpha")
        (self.inst / ".packs" / "alpha").rmdir()
        (self.inst / ".packs" / "alpha").symlink_to(dev)
        for cmd in ("check", "apply"):
            with self.subTest(cmd=cmd):
                r = self.packs(cmd, check=False)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn("symlink mount: .packs/alpha", r.stderr)

    def test_a_modified_mount_is_refused_and_remove_keeps_its_changes(self):
        self.mount_and_commit()
        skill = self.inst / ".packs" / "alpha" / "skills" / "alpha-one" / "SKILL.md"
        skill.write_text(skill.read_text() + "local edit\n")
        r = self.packs("check", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("modified mount: .packs/alpha", r.stderr)
        r = self.packs("remove", "alpha", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("local changes", r.stderr)
        self.assertIn("local edit", skill.read_text())

    def test_sync_refuses_a_symlinked_claude_skills(self):
        self.manifest("alpha")
        self.packs("apply")
        cs = self.inst / ".claude" / "skills"
        shutil.rmtree(cs)
        cs.symlink_to(self.tmp)
        r = self.packs("sync", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(".claude/skills is a symlink", r.stderr)

    def test_remove_in_a_linked_worktree_drops_its_module_gitdir(self):
        self.mount_and_commit("alpha", "beta")
        wt = self.tmp / "wt"
        git(self.inst, "worktree", "add", "-q", str(wt))
        run = lambda *a: subprocess.run(["scripts/packs.sh", *a], cwd=wt, capture_output=True,
                                        text=True, timeout=120, env={**os.environ, **GIT_ENV})
        r = run("apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        gd = Path(git(wt, "rev-parse", "--path-format=absolute", "--git-path", "modules/.packs/beta").strip())
        self.assertTrue(gd.is_dir(), gd)
        r = run("remove", "beta")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(gd.exists(), "the worktree's module gitdir must go with the pack")
        self.assertNotIn("  beta:", (wt / ".packs.yaml").read_text(), "remove drops the manifest entry")
        self.assertIn("  alpha:", (wt / ".packs.yaml").read_text())
        for d in ("skills", ".claude/skills"):
            self.assertFalse(os.path.lexists(wt / d / "beta-one"), f"{d}/beta-one must go with the pack")
            self.assertTrue((wt / d / "alpha-one").is_symlink(), f"{d}/alpha-one stays")

    def test_an_uninitialised_submodule_is_refused_then_apply_initialises_it(self):
        # what a fresh clone or a new worktree holds: the pin recorded, the folder empty
        self.mount_and_commit()
        git(self.inst, "submodule", "deinit", "-q", "-f", ".packs/alpha")
        self.assertEqual(list((self.inst / ".packs" / "alpha").iterdir()), [])
        for cmd in ("check", "sync"):
            with self.subTest(cmd=cmd):
                r = self.packs(cmd, check=False)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn("dangling mount: .packs/alpha is empty", r.stderr)
        out = self.packs("apply").stdout
        self.assertIn("initialising 'alpha'", out)
        self.assertTrue((self.inst / "skills" / "alpha-one" / "SKILL.md").is_file())
        self.assertIn("mounts match", self.packs("check").stdout)

    def test_a_dangling_skill_link_is_refused_by_check(self):
        self.manifest("alpha")
        self.packs("apply")
        (self.inst / "skills" / "alpha-old").symlink_to("/nonexistent/alpha-old")
        r = self.packs("check", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("dangling mount: skills/alpha-old", r.stderr)

    def test_check_refuses_a_declared_pack_that_is_not_mounted(self):
        self.manifest("alpha")
        self.packs("apply")
        with (self.inst / ".packs.yaml").open("a") as fh:
            fh.write("  ghost:\n    repo: /nowhere\n")
        r = self.packs("check", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("declared but not mounted: ghost", r.stderr)

    def test_apply_fails_when_a_declared_pack_cannot_mount(self):
        self.manifest("alpha")
        with (self.inst / ".packs.yaml").open("a") as fh:
            fh.write(f"  ghost:\n    repo: {self.tmp / 'no-such-repo'}\n")
        r = self.packs("apply", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not mounted: ghost", r.stderr)
        self.assertNotIn("state matches", r.stdout)
        self.assertTrue((self.inst / "skills" / "alpha-one").is_symlink(), "the other packs still mount")

    def test_update_stages_the_bump_so_apply_keeps_it(self):
        self.mount_and_commit()
        src = Path(self.urls["alpha"])
        (src / "CHANGELOG").write_text("bump\n")
        git(src, "add", ".")
        git(src, "commit", "-q", "-m", "bump")
        new = git(src, "rev-parse", "HEAD").strip()
        self.packs("update", "alpha")
        self.assertIn(".packs/alpha", git(self.inst, "diff", "--cached", "--name-only"))
        self.assertIn("mounts match", self.packs("check").stdout)
        self.packs("apply")
        self.assertEqual(git(self.inst / ".packs" / "alpha", "rev-parse", "HEAD").strip(), new)

    # --- the union of skills/ ----------------------------------------------------------

    def test_check_refuses_a_union_link_with_a_wrong_target_until_sync(self):
        self.manifest("alpha")
        self.packs("apply")
        link = self.inst / "skills" / "alpha-two"
        link.unlink()
        link.symlink_to("../.packs/alpha/skills/alpha-one")    # resolves, but to the wrong skill
        r = self.packs("check", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("pack links are stale", r.stderr)
        self.packs("sync")
        self.assertEqual(os.readlink(link), "../.packs/alpha/skills/alpha-two")
        self.assertIn("mounts match", self.packs("check").stdout)

    def test_an_instance_owned_skill_shadows_a_pack_skill_and_check_passes(self):
        self.manifest("alpha")
        self.packs("apply")
        own = self.inst / "skills" / "alpha-one"
        own.unlink()
        own.mkdir()
        (own / "SKILL.md").write_text("---\nname: alpha-one\n---\nthe instance's own\n")
        r = self.packs("sync")
        self.assertIn("shadowed by the real skills/alpha-one", r.stderr)
        self.assertFalse(own.is_symlink())
        self.assertIn("the instance's own", (own / "SKILL.md").read_text())
        self.assertNotIn("/skills/alpha-one", (self.inst / ".git" / "info" / "exclude").read_text())
        self.assertIn("mounts match", self.packs("check").stdout)

    # --- the instance's ignore rules -----------------------------------------------------

    def test_sync_applies_the_instance_ignore_rules_and_follows_their_edits(self):
        (self.inst / ".gitignore.instance").write_text("# mine\nlocal-cache/\n")
        out = self.packs("sync").stdout
        self.assertIn("1 instance ignore rule(s) applied", out)
        (self.inst / "local-cache").mkdir()
        (self.inst / "local-cache" / "x").write_text("x\n")
        (self.inst / "scratch.tmp").write_text("x\n")
        status = git(self.inst, "status", "--porcelain", "--untracked-files=all")
        self.assertNotIn("local-cache/", status)
        self.assertIn("scratch.tmp", status)
        (self.inst / ".gitignore.instance").write_text("*.tmp\n")
        self.packs("sync")
        status = git(self.inst, "status", "--porcelain", "--untracked-files=all")
        self.assertIn("local-cache/x", status)              # the old rule is gone, not appended to
        self.assertNotIn("scratch.tmp", status)
        exclude = (self.inst / ".git" / "info" / "exclude").read_text()
        self.assertEqual(1, exclude.count(".gitignore.instance (edit that file"))

    def test_config_resolves_the_instance_over_the_pack_default_and_validates_enums(self):
        self.manifest("alpha")
        self.packs("apply")
        self.assertEqual(self.packs("config", "alpha", "profile").stdout.strip(), "light")
        (self.inst / ".packs.yaml").write_text(
            f"packs:\n  alpha:\n    repo: {self.urls['alpha']}\n    config:\n      profile: full\n")
        self.assertEqual(self.packs("config", "alpha", "profile").stdout.strip(), "full")
        (self.inst / ".packs.yaml").write_text(
            f"packs:\n  alpha:\n    repo: {self.urls['alpha']}\n    config:\n      profile: wrong\n")
        r = self.packs("config", "alpha", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not in {light|full}", r.stderr)


if __name__ == "__main__":
    unittest.main()
