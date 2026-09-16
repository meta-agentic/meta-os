#!/usr/bin/env python3
"""Tests for the pack conformance gate — `scripts/validate_pack.py`.

The gate's whole value is that a pack's acceptance criteria are checked by a
program on every pull request instead of by a reviewer once. That only holds if
the gate itself is exercised, so this module drives the real command line —
`python3 scripts/validate_pack.py <pack>` — and asserts on its exit code and
output, not on internals. Two committed fixtures are the controls:

    tests/fixtures/conforming-pack   — must PASS, always
    tests/fixtures/violating-pack    — must FAIL, with a known set of findings

Everything that would be unsafe to commit to a public repository (a tracker-key
lookalike, an absolute home path) is assembled from fragments and written into a
temporary copy of a fixture at run time, never stored in the tree.

Run it:

    python3 -m unittest discover -s tests
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "validate_pack.py"
FIXTURES = ROOT / "tests" / "fixtures"
CONFORMING = FIXTURES / "conforming-pack"
VIOLATING = FIXTURES / "violating-pack"

sys.path.insert(0, str(ROOT / "scripts"))
import validate_pack  # noqa: E402  (path set up immediately above)

# Assembled, never written as a literal: this repository is public, and
# `validate_framework.py`'s own public-safety scan reads every tracked file — a
# committed tracker-key lookalike would (correctly) fail that gate.
TRACKER_KEY = "ACME" + "-" + "4172"
HOME_PATH = "/" + "Users" + "/example-operator/work/pack"
HOLDER = "Example Holder"          # the conforming fixture's LICENSE holder


def run_checker(*args: str) -> subprocess.CompletedProcess:
    """The gate, exactly as CI invokes it."""
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        capture_output=True, text=True, cwd=str(ROOT))


class PackGateTestCase(unittest.TestCase):
    """Shared staging: a writable copy of a fixture, torn down after the test."""

    def stage(self, fixture: Path = CONFORMING) -> Path:
        tmp = tempfile.mkdtemp(prefix="pack-gate-")
        self.addCleanup(shutil.rmtree, tmp, True)
        target = Path(tmp) / fixture.name
        shutil.copytree(fixture, target)
        return target

    def assertPasses(self, pack: Path, why: str = ""):
        r = run_checker(str(pack))
        self.assertEqual(r.returncode, 0,
                         f"{why}\nexpected the gate to pass\n{r.stdout}{r.stderr}")
        return r

    def assertFails(self, pack: Path, check: str, why: str = ""):
        r = run_checker(str(pack))
        self.assertNotEqual(r.returncode, 0,
                            f"{why}\nexpected the gate to fail\n{r.stdout}{r.stderr}")
        self.assertIn(f"[{check}]", r.stdout,
                      f"{why}\nexpected a {check!r} finding\n{r.stdout}{r.stderr}")
        return r


class ConformingPack(PackGateTestCase):
    """Acceptance criterion 3 — running the checker against a conforming pack passes."""

    def test_conforming_fixture_passes(self):
        r = self.assertPasses(CONFORMING)
        self.assertIn("packs conformant", r.stdout)

    def test_conforming_fixture_passes_under_strict(self):
        """No accepted debt to hide behind: the positive control is clean outright."""
        r = run_checker("--strict", str(CONFORMING))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_passes_when_checked_from_outside_the_repository(self):
        """The reusable workflow checks out the pack somewhere else entirely."""
        self.assertPasses(self.stage())

    def test_findings_never_carry_an_absolute_path(self):
        """A gate whose own output leaks the runner's paths is not estate-neutral."""
        pack = self.stage()
        (pack / "skills" / "example-method" / "SKILL.md").write_text(
            "---\nname: example-method\n---\n# Broken\n", encoding="utf-8")
        r = run_checker(str(pack))
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertNotIn(str(pack.parent), r.stdout)
        self.assertIn("example-method/SKILL.md", r.stdout.replace("\\", "/"))


class ViolatingPack(PackGateTestCase):
    """Acceptance criterion 1 — a pack with a violation fails the check."""

    def test_violating_fixture_fails(self):
        r = run_checker(str(VIOLATING))
        self.assertNotEqual(r.returncode, 0, r.stdout)
        # The verdict rides sys.exit(), i.e. stderr; the findings are on stdout.
        self.assertIn("pack gate FAILED", r.stderr)

    def test_violating_fixture_raises_every_expected_class(self):
        """The negative control is specific: silent drift in what it catches is drift."""
        r = run_checker(str(VIOLATING))
        for check in ("pack-schema", "pack-required-file",
                      "pack-skill-shape", "estate-neutral"):
            with self.subTest(check=check):
                self.assertIn(f"[{check}]", r.stdout, r.stdout)

    def test_violating_fixture_names_the_leaking_file(self):
        r = run_checker(str(VIOLATING))
        self.assertRegex(r.stdout.replace("\\", "/"),
                         r"skills/example-method/SKILL\.md:\d+: names the pack's LICENSE")

    def test_meta_os_own_sweep_stays_green(self):
        """The fixtures are inputs to this gate, so the in-repo sweep must skip them."""
        r = run_checker()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("fixtures", r.stdout)

    def test_discovery_excludes_the_fixture_tree(self):
        discovered = {p.resolve() for p in validate_pack.discover_packs()}
        self.assertNotIn(CONFORMING.resolve(), discovered)
        self.assertNotIn(VIOLATING.resolve(), discovered)


class LicenceExemption(PackGateTestCase):
    """Acceptance criterion 2 — the ratified LICENSE exemption, and its adversarial probes.

    Ratified 2026-09-14: *a copyright holder's name in LICENSE is not an instance
    identifier*. Encoded in the checker (`HOLDER_EXEMPT_FILES`), not in a review
    comment — these are the probes that hold it to exactly that scope.
    """

    def test_holder_name_in_license_passes(self):
        """The probe the exemption exists for."""
        pack = self.stage()
        self.assertIn(HOLDER, (pack / "LICENSE").read_text(encoding="utf-8"))
        self.assertPasses(pack, "a holder name in LICENSE is not an instance identifier")

    def test_same_holder_name_in_a_skill_file_fails(self):
        """The adversarial twin: same string, a file the exemption does not cover."""
        pack = self.stage()
        skill = pack / "skills" / "example-method" / "SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8")
            + f"\nReviewed by {HOLDER} before every release.\n", encoding="utf-8")
        r = self.assertFails(pack, "estate-neutral",
                             "the holder name outside LICENSE is an instance identifier")
        self.assertIn("SKILL.md", r.stdout)

    def test_same_holder_name_in_provenance_fails(self):
        """The exemption names LICENSE, not 'the pack's metadata files'."""
        pack = self.stage()
        prov = pack / "PROVENANCE.md"
        prov.write_text(prov.read_text(encoding="utf-8")
                        + f"\nMaintained by {HOLDER}.\n", encoding="utf-8")
        self.assertFails(pack, "estate-neutral")

    def test_holder_match_is_case_insensitive(self):
        pack = self.stage()
        readme = pack / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8")
                          + f"\nA note from {HOLDER.lower()}.\n", encoding="utf-8")
        self.assertFails(pack, "estate-neutral")

    def test_holder_match_respects_token_boundaries(self):
        """`Example Holder` must not fire on `Example Holdership`."""
        pack = self.stage()
        readme = pack / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8")
                          + f"\nOn {HOLDER}ships in general.\n", encoding="utf-8")
        self.assertPasses(pack)

    def test_license_is_not_exempt_from_the_tracker_key_class(self):
        """The exemption covers ONE class in that file, not the file."""
        pack = self.stage()
        lic = pack / "LICENSE"
        lic.write_text(lic.read_text(encoding="utf-8")
                       + f"\nInternal reference: {TRACKER_KEY}\n", encoding="utf-8")
        r = self.assertFails(pack, "estate-neutral")
        self.assertIn("LICENSE", r.stdout)

    def test_license_is_not_exempt_from_the_home_path_class(self):
        pack = self.stage()
        lic = pack / "LICENSE"
        lic.write_text(lic.read_text(encoding="utf-8")
                       + f"\nAuthored at {HOME_PATH}\n", encoding="utf-8")
        self.assertFails(pack, "estate-neutral")

    def test_unfilled_licence_template_names_nobody(self):
        """`<name of copyright owner>` must never become the string the gate hunts."""
        pack = self.stage()
        (pack / "LICENSE").write_text(
            "MIT License\n\nCopyright (c) <year> <name of copyright owner>\n",
            encoding="utf-8")
        self.assertPasses(pack, "a placeholder holder would match half the tree")

    def test_licence_body_prose_is_not_read_as_an_attribution(self):
        """MIT's 'The above copyright notice…' line must not be mistaken for the holder."""
        self.assertEqual(validate_pack.license_holder(CONFORMING), HOLDER)

    def test_pack_without_a_license_has_no_holder_to_hunt(self):
        pack = self.stage()
        (pack / "LICENSE").unlink()
        r = run_checker(str(pack))
        self.assertIn("[pack-required-file]", r.stdout)
        self.assertNotIn("[estate-neutral]", r.stdout)


class EstateNeutralClasses(PackGateTestCase):
    """The rest of the estate-neutral scan — the checks that used to live in a scratch script."""

    def test_tracker_key_in_a_skill_fails(self):
        pack = self.stage()
        skill = pack / "skills" / "example-method" / "SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8")
                         + f"\nSee {TRACKER_KEY} for the original decision.\n",
                         encoding="utf-8")
        self.assertFails(pack, "estate-neutral")

    def test_absolute_home_path_fails(self):
        pack = self.stage()
        readme = pack / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8")
                          + f"\nBuilt from {HOME_PATH}\n", encoding="utf-8")
        self.assertFails(pack, "estate-neutral")

    def test_standards_identifier_is_allowed(self):
        """`UTF-8` is tracker-key-shaped and is not one — the allow-list carries it."""
        pack = self.stage()
        skill = pack / "skills" / "example-method" / "SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8")
                         + "\nLedgers are written UTF-8, timestamps ISO-8601.\n",
                         encoding="utf-8")
        self.assertPasses(pack)

    def test_estate_neutral_findings_are_never_baselineable(self):
        """A leak has no undo, so it must fail on sight rather than become accepted debt."""
        self.assertFalse(validate_pack.BASELINEABLE["estate-neutral"])

    def test_estate_neutral_survives_strict_and_baseline_modes(self):
        """`--strict` may only ever add errors, never drop the unbaselineable class."""
        pack = self.stage()
        readme = pack / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8")
                          + f"\nTracked as {TRACKER_KEY}.\n", encoding="utf-8")
        r = run_checker("--strict", str(pack))
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("[estate-neutral]", r.stdout)


class ReusableWorkflow(unittest.TestCase):
    """Acceptance criterion 1/4 — the gate a pack repository adopts actually exists here."""

    WORKFLOW = ROOT / ".github" / "workflows" / "pack-conformance.yml"

    def load(self) -> dict:
        import yaml
        return yaml.safe_load(self.WORKFLOW.read_text(encoding="utf-8"))

    def test_reusable_workflow_exists(self):
        self.assertTrue(self.WORKFLOW.is_file(),
                        "a pack repo adopts the gate by calling this workflow")

    def test_reusable_workflow_is_callable(self):
        # `on` is a YAML 1.1 boolean; the file quotes the key, so read both spellings.
        data = self.load()
        triggers = data.get("on", data.get(True)) or {}
        self.assertIn("workflow_call", triggers,
                      "without workflow_call a pack repo cannot adopt this gate")

    def test_reusable_workflow_runs_the_one_checker(self):
        body = self.WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("scripts/validate_pack.py", body,
                      "the reusable workflow must run the checker in this repo")

    def test_reusable_workflow_is_read_only(self):
        self.assertEqual(self.load().get("permissions"), {"contents": "read"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
