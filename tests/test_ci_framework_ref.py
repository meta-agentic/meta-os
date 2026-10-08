#!/usr/bin/env python3
"""scripts/ci_framework_ref.py: a CI checkout of an instance gets the framework ref.

    python3 -m unittest tests.test_ci_framework_ref

Each case builds a throwaway framework repository (holding the real script), an instance
that merged it and then added its own commit, and a CI-like checkout of either: a
depth-1 clone over the file transport with no `upstream` remote, which is what
`actions/checkout` leaves. No network.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci_framework_ref.py"
WORKFLOW = ROOT / ".github" / "workflows" / "check.yml"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1", "HOME": tempfile.gettempdir(),
}


def run(cmd, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120,
                          env={**os.environ, **GIT_ENV, **(env or {})})


def git(cwd: Path, *args: str) -> str:
    r = run(["git", *args], cwd)
    if r.returncode:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr}")
    return r.stdout.strip()


def commit(repo: Path, files: dict[str, str], msg: str) -> str:
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


class CiFrameworkRefTest(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="metaos-ciref-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.fw = self.tmp / "framework"
        self.fw.mkdir()
        git(self.fw, "init", "-q", "-b", "main")
        self.v1 = commit(self.fw, {"README.md": "framework\n",
                                   "scripts/ci_framework_ref.py": SCRIPT.read_text()}, "v1")
        self.fw_url = f"file://{self.fw}"

    def instance(self, shared_history: bool = True) -> Path:
        inst = self.tmp / "instance"
        if shared_history:
            git(self.tmp, "clone", "-q", self.fw_url, str(inst))
        else:   # a template snapshot: the framework's files, none of its history
            inst.mkdir()
            git(inst, "init", "-q", "-b", "main")
            shutil.copytree(self.fw / "scripts", inst / "scripts")
        commit(inst, {".claude/CLAUDE.md": "# instance\n", "notes/mine.md": "x\n"}, "instance")
        return inst

    def ci_checkout(self, src: Path) -> Path:
        ci = self.tmp / "ci"
        git(self.tmp, "clone", "-q", "--depth", "1", f"file://{src}", str(ci))
        self.assertEqual(git(ci, "rev-parse", "--is-shallow-repository"), "true")
        return ci

    def script(self, ci: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return run(["python3", "scripts/ci_framework_ref.py", *args], ci,
                   env={"META_OS_UPSTREAM_URL": self.fw_url, **(env or {})})

    def test_the_framework_repository_is_left_alone(self):
        ci = self.ci_checkout(self.fw)
        r = self.script(ci)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("framework repository itself", r.stdout)
        self.assertNotIn("upstream", git(ci, "remote"))
        self.assertEqual(git(ci, "rev-parse", "--is-shallow-repository"), "true")

    def test_an_instance_gets_upstream_history_and_the_merged_framework_commit(self):
        inst = self.instance()
        commit(self.fw, {"README.md": "framework v2\n"}, "v2")   # not merged into the instance
        ci = self.ci_checkout(inst)
        r = self.script(ci)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(git(ci, "remote", "get-url", "upstream"), self.fw_url)
        self.assertEqual(git(ci, "rev-parse", "--is-shallow-repository"), "false")
        self.assertEqual(git(ci, "merge-base", "HEAD", "upstream/main"), self.v1)
        self.assertIn(f"framework at {self.v1[:12]}", r.stdout)

    def test_the_url_flag_wins_over_the_environment(self):
        ci = self.ci_checkout(self.instance())
        r = self.script(ci, "--url", self.fw_url, env={"META_OS_UPSTREAM_URL": "file:///nowhere"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(git(ci, "remote", "get-url", "upstream"), self.fw_url)

    def test_an_existing_upstream_remote_is_kept(self):
        ci = self.ci_checkout(self.instance())
        git(ci, "remote", "add", "upstream", self.fw_url)
        r = self.script(ci, "--url", "file:///nowhere")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("keeping the existing 'upstream' remote", r.stdout)
        self.assertEqual(git(ci, "remote", "get-url", "upstream"), self.fw_url)

    def test_an_instance_without_shared_history_fails_instead_of_guessing(self):
        ci = self.ci_checkout(self.instance(shared_history=False))
        r = self.script(ci)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("shares no history with upstream/main", r.stderr)

    def test_an_unreachable_framework_fails(self):
        ci = self.ci_checkout(self.instance())
        r = self.script(ci, "--url", f"file://{self.tmp / 'nowhere'}")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("failed", r.stderr)

    def test_both_gate_jobs_prepare_the_ref_before_the_framework_gate(self):
        jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
        for job in ("gates", "debt"):
            with self.subTest(job=job):
                runs = [s.get("run", "") for s in jobs[job]["steps"]]
                prep = [i for i, r in enumerate(runs) if "scripts/ci_framework_ref.py" in r]
                gate = [i for i, r in enumerate(runs) if "scripts/validate_framework.py" in r]
                self.assertTrue(prep and gate, runs)
                self.assertLess(prep[0], gate[0])


if __name__ == "__main__":
    unittest.main()
