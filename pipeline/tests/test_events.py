"""Tests for the event producers: the inbox format, the step wrapper, the vault hooks, the remote watcher."""
from __future__ import annotations

import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.dirname(HERE)
sys.path.insert(0, PIPELINE)

from metaos_pipeline import events, remote_watch, step_wrap  # noqa: E402

NAME_RE = re.compile(r"^\d{8}T\d{6}\.\d{6}Z-[a-z_]+-[0-9a-f]{8}\.json$")
ENV = {**os.environ, "PYTHONPATH": PIPELINE}
RATE_LINE = json.dumps({"type": "rate_limit_event", "rate_limit_info": {
    "status": "rejected", "resetsAt": 1791946800, "rateLimitType": "seven_day"}})


def py(*args: str) -> list[str]:
    return [sys.executable, "-c", *args]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.inbox = os.path.join(self.tmp, "inbox")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def only(self, kind: str) -> dict:
        evs = [e for e in events.list_events(self.inbox) if e["kind"] == kind]
        self.assertEqual(len(evs), 1, evs)
        self.assertWellFormed(evs[0])
        return evs[0]

    def assertWellFormed(self, ev: dict):
        name = os.path.basename(ev["path"])
        self.assertRegex(name, NAME_RE)
        self.assertEqual(ev["id"] + ".json", name)
        self.assertEqual(set(ev) - {"path"}, {"schema", "id", "kind", "at", "source", "payload"})
        self.assertIn(ev["kind"], events.KINDS)


class InboxFormat(Base):
    def test_write_is_atomic_and_tmp_files_are_ignored(self):
        os.makedirs(self.inbox)
        with open(os.path.join(self.inbox, ".tmp-20260101T000000.000000Z-step_exit-00000000.json"), "w") as fh:
            fh.write("{partial")
        p = events.write_event(self.inbox, "vault_commit", "test", {"sha": "abc"})
        self.assertEqual([e["path"] for e in events.list_events(self.inbox)], [p])
        self.assertEqual([n for n in os.listdir(self.inbox) if n.startswith(".tmp") and "vault" in n], [])

    def test_oldest_first_and_kinds(self):
        events.write_event(self.inbox, "remote_change", "t", now=2_000_000_000)
        events.write_event(self.inbox, "vault_commit", "t", now=1_000_000_000)
        self.assertEqual([e["kind"] for e in events.list_events(self.inbox)], ["vault_commit", "remote_change"])
        with self.assertRaises(ValueError):
            events.write_event(self.inbox, "nonsense", "t")

    def test_cli_emits_one_event_and_refuses_reserved_kinds(self):
        r = subprocess.run([sys.executable, "-m", "metaos_pipeline.events", "emit", "vault_commit",
                            "--inbox", self.inbox, "--source", "cli", "--payload", '{"sha": "x"}'],
                           env=ENV, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.only("vault_commit")["payload"], {"sha": "x"})
        r = subprocess.run([sys.executable, "-m", "metaos_pipeline.events", "emit", "control",
                            "--inbox", self.inbox, "--source", "cli"], env=ENV, capture_output=True)
        self.assertNotEqual(r.returncode, 0)


class WindowReset(Base):
    def test_one_schedule_per_window_and_reset(self):
        calls = []
        self.assertTrue(events.schedule_window_reset(self.inbox, "five_hour", 1800000000, "a", spawn=calls.append))
        self.assertFalse(events.schedule_window_reset(self.inbox, "five_hour", 1800000000, "b", spawn=calls.append))
        self.assertTrue(events.schedule_window_reset(self.inbox, "seven_day", 1800000000, "a", spawn=calls.append))
        self.assertEqual(len(calls), 2)
        self.assertIn("--at", calls[0])
        self.assertEqual(events.list_events(self.inbox), [])  # markers are not events

    def test_failed_spawn_can_be_retried(self):
        def boom(argv):
            raise OSError("no fork")
        with self.assertRaises(OSError):
            events.schedule_window_reset(self.inbox, "w", 1, "a", spawn=boom)
        self.assertTrue(events.schedule_window_reset(self.inbox, "w", 1, "a", spawn=lambda argv: None))

    def test_the_one_shot_writes_one_window_reset(self):
        r = subprocess.run([sys.executable, "-m", "metaos_pipeline.events", "emit", "window_reset",
                            "--inbox", self.inbox, "--source", "t", "--at", "0",
                            "--payload", '{"window": "five_hour", "resets_at": 0}'], env=ENV, capture_output=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.only("window_reset")["payload"]["window"], "five_hour")


class StepWrapper(Base):
    def wrap(self, code: str, inbox: str | None = None, log: str | None = None) -> int:
        w = step_wrap.Wrapper(inbox or self.inbox, "run-1", log)
        return w.run(py(code))

    def test_step_exit_carries_code_pr_and_branch(self):
        log = os.path.join(self.tmp, "step.log")
        rc = self.wrap("print('outcome-branch: spec/x-1');"
                       "print('https://github.com/o/r/pull/7'); raise SystemExit(3)", log=log)
        self.assertEqual(rc, 3)
        p = self.only("step_exit")["payload"]
        self.assertEqual((p["run_id"], p["exit_code"], p["log"]), ("run-1", 3, log))
        self.assertEqual((p["pr_url"], p["outcome_branch"]), ("https://github.com/o/r/pull/7", "spec/x-1"))
        self.assertLessEqual(p["started"], p["ended"])
        with open(log) as fh:
            self.assertIn("pull/7", fh.read())

    def test_rate_limit_writes_one_event_and_schedules_once(self):
        scheduled = []
        orig = events.schedule_window_reset
        events.schedule_window_reset = lambda *a, **k: orig(*a, spawn=scheduled.append)
        try:
            rc = self.wrap(f"line = {RATE_LINE!r}; print(line); print(line); print('{{\"type\": \"x\"}}')")
        finally:
            events.schedule_window_reset = orig
        self.assertEqual(rc, 0)
        p = self.only("rate_limit")["payload"]
        self.assertEqual((p["status"], p["window"], p["resets_at"]), ("rejected", "seven_day", 1791946800))
        self.assertEqual(json.loads(p["raw"])["type"], "rate_limit_event")
        self.assertEqual(len(scheduled), 1)
        self.only("step_exit")

    def test_parser_is_defensive(self):
        for line in ("not json", "{bad", "[1, 2]", '{"status": "rejected"}', '{"rate_limit_info": "x"}'):
            self.assertIsNone(step_wrap.parse_rate_limit(line))
        r = step_wrap.parse_rate_limit('{"a": {"rateLimitInfo": {"status": "allowed_warning", '
                                       '"resets_at": "2026-10-23T10:00:00Z"}}}')
        self.assertEqual((r["status"], r["window"], r["resets_at"]), ("allowed_warning", "unknown", 1792749600))

    def test_unwritable_inbox_keeps_the_exit_code(self):
        blocker = os.path.join(self.tmp, "file")
        open(blocker, "w").close()
        r = subprocess.run([sys.executable, "-m", "metaos_pipeline.step_wrap", "--inbox",
                            os.path.join(blocker, "inbox"), "--run-id", "r", "--",
                            *py(f"print({RATE_LINE!r}); raise SystemExit(5)")],
                           env=ENV, capture_output=True, text=True)
        self.assertEqual(r.returncode, 5)
        self.assertIn("rate_limit", r.stdout)
        self.assertIn("step_exit event failed", r.stderr)


class VaultHook(Base):
    def setUp(self):
        super().setUp()
        self.repo = os.path.join(self.tmp, "repo")
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "-c", "user.name=t", "-c", "user.email=t@example.com",
                        "commit", "-q", "--allow-empty", "-m", "init"], check=True)
        self.head = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"],
                                   capture_output=True, text=True, check=True).stdout.strip()

    def hook(self, name: str, inbox: str | None) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "METAOS_PIPELINE_INBOX"}
        if inbox:
            env["METAOS_PIPELINE_INBOX"] = inbox
        return subprocess.run(["sh", os.path.join(PIPELINE, "hooks", name)], cwd=self.repo, env=env,
                              capture_output=True, text=True)

    def test_each_hook_writes_one_vault_commit(self):
        for name in ("post-commit", "post-merge"):
            inbox = os.path.join(self.tmp, name)
            self.assertEqual(self.hook(name, inbox).returncode, 0)
            self.inbox = inbox
            ev = self.only("vault_commit")
            self.assertEqual((ev["payload"]["sha"], ev["source"]), (self.head, name))

    def test_no_inbox_is_a_no_op_and_failure_exits_zero(self):
        self.assertEqual(self.hook("post-commit", None).returncode, 0)
        blocker = os.path.join(self.tmp, "file")
        open(blocker, "w").close()
        r = self.hook("post-commit", os.path.join(blocker, "inbox"))
        self.assertEqual(r.returncode, 0)
        self.assertIn("event not written", r.stderr)


class FakeGitHub(http.server.BaseHTTPRequestHandler):
    etag = '"v1"'
    body = {"head": {"sha": "aaa"}, "updated_at": "2026-10-23T00:00:00Z", "state": "open"}
    seen: list = []

    def do_GET(self):
        FakeGitHub.seen.append((self.path, self.headers.get("If-None-Match")))
        if self.headers.get("If-None-Match") == FakeGitHub.etag:
            self.send_response(304)
            self.end_headers()
            return
        data = json.dumps(FakeGitHub.body).encode()
        self.send_response(200)
        self.send_header("ETag", FakeGitHub.etag)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class RemoteWatcher(Base):
    def setUp(self):
        super().setUp()
        self.srv = http.server.HTTPServer(("127.0.0.1", 0), FakeGitHub)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.api = f"http://127.0.0.1:{self.srv.server_port}"
        FakeGitHub.seen = []
        FakeGitHub.etag = '"v1"'
        FakeGitHub.body = {"head": {"sha": "aaa"}, "updated_at": "2026-10-23T00:00:00Z", "state": "open"}

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def test_change_writes_one_event_and_304_writes_none(self):
        targets = remote_watch.parse_targets(["o/r#4"])
        state: dict = {}
        self.assertEqual(remote_watch.poll_once(targets, state, self.inbox, self.api), 1)
        self.assertEqual(self.only("remote_change")["payload"]["sha"], "aaa")
        self.assertEqual(remote_watch.poll_once(targets, state, self.inbox, self.api), 0)
        self.assertEqual(FakeGitHub.seen[-1], ("/repos/o/r/pulls/4", '"v1"'))  # conditional, answered 304
        self.assertEqual(len(events.list_events(self.inbox)), 1)

    def test_same_value_under_a_new_etag_writes_none_then_a_new_sha_writes_one(self):
        targets = remote_watch.parse_targets(["o/r@main"])
        FakeGitHub.body = {"commit": {"sha": "bbb"}}
        state: dict = {}
        remote_watch.poll_once(targets, state, self.inbox, self.api)
        FakeGitHub.etag = '"v2"'
        self.assertEqual(remote_watch.poll_once(targets, state, self.inbox, self.api), 0)
        FakeGitHub.etag, FakeGitHub.body = '"v3"', {"commit": {"sha": "ccc"}}
        self.assertEqual(remote_watch.poll_once(targets, state, self.inbox, self.api), 1)
        self.assertEqual(FakeGitHub.seen[0][0], "/repos/o/r/branches/main")
        self.assertEqual(len(events.list_events(self.inbox)), 2)

    def test_errors_are_not_fatal_and_targets_are_validated(self):
        targets = remote_watch.parse_targets(["o/r#1"])
        self.assertEqual(remote_watch.poll_once(targets, {}, self.inbox, "http://127.0.0.1:1"), 0)
        for bad in (["../x"], ["o/r"], "o/r#1", [3]):
            with self.assertRaises(ValueError):
                remote_watch.parse_targets(bad)


if __name__ == "__main__":
    unittest.main()
