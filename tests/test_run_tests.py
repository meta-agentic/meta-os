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


class InInstance(unittest.TestCase):
    """Inside an instance only its own suites run; the framework repository runs them all.

    A throwaway framework holds the real runner and gate and two suites at the framework's
    paths; an instance clones it and adds a suite of its own.
    """

    GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
               "GIT_CONFIG_NOSYSTEM": "1", "HOME": tempfile.gettempdir()}

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="run-tests-inst-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.fw = self.tmp / "framework"
        for rel, text in {"scripts/run_tests.py": RUNNER.read_text(),
                          "scripts/validate_framework.py": (ROOT / "scripts" / "validate_framework.py").read_text(),
                          "tests/test_t.py": PASSING, "pipeline/tests/test_p.py": PASSING}.items():
            (self.fw / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.fw / rel).write_text(text, encoding="utf-8")
        self.git(self.fw.parent, "init", "-q", "-b", "main", str(self.fw))
        self.git(self.fw, "add", "-A")
        self.git(self.fw, "commit", "-q", "-m", "framework")

    def git(self, cwd: Path, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                              env={**os.environ, **self.GIT_ENV}).stdout.strip()

    def instance(self, with_upstream: bool = True) -> Path:
        inst = self.tmp / "instance"
        self.git(self.tmp, "clone", "-q", str(self.fw), str(inst))
        (inst / ".claude").mkdir()
        (inst / ".claude" / "CLAUDE.md").write_text("# instance\n")
        (inst / "automations" / "tests").mkdir(parents=True)
        (inst / "automations" / "tests" / "test_i.py").write_text(PASSING)
        self.git(inst, "add", "-A")
        self.git(inst, "commit", "-q", "-m", "instance")
        if with_upstream:
            self.git(inst, "remote", "add", "upstream", str(self.fw))
            self.git(inst, "fetch", "-q", "upstream")
        return inst

    def run_runner(self, cwd: Path, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items()
               if k not in ("GITHUB_STEP_SUMMARY", "META_OS_FRAMEWORK_REF")}
        return subprocess.run([sys.executable, "scripts/run_tests.py", *args], cwd=cwd,
                              capture_output=True, text=True, env=env)

    def test_the_framework_repository_runs_every_suite(self):
        r = self.run_runner(self.fw, "--list")
        self.assertEqual(r.stdout.split(), ["pipeline/tests", "tests"])
        self.assertNotIn("skipped", r.stderr)

    def test_an_instance_runs_only_its_own_suites_and_says_what_it_skipped(self):
        inst = self.instance()
        (inst / "tests" / "test_t.py").write_text(FAILING)   # would fail the run if it ran
        r = self.run_runner(inst)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok    automations/tests", r.stdout)
        self.assertNotIn("=== tests", r.stdout)
        self.assertNotIn("=== pipeline/tests", r.stdout)
        self.assertEqual(r.stderr.count("run_tests: skipped"), 1, r.stderr)
        self.assertIn("skipped the framework's suites pipeline/tests, tests", r.stderr)
        self.assertIn("framework suites run in the framework's CI; integrity is checked by the gate",
                      r.stderr)
        self.assertEqual(self.run_runner(inst, "--list").stdout.split(), ["automations/tests"])

    def test_without_a_framework_ref_an_instance_runs_everything(self):
        inst = self.instance(with_upstream=False)
        r = self.run_runner(inst, "--list")
        self.assertEqual(r.stdout.split(), ["automations/tests", "pipeline/tests", "tests"])
        self.assertNotIn("skipped", r.stderr)


if __name__ == "__main__":
    unittest.main()
