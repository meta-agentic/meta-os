#!/usr/bin/env python3
"""`scripts/packs.sh config` against the manifest shapes an instance actually writes.

    python3 -m unittest tests.test_packs_sh_config

Same throwaway instance as `test_packs_sh.py`, with two packs: `alpha`, whose pack.yaml
declares its keys in both shapes the parser accepts (block and inline map), and `bare`,
which ships no pack.yaml and is declared BEFORE alpha in the manifest. What is pinned
here is that a value is read as YAML reads it — a quoted `#` kept, a trailing comment
dropped, a block sequence or map returned whole rather than as empty — and that a key
the pack does not declare is refused or warned about instead of silently falling back
to the default.
"""
from __future__ import annotations

import unittest

from test_packs_sh import PacksShFixture

ALPHA_YAML = """name: alpha
version: 0.1.0
description: fixture
config:
  profile:
    default: light
    one_of: light | full
    doc: "the profile"
  scale: { default: fibonacci, one_of: fibonacci | linear }
  label:
    doc: "free text, no default"
  spaces:
    doc: "a list of spaces"
  space:
    doc: "one space; unset means every space"
  workers:
    doc: "a map of workers"
"""


class PacksShConfigTest(PacksShFixture):

    PACKS = {"bare": ["bare-one"], "alpha": ["alpha-one"]}

    def pack_yaml(self, name: str) -> str | None:
        return ALPHA_YAML if name == "alpha" else None

    def configure(self, *lines: str):
        """Declare bare, then alpha with `lines` under its config:, and mount both."""
        text = (f"packs:\n  bare:\n    repo: {self.urls['bare']}\n"
                f"  alpha:\n    repo: {self.urls['alpha']}\n")
        if lines:
            text += "    config:\n" + "".join(f"      {line}\n" for line in lines)
        (self.inst / ".packs.yaml").write_text(text)
        self.packs("apply")

    def resolved(self, pack: str = "alpha") -> dict[str, str]:
        r = self.packs("config", pack)
        self.assertNotIn("warn:", r.stderr)
        return dict(line.split("=", 1) for line in r.stdout.splitlines())

    def test_resolves_the_instance_over_block_and_inline_defaults_and_a_block_map(self):
        self.configure("profile: full",
                       "workers:",
                       "  codex: { enabled: true }   # the default engine",
                       "  gemini: { roles: [review, research] }")
        got = self.resolved()
        self.assertEqual(got["profile"], "full")          # instance over a block-form default
        self.assertEqual(got["scale"], "fibonacci")       # inline-map default
        self.assertEqual(got["label"], "")                # unset, no default
        workers = got["workers"]                          # a block map, not silently empty
        self.assertTrue(workers.startswith("{codex: {") and workers.endswith("}"), workers)
        self.assertIn("gemini: { roles: [review, research] }", workers)
        self.assertNotIn("#", workers)

    def test_keeps_a_hash_inside_quotes_and_drops_a_trailing_comment(self):
        self.configure('label: "a #b"   # comment')
        self.assertEqual(self.packs("config", "alpha", "label").stdout.strip(), "a #b")

    def test_reads_a_block_sequence_and_a_bare_key(self):
        self.configure("spaces:", "  - one", "  - two  # c", "space:")
        self.assertEqual(self.packs("config", "alpha", "spaces").stdout.strip(), "[one, two]")
        got = self.resolved()
        self.assertEqual(got["space"], "")
        self.assertEqual(got["spaces"], "[one, two]")

    def test_rejects_an_unknown_key_and_warns_on_a_misspelled_one(self):
        self.configure()
        r = self.packs("config", "alpha", "profil", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown config key 'alpha.profil'", r.stderr)
        self.configure("profil: full")
        r = self.packs("config", "alpha", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("alpha.profil", r.stderr)
        self.assertIn("profile=light", r.stdout)            # the default it fell back to, flagged

    def test_validates_an_enum_literally_and_after_dropping_the_comment(self):
        for value, shown in (("l.ght", "l.ght"), ("wrong # nope", "wrong")):
            with self.subTest(value=value):
                self.configure(f"profile: {value}")
                r = self.packs("config", "alpha", check=False)
                self.assertEqual(r.returncode, 1)
                self.assertIn(f"alpha.profile='{shown}' not in {{light|full}}", r.stderr)

    def test_a_pack_without_pack_yaml_stays_in_its_own_pack(self):
        # bare has no pack.yaml and no config; the pack after it has both
        self.configure("profile: full")
        r = self.packs("config", "bare")
        self.assertEqual(r.stdout, "")
        self.assertEqual(r.stderr, "")
        self.assertEqual(self.resolved()["profile"], "full")


if __name__ == "__main__":
    unittest.main()
