"""The vault write lock and the runner's vault commit: they take it, and a held lock defers the commit.

    python3 -m unittest discover -s pipeline/tests
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from metaos_pipeline import vaultlock  # noqa: E402
import tick  # noqa: E402


class VaultLockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = os.path.join(self.tmp.name, "vault")
        subprocess.run(["git", "init", "-q", self.vault], check=True)
        self.cfg = {"vault": self.vault, "vault_autocommit": True, "spaces": {}}

    def test_a_vault_commit_takes_the_lock_around_its_git_work(self):
        seen = []
        real = vaultlock.vault_lock

        def spy(vault, who, timeout=30.0):
            seen.append((str(vault), who))
            return real(vault, who, timeout)

        with mock.patch.object(vaultlock, "vault_lock", spy):
            out = tick.vault_commit(self.cfg, "m")
        self.assertEqual(out, "nothing to commit")
        self.assertEqual(seen, [(self.vault, "pipeline vault_commit")])

    def test_a_held_lock_defers_the_commit_naming_the_holder_and_commits_nothing(self):
        (open(os.path.join(self.vault, "x.md"), "w")).write("x")
        self.cfg["vault_lock_seconds"] = 0.3
        with vaultlock.vault_lock(self.vault, "the Stop-hook sweep"):
            # another process holds it: the same process would re-enter, so ask from a child
            code = ("import sys, json; sys.path.insert(0, %r); import tick; "
                    "print(tick.vault_commit(json.loads(sys.argv[1]), 'm'))" % os.path.dirname(HERE))
            r = subprocess.run([sys.executable, "-c", code, __import__("json").dumps(self.cfg)],
                               capture_output=True, text=True, timeout=60)
        self.assertIn("not committed: the vault write lock is held by", r.stdout)
        self.assertIn("the Stop-hook sweep", r.stdout)
        self.assertEqual(subprocess.run(["git", "-C", self.vault, "log", "--oneline"], capture_output=True,
                                        text=True).stdout.strip(), "")

    def test_autocommit_off_takes_no_lock(self):
        with mock.patch.object(vaultlock, "vault_lock", side_effect=AssertionError("locked")):
            self.assertEqual(tick.vault_commit({**self.cfg, "vault_autocommit": False}, "m"), "autocommit off")

    def test_the_lock_is_shared_by_a_worktree_and_the_path_is_the_common_git_dir(self):
        subprocess.run(["git", "-C", self.vault, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q",
                        "--allow-empty", "-m", "x"], check=True)
        wt = os.path.join(self.tmp.name, "wt")
        subprocess.run(["git", "-C", self.vault, "worktree", "add", "-q", "-b", "side", wt], check=True)
        self.assertEqual(vaultlock.lock_path(wt), vaultlock.lock_path(self.vault))
        self.assertTrue(vaultlock.lock_path(self.vault).endswith(os.path.join(".git", "vault-write.lock")))


if __name__ == "__main__":
    unittest.main()
