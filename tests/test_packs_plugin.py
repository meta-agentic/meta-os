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
    "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "protocol.file.allow", "GIT_CONFIG_VALUE_0": "always",
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
        for script in ("packs.sh", "packs_plugin.sh", "plugin_root.py"):
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

    def packs(self, *args: str, env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
        base = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
        return subprocess.run(["scripts/packs.sh", *args], cwd=cwd or self.inst, capture_output=True, text=True,
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
        self.assertIn("plugin 'meta-alpha@market' of pack 'alpha': not installed here", r.stderr)
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

    def test_claude_plugin_root_wins_only_when_it_is_this_plugin_from_this_marketplace(self):
        self.install(engine="cached")
        own = self.cache(version="9.9.9", engine="session")
        other = self.cache(plugin="meta-beta", engine="beta")
        namesake = self.cache(version="9.9.9", market="elsewhere", engine="namesake")
        self.manifest("    install: plugin\n")
        for root, want in ((own, "session"), (other, "cached"), (namesake, "cached")):
            r = self.packs("config", "alpha", "engine", env={"CLAUDE_PLUGIN_ROOT": str(root)})
            self.assertEqual(r.stdout, want + "\n", root)

    def test_a_stale_or_malformed_install_record_warns_with_its_cause(self):
        self.manifest("    install: plugin\n    config:\n      profile: full\n")
        self.installed["meta-alpha@market"] = [{"scope": "user", "installPath": str(self.tmp / "gone" / "1.0.0")}]
        self.write_installed()
        r = self.packs("config", "alpha")
        self.assertEqual((r.returncode, r.stdout), (0, "profile=full\n"))
        self.assertIn(f"not found at its recorded installPath {self.tmp / 'gone' / '1.0.0'}", r.stderr)
        for record, cause in (({"version": 2, "plugins": {"meta-alpha@market": [{"installPath": 5}]}},
                               "malformed entry for it in installed_plugins.json"),
                              ({"version": 2, "plugins": {"meta-alpha@market": [{"installPath": "/x", "projectPath": ""}]}},
                               "malformed entry for it in installed_plugins.json"),
                              ("not json", "unreadable installed_plugins.json (JSONDecodeError)"),
                              ([1, 2], "unreadable installed_plugins.json (TypeError)")):
            (self.config_dir / "plugins" / "installed_plugins.json").write_text(
                record if isinstance(record, str) else json.dumps(record))
            r = self.packs("config", "alpha")
            self.assertEqual((r.returncode, r.stdout), (0, "profile=full\n"), r.stderr)
            self.assertIn(cause, r.stderr)
            self.assertEqual(len(r.stderr.splitlines()), 1, r.stderr)

    def test_an_unknown_install_mode_is_refused_and_a_single_quoted_one_is_read(self):
        self.manifest("    install: Plugin\n    config:\n      profile: full\n")
        for cmd in ("check", "apply", "config"):
            r = self.packs(cmd, *(["alpha"] if cmd == "config" else []))
            self.assertNotEqual(r.returncode, 0, cmd)
            self.assertIn("unknown install mode for alpha: 'Plugin'", r.stderr, cmd)
        self.assertFalse((self.inst / ".packs").exists())
        self.install()
        self.manifest("    install: 'plugin'\n    config:\n      profile: full\n")
        self.assertEqual(self.packs("config", "alpha").stdout, "profile=full\nengine=claude\n")

    def test_install_without_a_space_is_read_and_an_empty_install_is_refused(self):
        self.install()
        self.manifest("    install:plugin\n    config:\n      profile: full\n")
        self.assertEqual(self.packs("config", "alpha").stdout, "profile=full\nengine=claude\n")
        self.manifest("    install:\n    config:\n      profile: full\n")
        for cmd in ("check", "apply", "config"):
            r = self.packs(cmd, *(["alpha"] if cmd == "config" else []))
            self.assertNotEqual(r.returncode, 0, cmd)
            self.assertIn("unknown install mode for alpha: ''", r.stderr, cmd)

    def test_the_plugin_root_is_read_from_stdout_and_a_helper_failure_is_named(self):
        self.install()
        self.manifest("    install: plugin\n    config:\n      profile: full\n")
        noise = self.tmp / "noise"
        noise.mkdir()
        (noise / "sitecustomize.py").write_text("import sys\nprint('interpreter noise', file=sys.stderr)\n")
        r = self.packs("config", "alpha", env={"PYTHONPATH": str(noise)})
        self.assertEqual((r.returncode, r.stdout), (0, "profile=full\nengine=claude\n"), r.stderr)
        (self.inst / "scripts" / "plugin_root.py").write_text("raise RuntimeError('boom')\n")
        r = self.packs("config", "alpha")
        self.assertEqual((r.returncode, r.stdout), (0, "profile=full\n"))
        self.assertIn("scripts/plugin_root.py failed (exit 1): RuntimeError: boom", r.stderr)

    def test_a_malformed_install_record_does_not_void_a_valid_one(self):
        root = self.install(engine="valid")
        self.installed["meta-alpha@market"] = [{"installPath": 5}, {"installPath": "/x", "projectPath": "a\u0000b"},
                                               {"scope": "user", "installPath": str(root)}]
        self.write_installed()
        self.manifest("    install: plugin\n")
        r = self.packs("config", "alpha", "engine")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "valid\n", ""))

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

    def mounted_then_flipped(self) -> Path:
        """A pack mounted as a submodule and committed, then declared `install: plugin`."""
        src = self.tmp / "src" / "alpha"
        (src / "skills" / "alpha-one").mkdir(parents=True)
        (src / "skills" / "alpha-one" / "SKILL.md").write_text("---\nname: alpha-one\n---\n")
        (src / "pack.yaml").write_text(PACK_YAML.format(v="0.1.0", engine="mounted"))
        (src / "agents").mkdir()
        (src / "agents" / "alpha-agent.md").write_text("# agent\n")
        for args in (["init", "-q", "-b", "main"], ["add", "."], ["commit", "-q", "-m", "init"]):
            subprocess.run(["git", *args], cwd=src, check=True, env={**os.environ, **GIT_ENV})
        r = self.packs("add", "alpha", str(src))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("alpha-one", self.links())
        subprocess.run(["git", "commit", "-q", "-am", "mount"], cwd=self.inst, check=True,
                       env={**os.environ, **GIT_ENV})
        self.manifest("    install: plugin\n    config:\n      profile: full\n")
        return self.inst / ".packs" / "alpha"

    def test_apply_never_mounts_a_plugin_pack_back_from_a_recorded_gitlink(self):
        mount = self.mounted_then_flipped()
        subprocess.run(["git", "submodule", "deinit", "-q", "-f", ".packs/alpha"], cwd=self.inst, check=True,
                       env={**os.environ, **GIT_ENV})       # a fresh clone of this state: empty dir, gitlink kept
        self.assertEqual(list(mount.iterdir()), [])
        for cmd in ("apply", "check"):
            r = self.packs(cmd)
            self.assertNotEqual(r.returncode, 0, cmd)
            self.assertIn("installed as a plugin and also mounted: alpha", r.stderr, cmd)
            self.assertNotIn("state matches", r.stdout)
        self.assertEqual(list(mount.iterdir()), [], "apply checked the plugin pack's mount out again")
        shutil.rmtree(mount)                                 # the gitlink alone still counts
        self.assertIn("also mounted: alpha", self.packs("check").stderr)

    def test_sync_links_nothing_from_a_leftover_mount_of_a_plugin_pack(self):
        self.mounted_then_flipped()
        self.assertIn("0 pack links", self.packs("sync").stdout)
        self.assertEqual(self.links(), [])
        self.assertEqual(list((self.inst / ".claude" / "agents").iterdir()), [])
        self.assertIn("also mounted: alpha", self.packs("check").stderr)

    def test_a_leftover_mount_after_a_pull_is_cleaned_by_apply_not_refused(self):
        """Origin removes the submodule; a clone that pulls keeps the populated dir, untracked."""
        def g(cwd, *args) -> str:
            return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                                  env={**os.environ, **GIT_ENV}).stdout
        g(self.inst, "add", "CLAUDE.md", "scripts", "systems", "skills/skill-builder")
        g(self.inst, "commit", "-q", "-m", "framework")
        self.mounted_then_flipped()
        self.manifest("    repo: x\n")                    # back to the mount for the first commit
        g(self.inst, "add", ".packs.yaml"); g(self.inst, "commit", "-q", "-m", "mount")
        clone = self.tmp / "clone"
        g(self.tmp, "clone", "-q", "--recurse-submodules", str(self.inst), str(clone))
        self.assertEqual(self.packs("sync", cwd=clone).returncode, 0)
        self.assertTrue((clone / "skills" / "alpha-one").is_symlink())
        # origin: drop the submodule, declare the plugin
        g(self.inst, "rm", "-q", "-f", ".packs/alpha")
        shutil.rmtree(self.inst / g(self.inst, "rev-parse", "--git-path", "modules/.packs/alpha").strip(),
                      ignore_errors=True)                  # an absolute path wins the join
        self.manifest("    install: plugin\n    config:\n      profile: full\n")
        g(self.inst, "add", ".packs.yaml"); g(self.inst, "commit", "-q", "-m", "plugin")
        self.assertEqual(self.packs("apply").returncode, 0)  # origin drops its own stale links
        self.assertEqual(self.packs("check").returncode, 0, self.packs("check").stderr)
        # the clone pulls: git cannot rmdir the populated mount and leaves it untracked
        g(clone, "pull", "-q", "--no-rebase")
        self.assertTrue((clone / ".packs" / "alpha" / "skills" / "alpha-one" / "SKILL.md").is_file())
        self.assertEqual(g(clone, "ls-files", "-s", "--", ".packs/alpha"), "")
        r = self.packs("apply", cwd=clone)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("state matches", r.stdout)
        self.assertFalse((clone / "skills" / "alpha-one").is_symlink(), "the stale pack link survived apply")
        r = self.packs("check", cwd=clone)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("warn: .packs/alpha is a leftover of plugin pack alpha", r.stderr)
        self.assertIn("rm -rf .packs/alpha", r.stderr)
        shutil.rmtree(clone / ".packs" / "alpha")
        r = self.packs("check", cwd=clone)
        self.assertEqual((r.returncode, "leftover" in r.stderr), (0, False), r.stderr)

    def test_list_shows_a_plugin_pack_and_remove_refuses_it(self):
        self.manifest("    install: plugin\n    config:\n      profile: full\n")
        self.assertEqual(self.packs("list").stdout,
                         "alpha  plugin meta-alpha@market  (installed by Claude Code, not mounted)\n"
                         "no packs mounted as submodules\n")
        r = self.packs("remove", "alpha")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("installed as a plugin: uninstall it with /plugin uninstall meta-alpha@market", r.stderr)
        self.assertIn("profile: full", (self.inst / ".packs.yaml").read_text())

    def test_check_warns_of_an_untracked_leftover_and_reports_a_plugin_pack_naming_none(self):
        (self.inst / ".packs" / "alpha").mkdir(parents=True)
        (self.inst / ".packs" / "alpha" / "pack.yaml").write_text(PACK_YAML.format(v="0", engine="x"))
        self.manifest("    install: plugin\n")
        r = self.packs("check")                             # no gitlink: a leftover, not a mount
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("warn: .packs/alpha is a leftover of plugin pack alpha", r.stderr)
        self.assertNotIn("also mounted", r.stderr)
        (self.inst / "systems" / "packs.yaml").write_text("packs:\n")
        shutil.rmtree(self.inst / ".packs")
        r = self.packs("check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("installed as a plugin but names none: alpha", r.stderr)


if __name__ == "__main__":
    unittest.main()
