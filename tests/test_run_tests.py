#!/usr/bin/env python3
"""scripts/run_tests.py: every test suite in the repository runs in CI, found rather than listed.

    python3 -m unittest tests.test_run_tests

What is pinned here: the runner finds this repository's suites (the gates' own and the
pipeline's), ignores fixture data, fails on a failing suite and on finding nothing, and
the blocking CI job is the one that calls it. The behavioural cases copy the real script
into a throwaway git repository with synthetic suites, so they never recurse into this one.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_tests.py"
WORKFLOW = ROOT / ".github" / "workflows" / "check.yml"

PASSING = "import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n"
FAILING = "import unittest\n\nclass T(unittest.TestCase):\n    def test_bad(self):\n        self.fail('x')\n"


class ThisRepository(unittest.TestCase):

    def test_finds_the_gate_and_pipeline_suites(self):
        out = subprocess.run([sys.executable, str(RUNNER), "--list"], cwd=ROOT,
                             check=True, capture_output=True, text=True).stdout.split()
        self.assertIn("tests", out)
        self.assertIn("pipeline/tests", out)

    def test_the_blocking_job_runs_every_suite(self):
        jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
        gates = jobs["gates"]
        self.assertFalse(gates.get("continue-on-error", False), "the gates job must block")
        runs = [s.get("run", "") for s in gates["steps"]]
        self.assertTrue(any("scripts/run_tests.py" in r for r in runs),
                        "the blocking job must call scripts/run_tests.py")
        for r in runs:
            self.assertNotIn("unittest discover", r,
                             "a hand-picked suite in CI bypasses discovery; call the runner")


class Runner(unittest.TestCase):

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="run-tests-"))
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "scripts").mkdir()
        shutil.copy2(RUNNER, self.repo / "scripts" / "run_tests.py")

    def write(self, rel: str, text: str) -> None:
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def run_runner(self, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"}
        return subprocess.run([sys.executable, "scripts/run_tests.py", *args], cwd=self.repo,
                              capture_output=True, text=True, env=env)

    def test_fixtures_and_non_test_files_are_not_suites(self):
        self.write("a/test_a.py", PASSING)
        self.write("tests/fixtures/pack/test_data.py", FAILING)
        self.write("b/helper.py", FAILING)
        self.write(".gitignore", "ignored/\n")
        self.write("ignored/test_i.py", FAILING)
        self.assertEqual(self.run_runner("--list").stdout.split(), ["a"])

    def test_all_suites_pass(self):
        self.write("a/test_a.py", PASSING)
        self.write("b/c/test_c.py", PASSING)
        r = self.run_runner()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_one_failing_suite_fails_the_run(self):
        self.write("a/test_a.py", PASSING)
        self.write("b/test_b.py", FAILING)
        r = self.run_runner()
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL  b", r.stdout)
        self.assertIn("ok    a", r.stdout)

    def test_finding_nothing_fails(self):
        r = self.run_runner()
        self.assertEqual(r.returncode, 1)
        self.assertIn("no test suite found", r.stderr)


if __name__ == "__main__":
    unittest.main()
