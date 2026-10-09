#!/usr/bin/env python3
"""scripts/packs.sh for a pack installed as a Claude Code plugin (`install: plugin`).

    python3 -m unittest tests.test_packs_plugin

Such a pack has no mount: `check` must not expect one, `sync` and `apply` place none, and
`config` reads the pack's `pack.yaml` where Claude Code installed the plugin, found through
`scripts/plugin_root.py`. Each case builds a throwaway instance and a fake Claude Code
config directory (`$CLAUDE_CONFIG_DIR`) holding `plugins/installed_plugins.json` and the
plugin cache laid out as Claude Code lays it out:
`plugins/cache/<marketplace>/<plugin>/<version>/`. No real plugin install is read.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1", "HOME": tempfile.gettempdir(),
}

PACK_YAML = ("name: alpha\nversion: {v}\ndescription: fixture\nconfig:\n"
             "  profile:\n    default: light\n    one_of: light | full\n    doc: \"the profile\"\n"
             "  engine:\n    default: {engine}\n    doc: \"the engine\"\n")


class PluginPackTest(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="metaos-plugin-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.inst = self.tmp / "inst"
        (self.inst / "scripts").mkdir(parents=True)
        for script in ("packs.sh", "plugin_root.py"):
            shutil.copy2(ROOT / "scripts" / script, self.inst / "scripts" / script)
        (self.inst / "CLAUDE.md").write_text("# framework\n")
        (self.inst / "systems").mkdir()
        (self.inst / "systems" / "packs.yaml").write_text(
            "packs:\n  alpha:\n    plugin: meta-alpha@market\n    provides: [alpha-one]\n    status: available\n")
        (self.inst / "skills" / "skill-builder").mkdir(parents=True)
        (self.inst / "skills" / "skill-builder" / "SKILL.md").write_text("---\nname: skill-builder\n---\n")
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.inst, check=True,
                       env={**os.environ, **GIT_ENV})
        self.config_dir = self.tmp / "claude"
        self.installed: dict[str, list] = {}
        self.write_installed()

    # --- helpers -------------------------------------------------------------------------

    def cache(self, plugin="meta-alpha", market="market", version="1.2.0", engine="claude") -> Path:
        root = self.config_dir / "plugins" / "cache" / market / plugin / version
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": plugin}))
        (root / "pack.yaml").write_text(PACK_YAML.format(v=version, engine=engine))
        (root / "skills" / "alpha-one").mkdir(parents=True)
        (root / "skills" / "alpha-one" / "SKILL.md").write_text("---\nname: alpha-one\n---\n")
        return root

    def install(self, plugin_id="meta-alpha@market", project: Path | None = None, **kw) -> Path:
        name, market = plugin_id.split("@")
        root = self.cache(plugin=name, market=market, **kw)
        entry = {"scope": "user", "installPath": str(root), "version": kw.get("version", "1.2.0")}
        if project:
            entry.update(scope="project", projectPath=str(project))
        self.installed.setdefault(plugin_id, []).append(entry)
        self.write_installed()
        return root

    def write_installed(self):
        f = self.config_dir / "plugins" / "installed_plugins.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"version": 2, "plugins": self.installed}))

    def manifest(self, entry: str):
        (self.inst / ".packs.yaml").write_text("packs:\n  alpha:\n" + entry)

    def packs(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        base = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
        return subprocess.run(["scripts/packs.sh", *args], cwd=self.inst, capture_output=True, text=True,
                              timeout=120, env={**base, **GIT_ENV, "CLAUDE_CONFIG_DIR": str(self.config_dir),
                                                **(env or {})})

    def links(self) -> list[str]:
        return [p.name for p in (self.inst / "skills").iterdir() if p.is_symlink()]

    # --- config ----------------------------------------------------------------------------

    def test_config_reads_the_schema_and_defaults_from_the_plugin_install(self):
        self.install()
        self.manifest("    install: plugin\n    config:\n      profile: full\n")
        r = self.packs("config", "alpha")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), ["profile=full", "engine=claude"])
        self.assertEqual(r.stderr, "")
        self.assertEqual(self.packs("config", "alpha", "engine").stdout, "claude\n")

    def test_config_validates_against_the_plugins_pack_yaml(self):
        self.install()
        self.manifest("    install: plugin\n    config:\n      profile: heavy\n      typo: x\n")
        r = self.packs("config", "alpha")
        self.assertEqual(r.returncode, 1)
        self.assertIn("alpha.profile='heavy' not in {light|full}", r.stderr)
        self.assertIn("alpha.typo in .packs.yaml is not a key of", r.stderr)
        self.assertNotEqual(self.packs("config", "alpha", "nokey").returncode, 0)

    def test_config_without_the_plugin_prints_the_instance_values_and_warns_once(self):
        self.manifest("    install: plugin\n    config:\n      profile: full\n")
        r = self.packs("config", "alpha")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), ["profile=full"])
        self.assertEqual(len(r.stderr.splitlines()), 1, r.stderr)
        self.assertIn("'meta-alpha@market' of pack 'alpha' is not installed", r.stderr)
        self.assertEqual(self.packs("config", "alpha", "profile").stdout, "full\n")
        r = self.packs("config", "alpha", "engine")          # a default nobody can read: empty, not a failure
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_the_manifest_plugin_overrides_the_registry_plugin(self):
        self.install()                                       # the registry's, default engine claude
        self.install("meta-alpha@fork", engine="grok")
        self.manifest("    install: plugin\n    plugin: meta-alpha@fork\n")
        self.assertEqual(self.packs("config", "alpha", "engine").stdout, "grok\n")

    def test_a_project_install_counts_only_for_its_project_and_wins_there(self):
        self.install(project=self.tmp / "elsewhere", engine="other")
        self.manifest("    install: plugin\n")
        self.assertIn("not installed", self.packs("config", "alpha").stderr)
        self.install(version="1.0.0", engine="user")
        self.install(version="2.0.0", engine="mine", project=self.inst)
        self.assertEqual(self.packs("config", "alpha", "engine").stdout, "mine\n")

    def test_claude_plugin_root_wins_only_when_it_is_this_plugin(self):
        self.install(engine="cached")
        own = self.cache(version="9.9.9", market="dev", engine="session")
        other = self.cache(plugin="meta-beta", engine="beta")
        self.manifest("    install: plugin\n")
        self.assertEqual(self.packs("config", "alpha", "engine", env={"CLAUDE_PLUGIN_ROOT": str(own)}).stdout,
                         "session\n")
        self.assertEqual(self.packs("config", "alpha", "engine", env={"CLAUDE_PLUGIN_ROOT": str(other)}).stdout,
                         "cached\n")

    def test_install_inside_the_config_block_is_a_config_value_not_the_install_mode(self):
        self.install()
        self.manifest("    config:\n      install: plugin\n")
        r = self.packs("config", "alpha")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not mounted", r.stderr)

    # --- check, sync, apply ------------------------------------------------------------------

    def test_check_sync_and_apply_expect_no_mount_for_a_plugin_pack(self):
        self.manifest("    install: plugin\n")
        r = self.packs("check")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("not mounted", r.stderr)
        r = self.packs("apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("mounting", r.stdout)
        self.assertFalse((self.inst / ".packs" / "alpha").exists())
        self.assertIn("0 pack links", self.packs("sync").stdout)
        self.assertEqual(self.links(), [])

    def test_check_reports_a_plugin_pack_that_is_also_mounted_or_names_no_plugin(self):
        (self.inst / ".packs" / "alpha").mkdir(parents=True)
        (self.inst / ".packs" / "alpha" / "pack.yaml").write_text(PACK_YAML.format(v="0", engine="x"))
        self.manifest("    install: plugin\n")
        r = self.packs("check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("installed as a plugin and also mounted: alpha", r.stderr)
        (self.inst / "systems" / "packs.yaml").write_text("packs:\n")
        shutil.rmtree(self.inst / ".packs")
        r = self.packs("check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("installed as a plugin but names none: alpha", r.stderr)


if __name__ == "__main__":
    unittest.main()
