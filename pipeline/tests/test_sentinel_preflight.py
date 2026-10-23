"""Tests for the sentinel and the pre-flight. Run: python3 -m unittest discover -s pipeline/tests

The sentinel tests use stalls of a fraction of a second (`--stall-minutes` takes fractions)
and a notifier that appends each message to a file, so they run in a few seconds.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import preflight  # noqa: E402
import sentinel  # noqa: E402

STALL = 0.01            # minutes: 0.6 s


class SentinelCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.inbox = os.path.join(self.tmp, "inbox")
        self.state = os.path.join(self.tmp, "state")
        self.log = os.path.join(self.tmp, "notified.log")
        os.makedirs(self.inbox)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def notify_cmd(self):
        code = "import sys; open(sys.argv[1], 'a').write(sys.argv[2] + '\\n')"
        return ["--notify-cmd", sys.executable, "-c", code, self.log]

    def notified(self) -> list[str]:
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as fh:
            return fh.read().splitlines()

    def event(self, name: str, age: float = 0.0) -> str:
        path = os.path.join(self.inbox, name)
        with open(path, "w") as fh:
            fh.write("{}")
        if age:
            t = time.time() - age
            os.utime(path, (t, t))
        return path

    def inbox_run(self, *extra: str) -> float:
        start = time.monotonic()
        rc = sentinel.main(["inbox", "--inbox", self.inbox, "--state", self.state,
                            "--stall-minutes", str(STALL), *extra, *self.notify_cmd()])
        self.assertEqual(rc, 0)
        return time.monotonic() - start


class InboxMode(SentinelCase):
    def test_empty_inbox_exits_at_once(self):
        self.assertLess(self.inbox_run(), 0.3)
        self.assertEqual(self.notified(), [])

    def test_tmp_files_are_not_events(self):
        self.event(".tmp-partial", age=60)
        self.assertLess(self.inbox_run(), 0.3)
        self.assertEqual(self.notified(), [])

    def test_stalled_event_notifies_exactly_once(self):
        self.event("0001-step-exit.json")
        runner = os.path.join(self.tmp, "runner.json")
        with open(runner, "w") as fh:
            json.dump({"actor": "runner", "last_action": "pass 7: plan"}, fh)
        took = self.inbox_run("--runner-state", runner)
        self.assertGreaterEqual(took, 0.5)
        msgs = self.notified()
        self.assertEqual(len(msgs), 1)
        self.assertIn("0001-step-exit.json", msgs[0])
        self.assertIn("pass 7: plan", msgs[0])
        self.inbox_run()                             # a second start: the same event, already notified
        self.assertEqual(len(self.notified()), 1)

    def test_each_stalled_event_notifies_once(self):
        self.event("a.json", age=60)
        self.event("b.json", age=60)
        self.inbox_run()
        self.assertEqual(len(self.notified()), 2)

    def test_event_consumed_before_deadline_does_not_notify(self):
        path = self.event("0002-commit.json")
        threading.Timer(0.2, os.remove, [path]).start()
        self.inbox_run()
        self.assertEqual(self.notified(), [])


class ProgressMode(SentinelCase):
    def setUp(self):
        super().setUp()
        self.marker = os.path.join(self.tmp, "armed", "run")
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(os.path.dirname(self.marker))
        os.makedirs(self.work)
        open(self.marker, "w").close()

    def progress_run(self):
        rc = sentinel.main(["progress", "--marker", self.marker, "--watch", self.work, "--state",
                            self.state, "--stall-minutes", str(STALL), *self.notify_cmd()])
        self.assertEqual(rc, 0)

    def touch_for(self, seconds: float, then_disarm_after: float):
        def worker():
            end = time.monotonic() + seconds
            n = 0
            while time.monotonic() < end:
                with open(os.path.join(self.work, f"out-{n % 3}"), "w") as fh:
                    fh.write(str(n))
                n += 1
                time.sleep(0.1)
            time.sleep(then_disarm_after)
            os.remove(self.marker)
        t = threading.Thread(target=worker)
        t.start()
        return t

    def test_scan_is_bounded_and_skips_build_and_dot_dirs(self):
        old = time.time() - 3600
        paths = {name: os.path.join(self.work, *name.split("/")) for name in
                 ("a/shallow", "a/b/c/deep", "node_modules/x", ".git/HEAD", "target/out")}
        for path in paths.values():
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w").close()
        for root, dirs, files in os.walk(self.work):
            for name in dirs + files:
                os.utime(os.path.join(root, name), (old, old))
        os.utime(self.work, (old, old))
        for name in ("a/b/c/deep", "node_modules/x", ".git/HEAD", "target/out"):
            os.utime(paths[name], None)              # changed now, but deep or in a skipped dir
            self.assertLess(sentinel.latest_mtime([self.work])[0], old + 1, name)
            os.utime(paths[name], (old, old))
        os.utime(paths["a/shallow"], None)
        self.assertEqual(sentinel.latest_mtime([self.work]), (os.stat(paths["a/shallow"]).st_mtime, paths["a/shallow"]))

    def test_unarmed_exits_at_once(self):
        os.remove(self.marker)
        self.progress_run()
        self.assertEqual(self.notified(), [])

    def test_no_notification_while_files_change(self):
        t = self.touch_for(1.5, then_disarm_after=0.0)
        self.progress_run()
        t.join()
        self.assertEqual(self.notified(), [])

    def test_silence_notifies_once_and_progress_rearms(self):
        def worker():
            time.sleep(1.5)                          # first silence: one notification
            with open(os.path.join(self.work, "out"), "w") as fh:
                fh.write("progress")
            time.sleep(1.5)                          # second silence after progress: one more
            os.remove(self.marker)
        t = threading.Thread(target=worker)
        t.start()
        self.progress_run()
        t.join()
        msgs = self.notified()
        self.assertEqual(len(msgs), 2, msgs)
        self.assertIn("no progress", msgs[0])


class Preflight(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.user = os.path.join(self.tmp, "user.json")
        os.makedirs(os.path.join(self.tmp, "proj", ".claude"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_pf(self, commands: list[str], user: dict, project: dict | None = None, mode: str | None = None):
        with open(self.user, "w") as fh:
            json.dump(user, fh)
        if project is not None:
            with open(os.path.join(self.tmp, "proj", ".claude", "settings.local.json"), "w") as fh:
                json.dump(project, fh)
        cmds = os.path.join(self.tmp, "commands.txt")
        with open(cmds, "w") as fh:
            fh.write("# step templates\n\n" + "\n".join(commands) + "\n")
        argv = ["--dir", os.path.join(self.tmp, "proj"), "--commands", cmds, "--user-settings", self.user]
        if mode:
            argv += ["--permission-mode", mode]
        out = io.StringIO()
        with redirect_stdout(out):
            rc = preflight.main(argv)
        return rc, out.getvalue()

    ALLOW = {"permissions": {"allow": ["Bash(git -C:*)", "Bash(python3 scripts/run_tests.py)", "Bash(gh pr view *)"]}}

    def test_allowed_commands_pass(self):
        rc, out = self.run_pf(["git -C {worktree} status", "python3 scripts/run_tests.py",
                               "gh pr view 12 --json state"], self.ALLOW)
        self.assertEqual(rc, 0, out)

    def test_prefix_rule_respects_word_boundary(self):
        rc, out = self.run_pf(["git -Cx status"], self.ALLOW)
        self.assertEqual(rc, 1)
        self.assertIn("no allow rule", out)

    def test_unmatched_command_is_refused(self):
        rc, out = self.run_pf(["python3 scripts/run_tests.py -v"], self.ALLOW)
        self.assertEqual(rc, 1)
        self.assertIn("NEEDS APPROVAL: python3 scripts/run_tests.py -v", out)

    def test_ask_rule_in_project_settings_is_refused(self):
        rc, out = self.run_pf(["git -C w push"], self.ALLOW, {"permissions": {"ask": ["Bash(git -C w push:*)"]}})
        self.assertEqual(rc, 1)
        self.assertIn("matched ask rule", out)

    def test_deny_rule_is_refused(self):
        user = {"permissions": {"allow": ["Bash"], "deny": ["Bash(rm:*)"]}}
        rc, out = self.run_pf(["rm -rf build"], user)
        self.assertEqual(rc, 1)
        self.assertIn("matched deny rule Bash(rm:*)", out)

    def test_compound_and_cd_commands_are_refused_even_if_allowed(self):
        user = {"permissions": {"allow": ["Bash"]}}
        for cmd in ("cd /repo", "git -C w fetch && git -C w status", "ls | head", "echo $(date)",
                    "make > log", "for f in a b; do echo $f; done", "FOO=1 make"):
            rc, out = self.run_pf([cmd], user)
            self.assertEqual(rc, 1, cmd)
        rc, out = self.run_pf(["git -C w commit -m 'a; b && c'"], user)
        self.assertEqual(rc, 0, out)                 # operators inside quotes are text

    def test_bypass_passes_with_caveat_and_names_risky_commands(self):
        rc, out = self.run_pf(["cd /repo && make"], {"permissions": {"defaultMode": "bypassPermissions"}})
        self.assertEqual(rc, 0)
        self.assertIn("caveat", out)
        self.assertIn("may still prompt", out)

    def test_cli_mode_overrides_settings(self):
        rc, _ = self.run_pf(["make"], {"permissions": {"defaultMode": "bypassPermissions"}}, mode="default")
        self.assertEqual(rc, 1)

    def test_unreadable_settings_is_a_usage_error(self):
        with open(self.user, "w") as fh:
            fh.write("{not json")
        cmds = os.path.join(self.tmp, "c.txt")
        with open(cmds, "w") as fh:
            fh.write("make\n")
        rc = preflight.main(["--dir", self.tmp, "--commands", cmds, "--user-settings", self.user])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
