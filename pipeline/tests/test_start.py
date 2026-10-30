"""The proven start, on the dry-run harness (`fake_engine.py`): nothing sleeps, nothing is launched.

A start missing any one of the four proofs is refused, naming it; a start whose launch command
exits 0 and does nothing is not a start. Run: python3 -m unittest discover -s pipeline/tests
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from metaos_pipeline import start  # noqa: E402
from metaos_pipeline.ledger import Ledger, StaleClone  # noqa: E402
import test_record  # noqa: E402
import tick  # noqa: E402
from test_runner import Base  # noqa: E402

LABEL = "org.example.sentinel-inbox"


def setUpModule():
    test_record.setUpModule()


def tearDownModule():
    test_record.tearDownModule()


class StartBase(Base):
    sentinel_up = True

    def setUp(self):
        super().setUp()
        self.led = Ledger(self.state)
        self.t0 = self.t
        self.preflight_calls = self.launch_calls = 0
        self.waits: list[float] = []

    def probe(self):
        return {"job": LABEL, "at": self.t} if self.sentinel_up else None

    def look(self, since):
        return start.observe(self.led, since=since, engine=self.engine, sentinel=self.probe, host="host-a",
                             clock=self.clock)

    def wait(self, seconds):
        self.waits.append(seconds)
        self.t += seconds

    def run_start(self, launch, preflight=None, deadline=30.0):
        def pre():
            self.preflight_calls += 1
            return preflight() if preflight else (0, "preflight: pass")

        def go():
            self.launch_calls += 1
            return launch()

        return start.start(self.led, preflight=pre, launch=go, look=self.look, wait=self.wait, clock=self.clock,
                           deadline=deadline, every=5.0)

    def launch_all(self):
        """What a healthy start does: the service manager starts the runner, which takes the lease and runs a pass."""
        self.t += 1
        r = self.started()
        self.engine.runners_alive.add(1111)
        return 0

    def events(self, kind):
        return [e for e in Ledger(self.state).events() if e["kind"] == kind]


class ProvenStartTests(StartBase):
    def test_all_four_seen_and_cited_is_started(self):
        rep = self.run_start(self.launch_all)
        self.assertTrue(rep["started"], rep)
        self.assertEqual(rep["missing"], [])
        p = rep["proofs"]
        self.assertEqual(p["runner"]["process"], "pid 1111 on host-a")
        self.assertEqual(p["runner"]["epoch"], 1)
        self.assertEqual(p["sentinel"]["job"], LABEL)
        self.assertIn(p["step"]["run_id"], [s["run"]["run_id"] for s in self.led.lanes() if s.get("run")])
        self.assertEqual(p["progress"]["run_id"], p["step"]["run_id"])
        self.assertGreater(p["progress"]["bytes"], 0)
        self.assertTrue(all(p[k].get("at") for k in start.PROOFS))
        text = start.render(rep)
        self.assertTrue(text.startswith("STARTED"))
        self.assertIn(p["step"]["run_id"], text)
        self.assertEqual(len(self.events("start_proven")), 1)

    def test_the_launch_command_exiting_zero_with_nothing_running_is_not_started(self):
        rep = self.run_start(lambda: 0)
        self.assertFalse(rep["started"])
        self.assertEqual(rep["launch_exit"], 0)
        self.assertEqual(rep["missing"], ["runner", "step", "progress"], "the sentinel job alone is not a start")
        self.assertTrue(self.waits, "it looked again until its deadline before giving up")
        self.assertEqual(sum(self.waits), 30.0)
        self.assertEqual(len(self.events("start_not_proven")), 1)
        self.assertEqual(self.events("start_proven"), [])

    def test_a_start_missing_the_runner_is_refused_and_names_it(self):
        def launch():
            self.launch_all()
            self.engine.runners_alive.clear()  # the runner process died after its pass
            return 0
        rep = self.run_start(launch)
        self.assertFalse(rep["started"])
        self.assertEqual(rep["missing"], ["runner"])
        self.assertIn("NOT STARTED: missing runner", start.render(rep))

    def test_a_lease_left_by_an_earlier_run_is_not_the_runner_of_this_start(self):
        r = self.runner()
        r.take_lease()  # an earlier run's runner, before this start began
        self.engine.runners_alive.add(1111)
        self.t += 100
        rep = self.run_start(lambda: 0)
        self.assertIn("runner", rep["missing"])

    def test_a_lease_held_on_another_machine_is_not_a_proof(self):
        def launch():
            self.launch_all()
            state = self.led.state()
            state["loop"]["host"] = "host-b"  # the record says another machine's runner holds the lease
            self.led.save_state(state)
            return 0
        rep = self.run_start(launch)
        self.assertEqual(rep["missing"], ["runner"])

    def test_a_launch_that_never_returns_does_not_hold_the_verdict_back(self):
        class Blocked:
            def poll(self):
                return None  # still running in the foreground

        rep = self.run_start(Blocked, deadline=30.0)
        self.assertFalse(rep["started"])
        self.assertIsNone(rep["launch_exit"])
        self.assertEqual(sum(self.waits), 30.0, "the deadline was enforced by looking, not by the launch")
        self.assertEqual(self.events("start_not_proven")[0]["launch_exit"], None)

    def test_the_verdict_is_said_before_it_is_recorded_and_a_record_failure_is_said_too(self):
        said, order = [], []

        def say(text):
            said.append(text)
            order.append("say")

        def broken(*a, **kw):
            order.append("record")
            raise StaleClone("the record's push was rejected 3 times")

        self.led.replay = broken
        rep = start.start(self.led, preflight=lambda: (0, ""), launch=lambda: 0, look=self.look, wait=self.wait,
                          clock=self.clock, deadline=0, every=5.0, say=say)
        self.assertEqual(order, ["say", "record", "say"])
        self.assertTrue(said[0].startswith("NOT STARTED"))
        self.assertIn("could not be recorded", said[1])
        self.assertIn("rejected 3 times", rep["not_recorded"])

    def test_a_step_of_an_earlier_run_is_not_the_first_step_of_this_start(self):
        self.started()  # a run from before: its step is alive and its log was written
        self.engine.runners_alive.add(1111)
        self.t += 100
        rep = self.run_start(lambda: 0)
        self.assertEqual(rep["missing"], ["runner", "step", "progress"])

    def test_a_start_missing_the_sentinel_is_refused_and_names_it(self):
        self.sentinel_up = False
        rep = self.run_start(self.launch_all)
        self.assertFalse(rep["started"])
        self.assertEqual(rep["missing"], ["sentinel"])
        self.assertIn("sentinel: NOT SEEN", start.render(rep))

    def test_a_start_missing_the_first_step_is_refused_and_names_it(self):
        def launch():
            self.launch_all()
            for rid in self.engine.steps:
                self.engine.steps[rid]["alive"] = False  # no step process carries a run id
            return 0
        rep = self.run_start(launch)
        self.assertFalse(rep["started"])
        self.assertEqual(rep["missing"], ["step", "progress"], "no step, so no progress to cite either")

    def test_a_start_missing_the_first_progress_is_refused_and_names_it(self):
        def launch():
            self.launch_all()
            for st in self.engine.steps.values():
                open(st["log"], "w").close()  # a step that has written nothing
                os.utime(st["log"], (self.t + 5, self.t + 5))  # recent, so only its size says so
            return 0
        rep = self.run_start(launch)
        self.assertFalse(rep["started"])
        self.assertEqual(rep["missing"], ["progress"])
        self.assertEqual(rep["proofs"]["step"]["run_id"] in self.engine.steps, True, "the step itself is cited")

    def test_progress_older_than_the_start_is_not_progress(self):
        def launch():
            self.launch_all()
            for st in self.engine.steps.values():
                os.utime(st["log"], (self.t0 - 500, self.t0 - 500))
            return 0
        rep = self.run_start(launch)
        self.assertEqual(rep["missing"], ["progress"])

    def test_it_waits_for_a_slow_proof_and_reports_started_when_it_comes(self):
        order = []

        def launch():
            self.t += 1
            order.append("launch")
            return 0

        def late(seconds):
            self.t += seconds
            order.append("wait")
            if order.count("wait") == 2:
                self.launch_all()

        rep = start.start(self.led, preflight=lambda: (0, ""), launch=launch, look=self.look, wait=late,
                          clock=self.clock, deadline=60.0, every=5.0)
        self.assertTrue(rep["started"])
        self.assertEqual(order, ["launch", "wait", "wait"])


class PreflightFirstTests(StartBase):
    def test_a_refusal_stops_the_start_with_its_reason_and_launches_nothing(self):
        rep = self.run_start(self.launch_all, preflight=lambda: (1, "NEEDS APPROVAL: git push (no allow rule matches)\n"))
        self.assertFalse(rep["started"])
        self.assertEqual(self.launch_calls, 0)
        self.assertEqual(self.engine.spawned, [])
        self.assertIn("NEEDS APPROVAL: git push", rep["refused"])
        self.assertIn("pre-flight refused", start.render(rep))
        self.assertEqual(len(self.events("start_refused")), 1)

    def test_the_preflight_runs_before_the_launch(self):
        order = []
        self.run_start(lambda: order.append("launch") or 0, preflight=lambda: order.append("preflight") or (0, ""),
                       deadline=0)
        self.assertEqual(order, ["preflight", "launch"])


class CliTests(StartBase):
    def appears(self, path, seconds=10.0):
        """The launch is started and not waited for: its effect shows a moment later."""
        end = time.time() + seconds
        while time.time() < end and not os.path.exists(path):
            time.sleep(0.05)
        return os.path.exists(path)

    def cli(self, launch_marker, commands, mode=None):
        cfg = os.path.join(self.tmp, "cfg.yaml")
        with open(cfg, "w") as fh:
            fh.write("vault: %s\n" % self.v.dir)
        cmds = os.path.join(self.tmp, "commands.txt")
        with open(cmds, "w") as fh:
            fh.write("\n".join(commands) + "\n")
        user = os.path.join(self.tmp, "user.json")
        with open(user, "w") as fh:
            json.dump({"permissions": {"allow": ["Bash(git -C:*)"]}}, fh)
        argv = ["--config", cfg, "--state", self.state, "start", "--dir", self.tmp, "--commands", cmds,
                "--user-settings", user, "--sentinel-job", LABEL, "--deadline", "0", "--",
                sys.executable, "-c", "open(%r, 'w').close()" % launch_marker]
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = tick.main(argv)
        return rc, out.getvalue()

    def test_a_preflight_refusal_stops_the_cli_start_before_the_launch(self):
        marker = os.path.join(self.tmp, "launched")
        rc, out = self.cli(marker, ["git push origin main"])
        self.assertEqual(rc, 1)
        self.assertIn("pre-flight refused", out)
        self.assertIn("git push origin main", out)
        time.sleep(0.5)
        self.assertFalse(os.path.exists(marker), "the launch command never ran")

    def test_a_passing_preflight_launches_and_a_launch_that_proves_nothing_is_not_started(self):
        marker = os.path.join(self.tmp, "launched")
        rc, out = self.cli(marker, ["git -C {worktree} status"])
        self.assertTrue(self.appears(marker), "the launch command was started")
        self.assertEqual(rc, 1, out)
        self.assertIn("NOT STARTED: missing runner, sentinel, step, progress", out)


    def test_a_launch_that_stays_in_the_foreground_still_gets_its_verdict_at_the_deadline(self):
        cfg = os.path.join(self.tmp, "cfg.yaml")
        with open(cfg, "w") as fh:
            fh.write("vault: %s\n" % self.v.dir)
        cmds = os.path.join(self.tmp, "commands.txt")
        with open(cmds, "w") as fh:
            fh.write("git -C {worktree} status\n")
        user = os.path.join(self.tmp, "user.json")
        with open(user, "w") as fh:
            json.dump({"permissions": {"allow": ["Bash(git -C:*)"]}}, fh)
        argv = ["--config", cfg, "--state", self.state, "start", "--dir", self.tmp, "--commands", cmds,
                "--user-settings", user, "--sentinel-job", LABEL, "--deadline", "0.2", "--every", "0.1", "--",
                sys.executable, "-c", "import time; time.sleep(3)"]
        out, t = io.StringIO(), time.time()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = tick.main(argv)
        self.assertLess(time.time() - t, 2.5, "the launch's 3 s sleep was not waited for")
        self.assertEqual(rc, 1)
        self.assertIn("NOT STARTED", out.getvalue())
        self.assertEqual(self.events("start_not_proven")[0]["launch_exit"], None)

    def test_a_pre_flight_usage_error_is_a_refusal_with_its_message(self):
        cfg = os.path.join(self.tmp, "cfg.yaml")
        with open(cfg, "w") as fh:
            fh.write("vault: %s\n" % self.v.dir)
        cmds = os.path.join(self.tmp, "commands.txt")
        with open(cmds, "w") as fh:
            fh.write("git status\n")
        marker = os.path.join(self.tmp, "launched")
        argv = ["--config", cfg, "--state", self.state, "start", "--dir", self.tmp, "--commands", cmds,
                "--permission-mode", "nonsense", "--sentinel-job", LABEL, "--deadline", "0", "--",
                sys.executable, "-c", "open(%r, 'w').close()" % marker]
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = tick.main(argv)
        self.assertEqual(rc, 1)
        self.assertIn("pre-flight refused", out.getvalue())
        self.assertIn("nonsense", out.getvalue())
        time.sleep(0.5)
        self.assertFalse(os.path.exists(marker))
        self.assertEqual(len(self.events("start_refused")), 1)

    def test_a_non_positive_every_or_a_negative_deadline_is_a_usage_error(self):
        for flags in (["--every", "0"], ["--every", "-1"], ["--deadline", "-1"]):
            with self.subTest(flags=flags), self.assertRaises(SystemExit) as cm, \
                    contextlib.redirect_stderr(io.StringIO()):
                tick.main(["--config", os.path.join(self.tmp, "cfg.yaml"), "start", "--dir", self.tmp,
                           "--commands", "x", "--sentinel-job", LABEL, *flags, "--", "true"])
            self.assertEqual(cm.exception.code, 2)


class ProbeTests(unittest.TestCase):
    class Done:
        def __init__(self, rc, stdout=""):
            self.returncode, self.stdout = rc, stdout

    LAUNCHCTL = ("gui/501/org.example.x = {\n\tstate = waiting\n\tpath = /home/u/org.example.x.plist\n"
                 "\twatch paths = {\n\t\t/data/runner/inbox\n\t}\n}\n")

    def launchd(self, text, inbox=None, rc=0):
        calls = []
        probe = start.service_job("org.example.x", inbox=inbox, platform="darwin", uid=501,
                                  run=lambda argv, **kw: calls.append(argv) or self.Done(rc, text))
        return probe(), calls

    def test_launchctl_print_of_the_label_on_macos(self):
        job, calls = self.launchd("")
        self.assertEqual(job["job"], "org.example.x")
        self.assertEqual(calls, [["launchctl", "print", "gui/501/org.example.x"]])

    def test_the_job_file_is_cited_and_the_job_must_watch_this_runs_inbox(self):
        job, _ = self.launchd(self.LAUNCHCTL, inbox="/data/runner/inbox")
        self.assertEqual(job["file"], "/home/u/org.example.x.plist")
        other, _ = self.launchd(self.LAUNCHCTL, inbox="/data/other/inbox")
        self.assertIsNone(other, "a sentinel for another inbox is not this run's")

    def test_a_job_that_shows_no_watch_paths_is_the_loaded_job_minimum(self):
        job, _ = self.launchd("gui/501/x = {\n\tstate = running\n}\n", inbox="/data/runner/inbox")
        self.assertEqual(job["job"], "org.example.x")
        self.assertIsNone(job["file"])

    def test_a_job_launchctl_does_not_know_is_not_seen(self):
        self.assertIsNone(self.launchd("", rc=113)[0])

    def test_systemctl_is_active_then_show_elsewhere(self):
        calls = []

        def run(argv, **kw):
            calls.append(argv)
            if "show" in argv:
                return self.Done(0, "FragmentPath=/etc/x.path\nPathChanged=/data/runner/inbox\nPathModified=\n")
            return self.Done(0)
        probe = start.service_job("x.path", inbox="/data/runner/inbox", run=run, platform="linux")
        self.assertEqual(probe()["file"], "/etc/x.path")
        self.assertEqual(calls[0], ["systemctl", "--user", "is-active", "--quiet", "x.path"])
        self.assertIsNone(start.service_job("x.path", inbox="/data/other", run=run, platform="linux")())

    def test_a_failing_systemctl_is_not_seen(self):
        self.assertIsNone(start.service_job("x.path", run=lambda argv, **kw: self.Done(3), platform="linux")())

    def test_a_missing_service_manager_is_not_seen(self):
        def boom(argv, **kw):
            raise FileNotFoundError(argv[0])
        self.assertIsNone(start.service_job("x", run=boom, platform="linux")())


if __name__ == "__main__":
    unittest.main()
