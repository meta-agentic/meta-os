#!/usr/bin/env python3
"""scripts/packs.sh with first-party packs that live in a monorepo, and with renamed pack keys.

    python3 -m unittest tests.test_packs_monorepo

Same throwaway instance as tests/test_packs_sh.py, against a local fixture monorepo with two
packs under plugins/. What is pinned: a registry `path:` (or a manifest `path:`) makes the pack
the directory inside the mounted repository, never the whole mount; only that directory is
checked out; each pack links only its own skills; a renamed key keeps working with a warning,
`migrate` rewrites the manifest and moves the mount, and a second `check` is clean.
"""
from __future__ import annotations

import subprocess
import unittest

from test_packs_sh import PacksShFixture, git

MONO_PACKS = {"disc-a": ["a-one", "a-two"], "disc-b": ["b-one"]}


class MonorepoTest(PacksShFixture):
    PACKS: dict = {}

    def setUp(self):
        super().setUp()
        mono = self.tmp / "src" / "mono"
        for pack, skills in MONO_PACKS.items():
            root = mono / "plugins" / pack
            for s in skills:
                (root / "skills" / s).mkdir(parents=True)
                (root / "skills" / s / "SKILL.md").write_text(f"---\nname: {s}\n---\n")
            (root / "pack.yaml").write_text(self.pack_yaml(pack))
        (mono / "README.md").write_text("monorepo\n")
        git(mono, "init", "-q", "-b", "main")
        git(mono, "add", ".")
        git(mono, "commit", "-q", "-m", "init")
        self.mono = str(mono)
        self.registry()

    def registry(self, a_extra: str = "", b_path: str = "plugins/disc-b"):
        (self.inst / "systems" / "packs.yaml").write_text(
            "packs:\n"
            f"  disc-a:\n    renamed-from: [old-a]\n    repo: {self.mono}\n    path: plugins/disc-a\n"
            f"    provenance: first-party\n    license: MIT\n    status: available\n{a_extra}"
            f"  disc-b:\n    renamed-from: [old-b, older-b]\n    repo: {self.mono}\n    path: {b_path}\n"
            "    provenance: first-party\n    license: MIT\n    status: available\n")
        git(self.inst, "add", ".")
        git(self.inst, "commit", "-q", "-m", "registry")

    def write_manifest(self, text: str):
        (self.inst / ".packs.yaml").write_text("packs:\n" + text)

    # --- a pack that lives in a subdirectory ------------------------------------------

    def test_add_mounts_the_monorepo_and_reads_only_the_pack_directory(self):
        self.packs("add", "disc-a")
        links = self.links()
        self.assertEqual(links["a-one"], "../.packs/disc-a/plugins/disc-a/skills/a-one")
        self.assertNotIn("b-one", links, "a sibling pack's skills are not this pack's")
        self.assertTrue((self.inst / "skills" / "a-two" / "SKILL.md").is_file())
        self.assertIn("disc-a", self.packs("list").stdout)
        self.assertIn("(2 skills)", self.packs("list").stdout)

    def test_only_the_packs_directory_is_checked_out(self):
        if "sparse-checkout" not in subprocess.run(["git", "help", "-a"], capture_output=True, text=True).stdout:
            self.skipTest("this git has no sparse-checkout; the whole tree is checked out, which only costs space")
        self.packs("add", "disc-a")
        mount = self.inst / ".packs" / "disc-a" / "plugins"
        self.assertTrue((mount / "disc-a").is_dir())
        self.assertFalse((mount / "disc-b").exists())

    def test_a_whole_tree_checkout_still_links_only_the_pack_directory(self):
        """Without sparse-checkout (an older git, a CI checkout) the sibling's files are on disk too."""
        self.packs("add", "disc-a")
        git(self.inst / ".packs" / "disc-a", "sparse-checkout", "disable")
        self.assertTrue((self.inst / ".packs" / "disc-a" / "plugins" / "disc-b" / "skills" / "b-one").is_dir())
        self.packs("sync")
        self.assertEqual(sorted(self.links()), ["a-one", "a-two"])

    def test_two_packs_of_one_monorepo_mount_side_by_side_and_apply_is_idempotent(self):
        self.write_manifest(f"  disc-a:\n    repo: {self.mono}\n  disc-b:\n    repo: {self.mono}\n")
        self.assertIn("state matches", self.packs("apply").stdout)
        links = self.links()
        self.assertEqual(links["b-one"], "../.packs/disc-b/plugins/disc-b/skills/b-one")
        self.assertEqual(links["a-one"], "../.packs/disc-a/plugins/disc-a/skills/a-one")
        git(self.inst, "add", ".gitmodules", ".packs", ".packs.yaml")
        git(self.inst, "commit", "-q", "-m", "mount")
        self.assertIn("state matches", self.packs("apply").stdout)
        self.assertIn("check: mounts match", self.packs("check").stdout)

    def test_config_reads_the_pack_yaml_inside_the_path(self):
        self.write_manifest(f"  disc-a:\n    repo: {self.mono}\n    config:\n      profile: full\n")
        self.packs("apply")
        self.assertEqual(self.packs("config", "disc-a", "profile").stdout.strip(), "full")
        self.assertEqual(self.packs("config", "disc-a").stdout.splitlines(), ["profile=full"])

    def test_a_path_the_repository_does_not_have_is_refused_by_name(self):
        self.registry(b_path="plugins/not-there")
        r = self.packs("add", "disc-b", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("plugins/not-there is not in", r.stderr)

    def test_a_path_that_climbs_out_of_the_mount_is_refused(self):
        self.write_manifest(f"  disc-a:\n    repo: {self.mono}\n    path: ../../etc\n")
        for cmd in ("check", "apply"):
            r = self.packs(cmd, check=False)
            self.assertNotEqual(r.returncode, 0, cmd)
            self.assertIn("must be a plain relative directory", r.stderr)

    def test_the_manifest_path_wins_over_the_registry(self):
        self.write_manifest(f"  disc-a:\n    repo: {self.mono}\n    path: plugins/disc-b\n")
        self.packs("apply")
        self.assertIn("b-one", self.links())
        self.assertNotIn("a-one", self.links())

    def test_a_mount_that_lost_its_path_after_a_pin_move_is_refused(self):
        self.write_manifest(f"  disc-a:\n    repo: {self.mono}\n")
        self.packs("apply")
        (self.inst / "systems" / "packs.yaml").write_text(
            (self.inst / "systems" / "packs.yaml").read_text().replace("plugins/disc-a", "plugins/moved", 1))
        r = self.packs("check", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("dangling mount: .packs/disc-a has no plugins/moved", r.stderr)

    # --- renamed keys -----------------------------------------------------------------

    def old_instance(self):
        """An instance still keyed old-a, mounted and committed, the way it was before the rename."""
        (self.inst / "systems" / "packs.yaml").write_text(
            f"packs:\n  old-a:\n    repo: {self.mono}\n    path: plugins/disc-a\n    status: available\n")
        git(self.inst, "add", ".")
        git(self.inst, "commit", "-q", "-m", "registry before the rename")
        self.write_manifest(f"  old-a:\n    repo: {self.mono}\n    config:\n      profile: full\n")
        self.packs("apply")
        git(self.inst, "add", ".gitmodules", ".packs", ".packs.yaml")
        git(self.inst, "commit", "-q", "-m", "mount")
        self.registry()          # the registry now carries the new key with renamed-from

    def test_an_instance_on_the_old_key_still_passes_check_with_a_deprecation_warning(self):
        self.old_instance()
        r = self.packs("check")
        self.assertIn("check: mounts match", r.stdout)
        self.assertIn("deprecated pack key: 'old-a' is now 'disc-a'", r.stderr)
        self.assertIn("migrate", r.stderr)

    def test_either_spelling_reads_the_same_config(self):
        self.old_instance()
        old = self.packs("config", "old-a").stdout
        new = self.packs("config", "disc-a").stdout
        self.assertEqual(old, new)
        self.assertEqual(old.strip(), "profile=full")

    def test_migrate_rewrites_the_manifest_and_moves_the_mount_and_a_second_check_is_clean(self):
        self.old_instance()
        out = self.packs("migrate").stdout
        self.assertIn("migrate: old-a -> disc-a", out)
        manifest = (self.inst / ".packs.yaml").read_text()
        self.assertIn("  disc-a:\n", manifest)
        self.assertNotIn("old-a", manifest)
        self.assertIn("profile: full", manifest, "the config block moves with its entry")
        self.assertTrue((self.inst / ".packs" / "disc-a" / "plugins" / "disc-a" / "pack.yaml").is_file())
        self.assertFalse((self.inst / ".packs" / "old-a").exists())
        self.assertIn(".packs/disc-a", (self.inst / ".gitmodules").read_text())
        self.assertEqual(self.links()["a-one"], "../.packs/disc-a/plugins/disc-a/skills/a-one")
        git(self.inst, "add", "-A", ".gitmodules", ".packs", ".packs.yaml")
        git(self.inst, "commit", "-q", "-m", "migrated")
        r = self.packs("check")
        self.assertIn("check: mounts match", r.stdout)
        self.assertNotIn("deprecated", r.stderr)
        self.assertIn("nothing to do", self.packs("migrate").stdout)
        self.assertIn("state matches", self.packs("apply").stdout)

    def test_migrate_refuses_an_instance_that_holds_both_keys(self):
        self.write_manifest(f"  old-a:\n    repo: {self.mono}\n  disc-a:\n    repo: {self.mono}\n")
        r = self.packs("migrate", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("both 'old-a' and 'disc-a'", r.stderr)
        self.assertIn("  old-a:", (self.inst / ".packs.yaml").read_text(), "nothing was rewritten")

    def test_every_old_spelling_of_a_pack_is_found(self):
        self.write_manifest(f"  older-b:\n    repo: {self.mono}\n")
        self.assertIn("'older-b' is now 'disc-b'", self.packs("check", check=False).stderr)
        self.assertIn("migrate: older-b -> disc-b", self.packs("migrate").stdout)


if __name__ == "__main__":
    unittest.main()
