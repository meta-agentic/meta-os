"""The public-repo instance-data gate (scripts/public_repo_gate.py), driven through its command
line against throwaway clones, with a fake `gh` on PATH standing in for the host.

Every test is a must-fail case first: each names the leak the gate exists to stop. The synthetic
keys use six-letter prefixes so that this file never trips the framework's own key scan.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GATE = Path(__file__).resolve().parent.parent / "scripts" / "public_repo_gate.py"
KEY = "SPACEA-12"
HOME_PATH = "/" + "Users" + "/someone/notes.md"   # built at runtime: the framework scan reads this file


class Clone:
    def __init__(self, root: Path, slug: str = "acme/widget"):
        self.dir = root / "clone"
        self.dir.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "dev@example.com")
        self.git("config", "user.name", "dev")
        self.git("remote", "add", "origin", f"https://github.com/{slug}.git")
        (self.dir / "README.md").write_text("widget\n")
        self.git("add", "README.md")
        self.git("commit", "-q", "--no-verify", "-m", "initial")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def git(self, *args: str, env=None) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.dir), *args], capture_output=True, text=True, env=env)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text('#!/bin/sh\n[ -n "$FAKE_VISIBILITY" ] || exit 1\necho "$FAKE_VISIBILITY"\n')
        gh.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                    "FAKE_VISIBILITY": "public"}
        self.config = self.tmp / "meta-os.config.json"
        self.write_config({"keyPattern": r"(?<![A-Za-z0-9])(?:SPACEA|SPACEB)-S?[0-9]+",
                           "exemptRepos": ["acme/tracker"]})

    def tearDown(self):
        subprocess.run(["rm", "-rf", str(self.tmp)])

    def write_config(self, gate: dict):
        self.config.write_text(json.dumps({"publicRepoGate": gate}))

    def gate(self, *args: str, config=True) -> subprocess.CompletedProcess:
        # Without config means no publicRepoGate object. An empty file stands for it, so the
        # result never depends on the meta-os.config.json of the repository running the test.
        bare = self.tmp / "no-gate-config.json"
        if not config:
            bare.write_text("{}")
        pre = ["--config", str(self.config if config else bare)]
        return subprocess.run([sys.executable, str(GATE), *pre, *args],
                              capture_output=True, text=True, env=self.env)

    def commit(self, clone: Clone, message: str) -> subprocess.CompletedProcess:
        (clone.dir / "change.txt").write_text(message)
        clone.git("add", "change.txt")
        return clone.git("commit", "-q", "-m", message, env=self.env)

    # ---- visibility
    def test_visibility_fails_closed(self):
        self.env["FAKE_VISIBILITY"] = "private"
        self.assertEqual(self.gate("visibility", "acme/widget").stdout.strip(), "private")
        self.env["FAKE_VISIBILITY"] = ""          # gh fails: unknown must not read as private
        self.assertEqual(self.gate("visibility", "acme/widget").stdout.strip(), "public")

    # ---- lane setup and the commit-msg hook
    def test_setup_installs_a_hook_that_rejects_a_key(self):
        c = Clone(self.tmp)
        self.assertEqual(self.gate("setup", "-C", str(c.dir)).returncode, 0)
        r = self.commit(c, f"fix the parser ({KEY})")
        self.assertNotEqual(r.returncode, 0, "a key in a public repo's commit message must be rejected")
        self.assertIn(KEY, r.stderr)
        self.assertEqual(self.commit(c, "fix the parser").returncode, 0)

    def test_setup_on_a_private_repo_installs_nothing(self):
        self.env["FAKE_VISIBILITY"] = "private"
        c = Clone(self.tmp)
        self.assertIn("private", self.gate("setup", "-C", str(c.dir)).stdout)
        self.assertEqual(self.commit(c, f"fix the parser ({KEY})").returncode, 0)

    def test_setup_flags_a_keyed_branch_name(self):
        c = Clone(self.tmp)
        c.git("checkout", "-q", "-b", f"feat/{KEY}-parser")
        self.assertEqual(self.gate("setup", "-C", str(c.dir)).returncode, 1)

    def test_setup_never_replaces_a_foreign_hook_or_a_hooks_path(self):
        c = Clone(self.tmp)
        hook = c.dir / ".git" / "hooks" / "commit-msg"
        hook.write_text("#!/bin/sh\nexit 0\n")
        self.assertEqual(self.gate("setup", "-C", str(c.dir)).returncode, 2)
        self.assertEqual(hook.read_text(), "#!/bin/sh\nexit 0\n")
        hook.unlink()
        c.git("config", "core.hooksPath", ".githooks")
        self.assertEqual(self.gate("setup", "-C", str(c.dir)).returncode, 2)

    def test_exempt_repo_may_carry_keys_but_never_a_machine_path(self):
        c = Clone(self.tmp, "acme/tracker")
        msg = self.tmp / "msg"
        msg.write_text(f"close {KEY}\n")
        self.assertEqual(self.gate("commit-msg", "-C", str(c.dir), str(msg)).returncode, 0)
        msg.write_text(f"see {HOME_PATH}\n")
        self.assertEqual(self.gate("commit-msg", "-C", str(c.dir), str(msg)).returncode, 1)

    def test_without_config_the_framework_key_shape_applies(self):
        c = Clone(self.tmp)
        msg = self.tmp / "msg"
        msg.write_text("close " + "AB" + "-7\n# a comment line is not the message: " + KEY + "\n")
        r = self.gate("commit-msg", "-C", str(c.dir), str(msg), config=False)
        self.assertEqual(r.returncode, 1)
        msg.write_text("upgrade to UTF-8 and SHA-256\n")
        self.assertEqual(self.gate("commit-msg", "-C", str(c.dir), str(msg), config=False).returncode, 0)

    def test_extra_path_prefix_is_instance_data(self):
        self.write_config({"pathPrefixes": ["/Volumes/estate/"]})
        c = Clone(self.tmp)
        msg = self.tmp / "msg"
        msg.write_text("data from /Volumes/estate/raw\n")
        self.assertEqual(self.gate("commit-msg", "-C", str(c.dir), str(msg)).returncode, 1)

    # ---- pre-PR
    def pre_pr(self, c: Clone) -> subprocess.CompletedProcess:
        return self.gate("pre-pr", "-C", str(c.dir), "--base", "origin/main")

    def test_pre_pr_flags_every_surface(self):
        cases = {
            "branch name": lambda c: c.git("checkout", "-q", "-b", f"feat/{KEY}"),
            "commit": lambda c: self.commit_no_hook(c, "a.txt", "x\n", f"work on {KEY}"),
            "added line": lambda c: self.commit_no_hook(c, "a.txt", f"see {KEY}\n", "add a"),
            "file name": lambda c: self.commit_no_hook(c, f"{KEY}.md", "x\n", "add notes"),
            "machine path": lambda c: self.commit_no_hook(c, "a.txt", f"{HOME_PATH}\n", "add a"),
        }
        for surface, leak in cases.items():
            with self.subTest(surface=surface):
                root = self.tmp / surface.replace(" ", "-")
                root.mkdir()
                c = Clone(root)
                if surface != "branch name":
                    c.git("checkout", "-q", "-b", "feat/parser")
                leak(c)
                r = self.pre_pr(c)
                self.assertEqual(r.returncode, 1, f"{surface}: {r.stderr}")
                self.assertIn(surface, r.stderr)

    def test_pre_pr_passes_a_clean_branch_and_skips_a_private_repo(self):
        c = Clone(self.tmp)
        c.git("checkout", "-q", "-b", "feat/parser")
        self.commit_no_hook(c, "a.txt", "parser\n", "fix the parser")
        self.assertEqual(self.pre_pr(c).returncode, 0)
        self.commit_no_hook(c, "b.txt", f"{KEY}\n", "add b")
        self.env["FAKE_VISIBILITY"] = "private"
        self.assertEqual(self.pre_pr(c).returncode, 0)

    def test_pre_pr_fails_closed_on_a_git_error(self):
        # An orphan branch has no merge base: the diff cannot be judged, so it must not pass.
        c = Clone(self.tmp)
        c.git("checkout", "-q", "--orphan", "feat/orphan")
        self.commit_no_hook(c, "a.txt", f"see {KEY}\n", "add a")
        r = self.pre_pr(c)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("merge-base", r.stderr)

    def test_pre_pr_scans_the_pr_title_body_and_a_plus_plus_line(self):
        c = Clone(self.tmp)
        c.git("checkout", "-q", "-b", "feat/parser")
        self.commit_no_hook(c, "a.txt", "parser\n", "fix the parser")
        body = self.tmp / "body.md"
        body.write_text(f"closes {KEY}\n")
        base = ["pre-pr", "-C", str(c.dir), "--base", "origin/main"]
        self.assertEqual(self.gate(*base, "--title", f"{KEY}: fix").returncode, 1)
        self.assertEqual(self.gate(*base, "--body-file", str(body)).returncode, 1)
        self.commit_no_hook(c, "b.txt", f"+ {KEY}\n", "add b")     # the diff line reads '++ <key>'
        self.assertEqual(self.pre_pr(c).returncode, 1)

    def test_a_bad_config_is_an_error_not_a_fallback(self):
        c = Clone(self.tmp)
        msg = self.tmp / "msg"
        msg.write_text("clean\n")
        for gate in ({"keyPatern": "x"}, {"exemptRepos": "acme/tracker"}, {"keyPattern": "("}):
            with self.subTest(gate=gate):
                self.write_config(gate)
                self.assertEqual(self.gate("commit-msg", "-C", str(c.dir), str(msg)).returncode, 2)

    def test_hook_scans_comment_looking_lines_that_commit_m_records(self):
        # `git commit -m` keeps '#' and scissors lines verbatim, so the hook must not skip them.
        c = Clone(self.tmp)
        self.assertEqual(self.gate("setup", "-C", str(c.dir)).returncode, 0)
        (c.dir / "change.txt").write_text("x\n")
        c.git("add", "change.txt")
        r = c.git("commit", "-q", "-m", "fix", "-m", f"# see {KEY}", env=self.env)
        self.assertNotEqual(r.returncode, 0, "a '#' line recorded by -m must be scanned")
        r = c.git("commit", "-q", "-m", "fix", "-m", f"# ------------------------ >8 ------------------------\n{KEY}",
                  env=self.env)
        self.assertNotEqual(r.returncode, 0, "text after a scissors line recorded by -m must be scanned")

    @staticmethod
    def commit_no_hook(c: Clone, name: str, text: str, message: str):
        (c.dir / name).write_text(text)
        c.git("add", name)
        c.git("commit", "-q", "--no-verify", "-m", message)


if __name__ == "__main__":
    unittest.main()
