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


class PacksShTest(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="metaos-packs-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.urls = {}
        for name, skills in PACKS.items():
            repo = self.tmp / "src" / name
            for s in skills:
                (repo / "skills" / s).mkdir(parents=True)
                (repo / "skills" / s / "SKILL.md").write_text(f"---\nname: {s}\n---\n")
            (repo / "pack.yaml").write_text(
                f"name: {name}\nversion: 0.1.0\ndescription: fixture\nconfig:\n"
                "  profile:\n    default: light\n    one_of: light | full\n    doc: \"the profile\"\n")
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
        r = self.packs("sync", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("dangling mount", r.stderr)

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
        for bad in ("alpha/..", "../x", "a b"):
            r = self.packs("remove", bad, check=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("invalid pack name", r.stderr)

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
