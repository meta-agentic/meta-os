#!/usr/bin/env python3
"""Tests for the catalog check of the framework gate — `check_index_resolves` in
`scripts/validate_framework.py`, with the registry read in `scripts/pack_registry.py`.

A catalogued skill resolves in one of three ways: a real `skills/<name>/SKILL.md`, the link a
mounted pack places in `skills/`, or — only while its pack is not mounted — an installable pack
in `systems/packs.yaml` that lists it in `provides:`, the one way that also holds for a pack
installed as a plugin, which leaves nothing on disk. Anything else is `index-phantom`, and a
registry or pack-provided row the gate cannot read is a finding of its own. Each case builds a
small throwaway tree and points the gate at it; one case reads the real catalog and registry.

    python3 -m unittest discover -s tests
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_framework as vf  # noqa: E402  (path set up immediately above)

REGISTRY = """version: 1
packs:
  agile:
    repo: https://example.invalid/agile
    provides: [alpha, beta]
    status: available
  later:
    repo: https://example.invalid/later
    provides: [gamma]
    status: planned
"""


class IndexResolvesTest(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="metaos-index-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.skills = self.tmp / "skills"
        self.skills.mkdir()
        self.registry = self.tmp / "packs.yaml"
        self.registry.write_text(REGISTRY)
        self.own("core-skill")
        for name, value in (("SKILLS_DIR", self.skills),
                            ("SKILLS_INDEX", self.skills / "_index.md"),
                            ("PACKS_REGISTRY", self.registry),
                            ("PACKS_DIR", self.tmp / ".packs")):
            patcher = mock.patch.object(vf, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def own(self, name: str) -> None:
        (self.skills / name).mkdir()
        (self.skills / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n")

    def catalog(self, *names: str) -> None:
        rows = "".join(f"| [[skills/{n}/SKILL\\|{n}]] | x |\n" for n in names)
        (self.skills / "_index.md").write_text(f"## Core\n\n| Skill | Use |\n|---|---|\n{rows}")

    def phantoms(self, others: tuple[str, ...] = ()) -> tuple[set[str], object]:
        findings: list = []
        provided = vf.check_index_resolves(findings)
        self.assertEqual([f.detail for f in findings if f.check != "index-phantom"], list(others))
        return {f.detail.split("'")[1] for f in findings if f.check == "index-phantom"}, provided

    def test_a_registry_provided_entry_resolves_with_no_mount(self):
        self.catalog("core-skill", "alpha", "beta")
        phantoms, provided = self.phantoms()
        self.assertEqual(phantoms, set())
        self.assertEqual(provided, {"alpha": "agile", "beta": "agile"})

    def test_an_entry_no_installable_pack_provides_stays_phantom(self):
        # `gamma` is provided only by a planned pack, which cannot be installed yet
        self.catalog("core-skill", "alpha", "ghost", "gamma")
        phantoms, provided = self.phantoms()
        self.assertEqual(phantoms, {"ghost", "gamma"})
        self.assertEqual(provided, {"alpha": "agile"})

    def test_a_missing_registry_provides_nothing_and_is_reported(self):
        self.registry.unlink()
        self.catalog("core-skill", "alpha")
        findings: list = []
        self.assertEqual(vf.check_index_resolves(findings), {})
        self.assertEqual({(f.check, f.path) for f in findings},
                         {("index-phantom", "skills/_index.md"), ("pack-registry", "systems/packs.yaml")})
        detail = [f.detail for f in findings][0]
        self.assertEqual(detail, "registry unreadable — No such file or directory")
        self.assertFalse(vf.BASELINEABLE["pack-registry"], "an unreadable registry is never accepted debt")

    def test_an_unparseable_registry_is_reported_besides_the_phantoms(self):
        self.registry.write_text("packs:\n  agile: [unclosed\n")
        self.catalog("core-skill", "alpha")
        findings: list = []
        vf.check_index_resolves(findings)
        self.assertEqual(sorted(f.check for f in findings), ["index-phantom", "pack-registry"])
        detail = next(f.detail for f in findings if f.check == "pack-registry")
        self.assertTrue(detail.startswith("registry unparseable — ") and detail.endswith(" at line 3"), detail)
        self.assertNotIn(str(self.tmp), detail, "a finding may reach a tracked file: no local path")

    def test_provides_as_a_string_is_an_error_and_provides_nothing(self):
        self.registry.write_text(REGISTRY + "  solo:\n    provides: delta\n    status: available\n")
        self.catalog("core-skill", "alpha", "delta")
        phantoms, provided = self.phantoms(("pack 'solo': `provides:` must be a list, not str",))
        self.assertEqual(phantoms, {"delta"})
        self.assertEqual(provided, {"alpha": "agile"})

    def test_a_mounted_pack_still_resolves_through_its_link(self):
        # a mounted pack: its skill folder linked into skills/, as `packs.sh sync` does;
        # `alpha` is registry-provided too, `delta` is not (an unregistered custom pack)
        mount = self.tmp / ".packs" / "custom" / "skills"
        for name in ("alpha", "delta"):
            (mount / name).mkdir(parents=True)
            (mount / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
            (self.skills / name).symlink_to(mount / name)
        self.catalog("core-skill", "alpha", "delta")
        phantoms, provided = self.phantoms()
        self.assertEqual(phantoms, set())
        self.assertEqual(provided, {}, "a linked skill resolves on disk, not from the registry")

    def test_an_uninitialised_submodule_is_not_a_mount(self):
        # what a CI checkout without `submodules:` holds: an empty .packs/<pack>/, no links
        (self.tmp / ".packs" / "agile").mkdir(parents=True)
        self.catalog("core-skill", "alpha", "beta")
        phantoms, provided = self.phantoms()
        self.assertEqual((phantoms, provided), (set(), {"alpha": "agile", "beta": "agile"}))

    def test_a_mounted_pack_resolves_from_its_own_tree_before_sync(self):
        # initialised but `packs.sh sync` never ran: no links in skills/
        pack = self.tmp / ".packs" / "agile"
        for rel in ("skills/alpha", "skills/nested/beta", "skills/gamma"):
            (pack / rel).mkdir(parents=True)
            (pack / rel / "SKILL.md").write_text("---\nname: x\n---\n")
        (pack / ".git").write_text("gitdir: elsewhere\n")
        self.catalog("core-skill", "alpha", "beta")
        phantoms, provided = self.phantoms()
        self.assertEqual((phantoms, provided), (set(), {}))
        # a plugin.json with skill paths is authoritative, as for packs.sh: beta is not listed
        (pack / ".claude-plugin").mkdir()
        (pack / ".claude-plugin" / "plugin.json").write_text('{"name": "agile", "skills": ["./skills/alpha"]}')
        phantoms, provided = self.phantoms()
        self.assertEqual((phantoms, provided), ({"beta"}, {}))

    def test_a_mounted_pack_that_no_longer_ships_an_entry_is_phantom(self):
        # `agile` is mounted and links alpha only; the registry still says it provides beta
        mount = self.tmp / ".packs" / "agile" / "skills" / "alpha"
        mount.mkdir(parents=True)
        (mount / "SKILL.md").write_text("---\nname: alpha\n---\n")
        (self.skills / "alpha").symlink_to(mount)
        self.catalog("core-skill", "alpha", "beta")
        findings: list = []
        self.assertEqual(vf.check_index_resolves(findings), {})
        self.assertEqual([f.detail for f in findings],
                         ["entry 'beta' does not resolve — no skills/beta/SKILL.md "
                          "(pack 'agile' is mounted and does not ship it)"])

    def test_the_pack_provided_table_is_catalogued(self):
        (self.skills / "_index.md").write_text(
            "## Core\n\n| Skill | Use |\n|---|---|\n"
            "| [[skills/core-skill/SKILL\\|core-skill]] | x |\n"
            "| `removed-skill` | removed, third-party |\n\n"
            "## Pack-provided skills\n\n| Skill | Pack | Plugin | Use for |\n|---|---|---|---|\n"
            "| `alpha` | [agile](https://example.invalid/agile) | `p@m` | x |\n"
            "| `ghost` | [none](https://example.invalid/none) | `p@m` | x |\n\n"
            "## After\n\n| `not-an-entry` | x |\n")
        self.assertEqual(vf.index_entries(), {"core-skill", "alpha", "ghost"})
        phantoms, provided = self.phantoms()
        self.assertEqual(phantoms, {"ghost"})
        self.assertEqual(provided, {"alpha": "agile"})

    def test_rows_the_pack_table_would_skip_are_findings(self):
        (self.skills / "_index.md").write_text(
            "## Pack-provided skills\n\nSee [[systems/packs.yaml|the registry]] and [[systems/packs]].\n\n"
            "| Skill | Pack | Plugin | Use for |\n|---|---|---|---|\n"
            "| `alpha` | [agile](https://example.invalid/agile) | `p@m` | x |\n"
            "| | [agile](https://example.invalid/agile) | `p@m` | x |\n"
            "  | `beta` | [agile](https://example.invalid/agile) | `p@m` | x |\n"
            "`gamma` | agile | `p@m` | x\n")
        phantoms, provided = self.phantoms((
            "pack-provided row '' does not start with one backticked skill name",
            "pack-provided row '| `beta` | [agile](https://example.invalid/agile) | `p@m` | x |' "
            "is not a table row (indented, or no leading pipe)",
            "pack-provided row '`gamma` | agile | `p@m` | x' is not a table row (indented, or no leading pipe)"))
        self.assertEqual((phantoms, provided), (set(), {"alpha": "agile"}))

    def test_an_at_sign_outside_a_plugin_column_is_not_a_pack_row(self):
        (self.skills / "_index.md").write_text(
            "## Core\n\n| Skill | Use |\n|---|---|\n"
            "| [[skills/core-skill/SKILL\\|core-skill]] | pinned at `pkg@1.2.3` |\n"
            "| `a@b` | an address |\n\n"
            "## Library\n\n| Family | Members | Plugin |\n|---|---|---|\n"
            "| **misc** | core-skill | `p@m` |\n")
        phantoms, provided = self.phantoms(("pack row '**misc**' sits outside a `## Pack-provided` table",))
        self.assertEqual((phantoms, provided), (set(), {}))

    def test_a_pack_table_the_gate_cannot_read_fails_closed(self):
        (self.skills / "_index.md").write_text(
            "## Core\n\n| Skill | Use |\n|---|---|\n"
            "| [[skills/core-skill/SKILL\\|core-skill]] | x |\n\n"
            "## Pack-provided skills\n\n| Skill | Pack | Plugin | Use for |\n|---|---|---|---|\n"
            "| `alpha` | [agile](https://example.invalid/agile) | `p@m` | x |\n"
            "| beta | [agile](https://example.invalid/agile) | `p@m` | x |\n"
            "| `beta` `gamma` | [agile](https://example.invalid/agile) | `p@m` | x |\n\n"
            "## Moved skills\n\n| Skill | Plugin |\n|---|---|\n"
            "| `beta` | `p@m` |\n")
        phantoms, provided = self.phantoms((
            "pack-provided row 'beta' does not start with one backticked skill name",
            "pack-provided row '`beta` `gamma`' does not start with one backticked skill name",
            "pack row '`beta`' sits outside a `## Pack-provided` table"))
        self.assertEqual((phantoms, provided), (set(), {"alpha": "agile"}))
        self.assertEqual(vf.index_entries(), {"core-skill", "alpha"})


class RealCatalogTest(unittest.TestCase):

    def test_the_framework_catalog_has_no_phantom_without_mounts(self):
        """The framework repository mounts no pack: its pack rows resolve from the registry."""
        findings: list = []
        vf.check_index_resolves(findings)
        self.assertEqual([str(f) for f in findings], [])
        self.assertLessEqual({"agile-process", "agile-swarm"}, vf.index_entries())


if __name__ == "__main__":
    unittest.main()
