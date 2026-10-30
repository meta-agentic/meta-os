#!/usr/bin/env python3
"""hooks/framework-status.sh: a check-only notice at session start, never an action.

    python3 -m unittest tests.test_framework_status

A throwaway upstream is built from THIS working tree (so the hook under test is the one about to
be committed), an instance is cloned from it and bootstrapped, and the hook is run the way the
harness runs it, with CLAUDE_PROJECT_DIR set. What is pinned: behind names
the command; current is silent; offline is silent and bounded; a repository from before the
one-repository layout gets the adoption hint; and the hook writes nothing but its own stamp.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from test_instance_lifecycle import GIT_ENV, ROOT, git, run, working_tree_files

HOOK_REL = "hooks/framework-status.sh"


class StatusHookBase(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="metaos-status-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.upstream = self.tmp / "upstream"
        self.upstream.mkdir()
        for rel in working_tree_files():
            src = ROOT / rel
            if src.is_file():
                dst = self.upstream / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst, follow_symlinks=False)
        git(self.upstream, "init", "-q", "-b", "main")
        git(self.upstream, "add", "-A")
        git(self.upstream, "commit", "-q", "-m", "framework v1")
        self.inst = self.tmp / "inst"
        git(self.tmp, "clone", "-q", str(self.upstream), str(self.inst))
        run(["scripts/bootstrap.sh", "--yes", "--name", "inst", "--upstream", str(self.upstream)], self.inst)
        git(self.inst, "add", "-A")
        git(self.inst, "commit", "-q", "-m", "instantiate")

    def upstream_commit(self, rel: str, text: str, msg: str = "framework change") -> None:
        p = self.upstream / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as fh:
            fh.write(text)
        git(self.upstream, "add", "-A")
        git(self.upstream, "commit", "-q", "-m", msg)

    def hook(self, inst: Path | None = None, **env) -> subprocess.CompletedProcess:
        inst = inst or self.inst
        t0 = time.time()
        r = subprocess.run(["bash", str(ROOT / HOOK_REL)], cwd=inst if inst.is_dir() else self.tmp, capture_output=True, text=True, timeout=60,
                           env={**os.environ, **GIT_ENV, "CLAUDE_PROJECT_DIR": str(inst), **env})
        r.elapsed = time.time() - t0
        return r

    def message(self, r: subprocess.CompletedProcess) -> str:
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotEqual(r.stdout.strip(), "", "expected a notice")
        out = json.loads(r.stdout)
        self.assertEqual(out["systemMessage"], out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertEqual(r.stdout.strip().count("\n"), 0, "one line")
        return out["systemMessage"]

    def fetch(self):
        git(self.inst, "fetch", "-q", "upstream")

    def reset_throttle(self):
        stamp = self.inst / git(self.inst, "rev-parse", "--git-path", "meta-os-status")
        stamp.unlink(missing_ok=True)


class NoticeTest(StatusHookBase):

    def test_current_is_silent(self):
        self.fetch()
        r = self.hook()
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_behind_prints_one_line_naming_the_command(self):
        self.upstream_commit("systems/new-note.md", "x\n")
        self.fetch()
        msg = self.message(self.hook())
        self.assertIn("the framework is 1 commit(s) behind: scripts/upgrade.sh --check", msg)

    def test_a_framework_that_moved_since_the_last_fetch_is_noticed_from_the_remote(self):
        self.fetch()
        self.upstream_commit("systems/new-note.md", "x\n")      # not fetched
        msg = self.message(self.hook())
        self.assertIn("the framework moved since your last fetch: scripts/upgrade.sh --check", msg)

    def test_an_edited_framework_path_is_reported(self):
        self.fetch()
        with (self.inst / "skills" / "_index.md").open("a") as fh:
            fh.write("\nan edit that belongs upstream\n")
        git(self.inst, "commit", "-q", "-am", "edit a framework path")
        msg = self.message(self.hook())
        self.assertIn("1 framework path(s) edited in this instance", msg)

    def test_template_drift_is_reported_and_an_acknowledged_one_is_not(self):
        self.upstream_commit("instance-template/root/_index.md", "\nnew line\n")
        self.fetch()
        git(self.inst, "merge", "-q", "--no-edit", "upstream/main")
        msg = self.message(self.hook())
        self.assertIn("instance-template/ changed since it was instantiated", msg)
        self.assertNotIn("behind", msg)
        run(["scripts/upgrade.sh", "--ack-template"], self.inst)
        git(self.inst, "commit", "-q", "-am", "ack the template")
        r = self.hook()
        self.assertEqual(r.stdout, "", r.stdout)

    def test_off_and_not_an_instance_are_silent(self):
        self.upstream_commit("systems/new-note.md", "x\n")
        self.fetch()
        self.assertEqual(self.hook(METAOS_STATUS_OFF="1").stdout, "")
        plain = self.tmp / "plain"
        git(self.tmp, "init", "-q", "-b", "main", str(plain))
        self.assertEqual(self.hook(plain).stdout, "")
        self.assertEqual(self.hook(self.tmp / "no-such-dir").stdout, "")

    def test_a_repository_from_before_the_layout_gets_the_adoption_hint(self):
        old = self.tmp / "old"
        git(self.tmp, "init", "-q", "-b", "main", str(old))
        (old / "CLAUDE.md").write_text("# my own contract\n")
        (old / "projects").mkdir()
        (old / "projects" / "a.md").write_text("x\n")
        git(old, "add", "-A")
        git(old, "commit", "-q", "-m", "old instance")
        git(old, "remote", "add", "upstream", str(self.upstream))
        msg = self.message(self.hook(old))
        self.assertIn("predates the one-repository layout", msg)
        self.assertIn("--adopt --dry-run", msg)

    def test_the_template_wires_the_hook_at_session_start(self):
        settings = json.loads((self.inst / ".claude" / "settings.json").read_text())
        cmds = [h["command"] for g in settings["hooks"]["SessionStart"] for h in g["hooks"]]
        self.assertTrue(any("hooks/framework-status.sh" in c for c in cmds), cmds)
        self.assertTrue((self.inst / "hooks" / "framework-status.sh").is_file())


class OfflineAndThrottleTest(StatusHookBase):

    def hang_the_remote(self):
        git(self.inst, "remote", "set-url", "upstream", "ext::sleep 30")
        return {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_1": "protocol.ext.allow", "GIT_CONFIG_VALUE_1": "always"}

    def test_offline_is_silent_and_bounded(self):
        self.fetch()
        env = self.hang_the_remote()
        r = self.hook(METAOS_STATUS_TIMEOUT="1", **env)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertLess(r.elapsed, 6, "the bound plus the process start, never the remote's 30 seconds")

    def test_the_failed_attempt_is_stamped_so_a_second_session_pays_nothing(self):
        self.fetch()
        env = self.hang_the_remote()
        self.hook(METAOS_STATUS_TIMEOUT="1", **env)
        r = self.hook(METAOS_STATUS_TIMEOUT="1", **env)
        self.assertEqual(r.stdout, "")
        self.assertLess(r.elapsed, 1.5, "within the ttl the remote is not asked again")

    def test_offline_still_reports_what_the_last_fetch_shows(self):
        self.upstream_commit("systems/new-note.md", "x\n")
        self.fetch()
        env = self.hang_the_remote()
        msg = self.message(self.hook(METAOS_STATUS_TIMEOUT="1", **env))
        self.assertIn("1 commit(s) behind", msg)

    def test_after_the_ttl_the_remote_is_asked_again(self):
        self.fetch()
        self.hook()
        self.upstream_commit("systems/new-note.md", "x\n")
        self.assertEqual(self.hook().stdout, "", "within the ttl the stamped remote answer stands")
        msg = self.message(self.hook(METAOS_STATUS_TTL="0"))
        self.assertIn("moved since your last fetch", msg)


class ReadOnlyTest(StatusHookBase):

    def snapshot(self) -> dict:
        gd = self.inst / ".git"
        tree = {}
        for p in sorted(self.inst.rglob("*")):
            rel = p.relative_to(self.inst).as_posix()
            if rel.startswith(".git/"):
                continue
            tree[rel] = hashlib.sha1(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink() else "-"
        gitfiles = {}
        for p in sorted(gd.rglob("*")):
            rel = p.relative_to(gd).as_posix()
            if p.is_file() and rel != "meta-os-status" and not rel.startswith(("logs/", "objects/")):
                gitfiles[rel] = hashlib.sha1(p.read_bytes()).hexdigest()
        objs = sorted(p.name for p in (gd / "objects").rglob("*") if p.is_file())
        return {"tree": tree, "git": gitfiles, "objects": objs,
                "refs": git(self.inst, "for-each-ref"), "head": git(self.inst, "rev-parse", "HEAD")}

    def test_the_hook_writes_nothing_but_its_own_stamp(self):
        self.upstream_commit("systems/new-note.md", "x\n")
        self.fetch()
        with (self.inst / "untracked-note.md").open("w") as fh:
            fh.write("a file in the working tree\n")
        before = self.snapshot()
        r = self.hook()
        self.message(r)                       # it did report: this is not a vacuous run
        self.assertEqual(self.snapshot(), before)
        self.assertTrue((self.inst / ".git" / "meta-os-status").is_file())
        self.reset_throttle()
        self.hook(METAOS_STATUS_TTL="0")
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
