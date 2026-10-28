"""The event-driven runner, on the dry-run harness: an injected clock, waiter and fake step engine, so nothing sleeps."""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import socket
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from metaos_pipeline import events, runner  # noqa: E402
from metaos_pipeline.fake_engine import FakeEngine  # noqa: E402
from metaos_pipeline.ledger import Ledger  # noqa: E402
import tick  # noqa: E402
import test_record  # noqa: E402
from test_pipeline import CFG, FakeVault, write  # noqa: E402

MODEL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "systems", "pipeline", "queueing-model.py")
# The backlog CLI's contract, faked: `transition KEY STATUS` rewrites the item's status, and logs the call.
BACKLOG = """import glob, os, re, sys
_, cmd, key, status = sys.argv[:4]
vault = os.environ["METAOS_VAULT"]
with open(os.path.join(vault, "calls.log"), "a") as fh:
    fh.write(f"{key} {status}\\n")
path = glob.glob(os.path.join(vault, "*", "*", key + ".md"))[0]
text = re.sub(r"(?m)^status: .*$", "status: " + status, open(path).read(), count=1)
open(path, "w").write(text)
"""
PR = "https://github.com/org/app/pull/7"


def setUpModule():
    test_record.setUpModule()


def tearDownModule():
    test_record.tearDownModule()


class Killed(BaseException):
    """The runner process dying mid-pass."""


class Base(unittest.TestCase):
    def setUp(self):
        self.v = FakeVault()
        self.tmp = tempfile.mkdtemp(prefix="runner-")
        self.inbox, self.work = os.path.join(self.tmp, "inbox"), os.path.join(self.tmp, "work")
        self.state = os.path.join(self.tmp, "record")
        cli = os.path.join(self.tmp, "backlog.py")
        write(cli, BACKLOG)
        self.t = time.time()
        self.cfg = dict(CFG, vault=self.v.dir, model_path=MODEL, backlog_cli=cli, vault_autocommit=False,
                        fairness_share=1.0, lane_prompt="Work on {id}", step_command=["engine", "{prompt_file}"],
                        regulator={"N0": 3, "N_min": 1, "N_max": 4, "budget": 20, "window_hours": 5, "lane_cap": 12},
                        _swarm_lanes=2, _config_path=os.path.join(self.tmp, "config.yaml"))
        os.makedirs(self.inbox)
        self.engine = FakeEngine(self.inbox, self.clock)

    def tearDown(self):
        self.v.cleanup()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def clock(self) -> float:
        return self.t

    def runner(self, led: Ledger | None = None, pid: int = 1111, host: str = "host-a", engine=None, waiter=None):
        return runner.Runner(self.cfg, led or Ledger(self.state), self.inbox, self.work, plan=tick.plan_pass,
                             record=tick.record_pass, engine=engine or self.engine, waiter=waiter, clock=self.clock,
                             host=host, pid=pid)

    def event(self, kind: str = "vault_commit", **payload) -> None:
        events.write_event(self.inbox, kind, "test", payload, now=self.t)

    def pass_(self, r: runner.Runner) -> list[str]:
        return r.run_pass(events.list_events(self.inbox))

    def status(self, key: str) -> str | None:
        return tick.vault_status(self.v.dir, key)

    def runs(self, led: Ledger | None = None) -> dict[str, dict]:
        return {s["run"]["item"]: {**s["run"], "lane_id": s["lane_id"]} for s in (led or Ledger(self.state)).lanes() if s.get("run")}

    def calls(self) -> list[str]:
        path = os.path.join(self.v.dir, "calls.log")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return fh.read().splitlines()

    def started(self) -> dict[str, dict]:
        """Two free slots, three admissible items, one event: one pass starts two steps."""
        r = self.runner()
        r.take_lease()
        self.event()
        self.pass_(r)
        return r


class PassTests(Base):
    def test_one_event_one_pass_starts_two_steps_and_an_exit_with_a_pr_goes_to_review(self):
        r = self.started()
        runs = self.runs()
        self.assertEqual(len(self.engine.spawned), 2)
        self.assertEqual(len(runs), 2)
        for key, run in runs.items():
            self.assertEqual(self.status(key), "IN PROGRESS")
            self.assertTrue(run["started"] and run["pid"] and run["log"])
        self.assertEqual(sorted(self.calls()), sorted(f"{k} IN PROGRESS" for k in runs))
        self.assertEqual(events.list_events(self.inbox), [], "a consumed event is deleted after the commit")
        key, run = sorted(runs.items())[0]
        self.engine.exit(run["run_id"], 0, pr_url=PR)
        self.pass_(r)
        self.assertEqual(self.status(key), "IN REVIEW")
        slot = next(s for s in Ledger(self.state).lanes() if s["lane_id"] == run["lane_id"])
        self.assertEqual((slot["history"][-1]["outcome"], slot["history"][-1]["pr"]), ("in_review", PR))
        self.assertEqual(len(self.engine.spawned), 3, "the freed slot takes the third admissible item")

    def test_no_event_no_pass(self):
        files = ("runs.ndjson", "events.ndjson", "state.json", "lanes.json")
        seen: list = []

        class Idle:
            def wait(w, timeout):
                seen.append((timeout, [os.path.getsize(os.path.join(self.state, f)) if os.path.exists(os.path.join(self.state, f)) else 0 for f in files]))
                self.t += 3600
                if len(seen) == 5:
                    r.stopping = True

        r = self.runner(waiter=Idle())
        r.run()
        self.assertEqual(len(seen), 5)
        self.assertEqual({t for t, _ in seen}, {None}, "nothing running: a blocking wait, no timer and no poll")
        self.assertEqual(len({tuple(s) for _, s in seen}), 1, "the record did not change while idle")
        self.assertEqual((r.passes, self.engine.spawned, self.calls()), (0, [], []))

    def test_a_silent_step_is_killed_and_its_item_given_back_with_the_reason(self):
        r = self.started()
        (ka, a), (kb, b) = sorted(self.runs().items())
        self.t += 240
        self.assertAlmostEqual(r.next_deadline(), 60, delta=1)
        self.engine.progress(b["run_id"])
        self.t += 120
        r.quiet_timers()
        stall = [e for e in events.list_events(self.inbox) if e["kind"] == "stall"]
        self.assertEqual(stall[0]["payload"]["run_ids"], [a["run_id"]], "only the step with no progress")
        self.cfg["_swarm_lanes"] = 0  # keep the freed slot empty, to read the reap alone
        self.pass_(r)
        self.assertIn(a["pid"], self.engine.killed)
        self.assertNotIn(b["pid"], self.engine.killed)
        self.assertEqual(self.status(ka), "REFINED")
        self.assertEqual(self.status(kb), "IN PROGRESS")
        led = Ledger(self.state)
        self.assertEqual(led.state()["retries"][ka], 1)
        filed = led.read_run(1)
        self.assertEqual((filed["item"], filed["outcome"]), (ka, "stalled"))
        self.assertIn("no progress for 5 min", filed["reason"])
        # The killed wrapper's own step_exit names a run no slot holds: consumed, nothing changes.
        self.pass_(r)
        self.assertEqual(Ledger(self.state).state()["retries"][ka], 1)

    def test_a_rate_limit_holds_new_starts_until_the_reset_and_leaves_running_steps(self):
        r = self.started()
        b, a = (run for _, run in sorted(self.runs().items()))  # b's [SPA] slot frees for the third [SPA] item
        self.engine.rate_limit(a["run_id"], resets_at=self.t + 3600)
        self.engine.exit(b["run_id"], 0, pr_url=PR)
        self.pass_(r)
        self.assertEqual(len(self.engine.spawned), 2, "the freed slot stays empty while starts are held")
        self.assertEqual(self.engine.killed, [])
        self.assertIn(a["item"], self.runs())
        self.event("window_reset", window="five_hour")
        self.pass_(r)
        self.assertEqual(len(self.engine.spawned), 3)

    def test_a_lost_reset_event_cannot_hold_the_pipe(self):
        r = self.started()
        b, a = (run for _, run in sorted(self.runs().items()))  # b's [SPA] slot frees for the third [SPA] item
        self.engine.rate_limit(a["run_id"], resets_at=self.t + 60)
        self.engine.exit(b["run_id"], 0, pr_url=PR)
        self.pass_(r)
        self.assertEqual(len(self.engine.spawned), 2)
        self.t += 61
        self.engine.progress(a["run_id"])
        self.event()  # any event: the pass is past the recorded reset
        self.pass_(r)
        self.assertEqual(len(self.engine.spawned), 3)

    def test_a_replayed_transition_is_not_run_twice(self):
        self.assertEqual(tick.backlog(self.cfg, "transition", "SPACEA-1", "IN PROGRESS")[0], 0)
        rc, msg = tick.backlog(self.cfg, "transition", "SPACEA-1", "IN PROGRESS")
        self.assertEqual((rc, self.calls()), (0, ["SPACEA-1 IN PROGRESS"]))
        self.assertIn("already IN PROGRESS", msg)


class RestartTests(Base):
    def test_a_restarted_runner_adopts_a_found_step_and_fails_an_absent_one(self):
        engine = self.engine

        class DiesOnSecondStart(FakeEngine):
            def spawn(e, argv):
                if engine.spawned:
                    raise Killed()
                return engine.spawn(argv)

        first = self.runner(engine=DiesOnSecondStart(self.inbox, self.clock))
        first.take_lease()
        self.event()
        with self.assertRaises(Killed):
            self.pass_(first)
        half = self.runs()
        self.assertEqual([r["started"] for r in half.values()], [None, None], "the forged half pass: both spawning")
        self.assertEqual(len(events.list_events(self.inbox)), 1, "its event is kept for the restarted runner")
        second = self.runner(pid=2222)  # pid 1111 is dead: the restart takes the lease
        second.run(max_passes=1)
        adopted = next(r for r in half.values() if r["run_id"] in engine.steps)
        absent = next(r for r in half.values() if r is not adopted)
        self.assertEqual(self.runs()[adopted["item"]]["pid"], engine.steps[adopted["run_id"]]["pid"])
        self.assertEqual(self.status(adopted["item"]), "IN PROGRESS")
        filed = Ledger(self.state).read_run(1)
        self.assertEqual((filed["run_id"], filed["outcome"]), (absent["run_id"], "failed_spawn"))
        self.assertNotIn(f"{absent['item']} IN PROGRESS", self.calls()[:1], "the absent run's item was never transitioned")
        ids = [a[a.index("--run-id") + 1] for a in engine.spawned]
        self.assertEqual(len(ids), len(set(ids)), "no run started twice")


class LeaseTests(Base):
    def test_one_runner_per_host_and_never_one_from_another_host(self):
        a = self.runner(pid=1111)
        self.engine.runners_alive.add(1111)
        a.take_lease()
        with self.assertRaises(runner.LeaseLost):
            self.runner(pid=2222).take_lease()
        self.engine.runners_alive.clear()
        with self.assertRaises(runner.LeaseLost):
            self.runner(pid=3333, host="host-b").take_lease()
        lost = [e for e in Ledger(self.state).events() if e["kind"] == "lease_lost"]
        self.assertEqual(len(lost), 2)
        self.assertIn("control lease take", lost[1]["reason"])
        self.assertTrue(tick.lease_holder(Ledger(self.state)), "plan and record refuse while it is held")

    def test_control_lease_take_moves_it_and_the_former_holder_stops(self):
        a = self.runner()
        a.take_lease()
        with contextlib.redirect_stdout(io.StringIO()):
            tick.cmd_control(self.cfg, Ledger(self.state), type("A", (), {"reason": "machine swap"})())
        self.event()
        with self.assertRaises(runner.LeaseLost):
            self.pass_(a)
        here = self.runner(pid=4444, host=socket.gethostname())
        here.take_lease()
        self.assertEqual(Ledger(self.state).state()["loop"]["epoch"], 3)

    def test_a_pass_is_one_commit_in_the_record_repository(self):
        repo = test_record.RecordRepo()
        try:
            led = Ledger(repo.clone("a"), remote=repo.url)
            r = self.runner(led=led)
            r.take_lease()
            self.event()
            self.pass_(r)
            self.assertEqual(len(self.engine.spawned), 2)
            log = repo.log()
            self.assertEqual(len(log), 3, log)  # seed, the lease, the pass (its checkpoint amended)
            self.assertTrue(log[0].startswith("pass "), log)
            self.assertEqual(test_record.git(led.dir, "status", "--porcelain"), "")
        finally:
            repo.cleanup()


class WaiterTests(unittest.TestCase):
    def setUp(self):
        self.inbox = tempfile.mkdtemp(prefix="inbox-")

    def tearDown(self):
        shutil.rmtree(self.inbox, ignore_errors=True)

    @unittest.skipUnless(hasattr(runner.select, "kqueue"), "kqueue only")
    def test_kqueue_wakes_on_a_write_to_the_inbox(self):
        w = runner.KqueueWaiter(self.inbox)
        events.write_event(self.inbox, "vault_commit", "test")
        t0 = time.monotonic()
        w.wait(30)
        self.assertLess(time.monotonic() - t0, 5)

    @unittest.skipUnless(runner.inotify_libc() is not None, "inotify only (Linux)")
    def test_inotify_wakes_on_a_write_to_the_inbox(self):
        w = runner.InotifyWaiter(self.inbox)
        events.write_event(self.inbox, "vault_commit", "test")
        t0 = time.monotonic()
        w.wait(30)
        self.assertLess(time.monotonic() - t0, 5)

    @unittest.skipUnless(runner.inotify_libc() is not None, "inotify only (Linux)")
    def test_inotify_returns_at_the_timeout_when_nothing_happens(self):
        w = runner.InotifyWaiter(self.inbox)
        t0 = time.monotonic()
        w.wait(0.2)
        self.assertLess(time.monotonic() - t0, 5)

    def test_the_platform_chooses_kernel_events_and_polls_only_without_them(self):
        from unittest import mock
        has_kq = hasattr(runner.select, "kqueue")
        w = runner.waiter_for(self.inbox)
        if has_kq:
            self.assertIsInstance(w, runner.KqueueWaiter)
        elif runner.inotify_libc() is not None:
            self.assertIsInstance(w, runner.InotifyWaiter)
        with mock.patch.object(runner, "select", mock.Mock(spec=[])), \
                mock.patch.object(runner, "inotify_libc", return_value=None), \
                mock.patch.object(runner.sys, "stderr") as err:
            w = runner.waiter_for(self.inbox)
        self.assertIsInstance(w, runner.PollWaiter)
        self.assertIn("no kernel file events", "".join(c.args[0] for c in err.write.call_args_list))

    def test_the_poll_fallback_looks_at_its_interval_and_returns_on_an_event(self):
        now, slept = [0.0], []

        def sleep(s):
            slept.append(s); now[0] += s

        w = runner.PollWaiter(self.inbox, seconds=2, clock=lambda: now[0], sleep=sleep)
        w.wait(5)
        self.assertEqual(slept, [2, 2, 1])
        events.write_event(self.inbox, "vault_commit", "test")
        w.wait(None)
        self.assertEqual(len(slept), 3, "an event waiting: no sleep")


class RealStepTests(Base):
    def test_steps_run_as_processes_under_the_wrapper(self):
        self.cfg["step_command"] = [sys.executable, "-m", "metaos_pipeline.fake_engine", "--line", "working",
                                    "--line", PR, "--exit", "0"]
        engine = runner.OsEngine()
        r = runner.Runner(self.cfg, Ledger(self.state), self.inbox, self.work, plan=tick.plan_pass,
                          record=tick.record_pass, engine=engine, host="host-a")
        r.take_lease()
        self.event()
        r.run_pass(events.list_events(self.inbox))
        self.assertEqual(len(engine.procs), 2)
        for p in engine.procs:
            p.wait(timeout=60)  # the wrapper writes step_exit before it exits
        exits = [e for e in events.list_events(self.inbox) if e["kind"] == "step_exit"]
        self.assertEqual(len(exits), 2)
        r.run_pass(events.list_events(self.inbox))
        for key in ("SPACEA-2", "SPACEA-4"):
            self.assertEqual(self.status(key), "IN REVIEW")
        with open(exits[0]["payload"]["log"], encoding="utf-8") as fh:
            self.assertIn("working", fh.read())
        for p in engine.procs:  # the third item's step, started into the freed slot
            p.wait(timeout=60)


class LaunchdTemplateTests(unittest.TestCase):
    def test_the_template_restarts_a_crash_only_and_holds_placeholders_only(self):
        import plistlib
        path = os.path.join(os.path.dirname(HERE), "runner.plist.template")
        with open(path, "rb") as fh:
            text = fh.read()
        doc = plistlib.loads(text)
        self.assertEqual(doc["KeepAlive"], {"SuccessfulExit": False})
        self.assertEqual(doc["ProgramArguments"][4:6], ["run", "--inbox"])
        self.assertNotRegex(text, rb"<string>/", "no absolute path: every path is a placeholder")


class SystemdTemplateTests(unittest.TestCase):
    DIR = os.path.join(os.path.dirname(HERE), "systemd")

    def read(self, name):
        with open(os.path.join(self.DIR, name), encoding="utf-8") as fh:
            return fh.read()

    def placeholders(self, text):
        import re
        return set(re.findall(r"__[A-Z_]+__", text))

    def test_the_runner_unit_restarts_a_crash_only_with_the_launchd_placeholders(self):
        unit = self.read("metaos-runner.service.template")
        self.assertIn("Restart=on-failure", unit)
        self.assertRegex(unit, r"ExecStart=__PYTHON__ __PIPELINE__/tick.py --config __CONFIG__ run --inbox __INBOX__")
        with open(os.path.join(os.path.dirname(HERE), "runner.plist.template"), encoding="utf-8") as fh:
            plist = fh.read()
        self.assertEqual(self.placeholders(unit), self.placeholders(plist))

    def test_the_sentinel_starts_on_an_inbox_change_never_on_an_interval(self):
        path = self.read("metaos-sentinel.path.template")
        self.assertIn("PathChanged=__INBOX__", path)
        self.assertIn("Unit=metaos-sentinel.service", path)
        service = self.read("metaos-sentinel.service.template")
        self.assertIn("Type=oneshot", service)
        self.assertIn("sentinel.py inbox --inbox __INBOX__", service)
        for text in (path, service):
            self.assertNotIn("OnCalendar", text)
            self.assertNotIn("OnUnitActiveSec", text)

    def test_every_path_is_a_placeholder(self):
        for name in os.listdir(self.DIR):
            if name.endswith(".template"):
                self.assertNotRegex(self.read(name), r"(?m)=/|\s/[a-z]", name)


if __name__ == "__main__":
    unittest.main()
