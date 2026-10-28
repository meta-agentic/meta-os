"""Lane slots: durable lanes bound to one project, one run at a time, drained before a rebind.

Run: python3 -m unittest discover -s pipeline/tests
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from metaos_pipeline import slots  # noqa: E402
from metaos_pipeline.ledger import Ledger  # noqa: E402
from test_pipeline import CFG, FakeVault, write  # noqa: E402
import tick  # noqa: E402


def working(n: int, project: str, item: str, session: str, session_project: str | None = None) -> dict:
    s = slots.new_slot(n)
    s.update({"project": project, "actual": "working",
              "run": {"run_id": f"r-1-{n:06x}", "kind": "work", "item": item, "space": "spacea", "branch": "b",
                      "sessions": [{"session_id": session, "project": session_project or project, "started": 1.0, "ended": None}],
                      "started": 1.0, "heartbeat": 1.0, "usage": [], "retries": 0}})
    return s


class Pipe:
    """A fake vault, a plain record directory and an estate config naming `swarm.lanes`."""

    def __init__(self, test: unittest.TestCase, lanes: int, prompt: str = "{id}"):
        self.v = FakeVault(); self.state = tempfile.mkdtemp(); self.inst = tempfile.mkdtemp()
        test.addCleanup(self.v.cleanup); test.addCleanup(shutil.rmtree, self.state, True); test.addCleanup(shutil.rmtree, self.inst, True)
        model = os.path.join(os.path.dirname(os.path.dirname(HERE)), "systems", "pipeline", "queueing-model.py")
        cfg = dict(CFG, vault=self.v.dir, model_path=model, backlog_cli=None, vault_autocommit=False, lane_prompt=prompt,
                   regulator={"N0": 3, "N_min": 1, "N_max": 4, "budget": 20, "window_hours": 5, "lane_cap": 12})
        import yaml
        self.cfg_path = os.path.join(self.inst, "config.yaml")
        write(self.cfg_path, yaml.safe_dump(cfg))
        self.set_lanes(lanes)
        self.n = 0

    def set_lanes(self, n: int) -> None:
        write(os.path.join(self.inst, "meta-os.config.json"), json.dumps({"swarm": {"lanes": n}}))

    def led(self) -> Ledger:
        return Ledger(self.state)

    def seed(self, lanes: list[dict]) -> None:
        write(os.path.join(self.state, "lanes.json"), json.dumps([{**l, "schema": 2} for l in lanes]))

    def run(self, *args: str) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = tick.main(["--config", self.cfg_path, "--state", self.state, *args])
        return rc, err.getvalue()

    def plan(self) -> dict:
        self.n += 1
        out = os.path.join(self.state, f"plan-{self.n}.json")
        self.run("plan", "--out", out)
        with open(out, encoding="utf-8") as fh:
            return json.load(fh)

    def record(self, results: dict) -> str:
        self.n += 1
        path = os.path.join(self.state, f"results-{self.n}.json")
        write(path, json.dumps(results))
        return self.run("record", "--results", path)[1]

    def slot(self, lane_id: str) -> dict:
        return next(l for l in self.led().lanes() if l["lane_id"] == lane_id)


class Assignment(unittest.TestCase):
    def test_the_first_pass_creates_swarm_lanes_slots_on_an_empty_record(self):
        p = Pipe(self, lanes=3)
        plan = p.plan()
        self.assertEqual([l["lane_id"] for l in p.led().lanes()], ["lane-1", "lane-2", "lane-3"])
        self.assertEqual([l["lane_id"] for l in plan["lanes"]], ["lane-1", "lane-2", "lane-3"])
        self.assertTrue(plan["spawn"] and all(s["lane_id"].startswith("lane-") and s["run_id"].startswith("r-1-") for s in plan["spawn"]))

    def test_a_bound_lane_takes_its_projects_item_over_an_earlier_one(self):
        # Must fail without the preference: the committed org/app item comes first in the ready order.
        p = Pipe(self, lanes=1)
        bound = slots.new_slot(1); bound["project"] = "org/infra"
        p.seed([bound])
        spawn = p.plan()["spawn"]
        self.assertEqual([(s["lane_id"], s["item"], s["repo"]) for s in spawn], [("lane-1", "SPACEA-4", "org/infra")])
        self.assertEqual([e for e in p.led().events() if e["kind"] == "lane_rebound"], [])

    def test_an_idle_lane_rebinds_to_another_project_with_an_event(self):
        p = Pipe(self, lanes=1)
        bound = slots.new_slot(1); bound["project"] = "org/elsewhere"
        p.seed([bound])
        self.assertEqual(p.plan()["spawn"][0]["repo"], "org/app")
        ev = [e for e in p.led().events() if e["kind"] == "lane_rebound"]
        self.assertEqual([(e["lane_id"], e["from"], e["to"], e["reason"]) for e in ev], [("lane-1", "org/elsewhere", "org/app", "assignment")])

    def test_a_working_slot_takes_no_second_item(self):
        p = Pipe(self, lanes=1)
        first = p.plan()["spawn"]
        self.assertEqual(len(first), 1)
        self.assertEqual(p.plan()["spawn"], [], "the slot is working from the plan on")
        with self.assertRaisesRegex(slots.InvariantBroken, "holds list"):
            s = working(1, "org/app", "SPACEA-1", "s1"); s["run"] = [s["run"], s["run"]]
            slots.check_invariant([s])

    def test_the_prompt_carries_the_lane_project_and_item_hash(self):
        p = Pipe(self, lanes=1, prompt="{lane_id}|{project}|{vault_sha}|{item_sha256}")
        s = p.plan()["spawn"][0]
        self.assertEqual(s["prompt"], f"lane-1|{s['repo']}||{s['item_ref']['sha256']}")


class Drain(unittest.TestCase):
    def test_a_rebind_mid_run_drains_first_then_files_the_run(self):
        p = Pipe(self, lanes=1)
        s = p.plan()["spawn"][0]
        p.record({"spawned": [{"lane_id": "lane-1", "run_id": s["run_id"], "ok": True, "session_id": "sess-1"}]})
        led = p.led()
        with led.locked():
            lanes = led.lanes()
            with self.assertRaisesRegex(slots.InvariantBroken, "cannot rebind while working"):
                slots.rebind(lanes[0], "org/infra", "control", led.event)
            slots.drain(lanes[0], "control", led.event, to="org/infra")  # the control plane's call, made directly
            led.save_lanes(lanes)
        self.assertEqual(p.plan()["spawn"], [], "a draining slot takes nothing new")
        self.assertEqual(p.slot("lane-1")["actual"], "draining")
        p.record({"checks": [{"lane_id": "lane-1", "status": "idle", "usage": {"cost_usd": 1.5}, "pr": {"url": "u/1", "number": 1}}]})
        slot = p.slot("lane-1")
        self.assertEqual((slot["actual"], slot["run"], slot["project"]), ("idle", None, "org/infra"))
        self.assertNotIn("drain", slot)
        self.assertEqual(slot["history"][-1]["outcome"], "in_review")
        run = p.led().read_run(1)
        self.assertEqual((run["run_id"], run["outcome"], run["pr"]["url"], run["project"]), (s["run_id"], "in_review", "u/1", "org/app"))
        self.assertTrue(all(x["ended"] for x in run["sessions"]), "the run's sessions are archived")
        kinds = [e["kind"] for e in p.led().events() if e["kind"] in ("lane_draining", "lane_ended", "lane_rebound")]
        self.assertEqual(kinds, ["lane_draining", "lane_ended", "lane_rebound"])
        self.assertEqual(p.led().state()["spent_finished"], 1.5)

    def test_lowering_swarm_lanes_drains_the_slots_above_it(self):
        emitted = []
        lanes = [working(1, "org/app", "SPACEA-1", "s1"), working(2, "org/infra", "SPACEA-4", "s2"), slots.new_slot(3)]
        slots.ensure(lanes, 1, lambda kind, **f: emitted.append((kind, f["lane_id"])))
        self.assertEqual([l["actual"] for l in lanes], ["working", "draining", "idle"])
        self.assertEqual(emitted, [("lane_draining", "lane-2")])
        self.assertFalse(slots.eligible(lanes[2], 1), "an idle slot above swarm.lanes takes nothing")
        slots.finish(lanes[1], "ended_empty", 9.0); slots.settle(lanes[1], lambda *a, **k: None)
        self.assertEqual((lanes[1]["actual"], lanes[1]["project"], len(lanes)), ("idle", "org/infra", 3), "it stays in the record")

    def test_history_keeps_the_last_five_runs(self):
        s = slots.new_slot(1)
        for n in range(7):
            slots.start(s, "org/app", n, 0.0, lambda *a, **k: None, kind="work", item=f"SPACEA-{n}")
            slots.finish(s, "ended_empty", float(n))
        self.assertEqual([h["item"] for h in s["history"]], [f"SPACEA-{n}" for n in range(2, 7)])


class Invariant(unittest.TestCase):
    def test_a_forged_session_under_two_projects_stops_the_pass(self):
        # Must fail if the check is skipped: each slot alone is consistent.
        p = Pipe(self, lanes=2)
        p.seed([working(1, "org/app", "SPACEA-1", "sess-x"), working(2, "org/infra", "SPACEA-4", "sess-x")])
        with self.assertRaises(SystemExit) as cm:
            p.plan()
        self.assertIn("session sess-x appears under 2 projects: org/app, org/infra", str(cm.exception))
        with self.assertRaises(SystemExit):
            p.record({"checks": []})

    def test_a_finished_sessions_id_reused_for_another_project_is_refused(self):
        # Must fail without the session index: the run under org/app is filed and gone from lanes.json.
        p = Pipe(self, lanes=1)
        s = p.plan()["spawn"][0]
        p.record({"spawned": [{"lane_id": "lane-1", "run_id": s["run_id"], "ok": True, "session_id": "sess-r"}]})
        p.record({"checks": [{"lane_id": "lane-1", "status": "idle", "branch_pushed": True}]})
        self.assertEqual(p.led().state()["sessions"], {"sess-r": s["repo"]})
        led = p.led()
        with led.locked():
            lanes = led.lanes()
            slots.start(lanes[0], "org/other", 9, 0.0, led.event, kind="work", item="SPACEA-1")
            led.save_lanes(lanes)
        with self.assertRaisesRegex(SystemExit, f"session sess-r served {s['repo']} and is now spawned under lane-1 for org/other"):
            p.record({"spawned": [{"lane_id": "lane-1", "ok": True, "session_id": "sess-r"}]})
        forged = working(1, "org/other", "SPACEA-1", "sess-r")
        with self.assertRaisesRegex(slots.InvariantBroken, "session sess-r appears under 2 projects"):
            slots.check_invariant([forged], {"sess-r": s["repo"]})

    def test_a_session_of_another_project_or_an_item_in_two_slots_is_refused(self):
        with self.assertRaisesRegex(slots.InvariantBroken, "session s1 serves org/infra under lane-1, which is bound to org/app"):
            slots.check_invariant([working(1, "org/app", "SPACEA-1", "s1", session_project="org/infra")])
        with self.assertRaisesRegex(slots.InvariantBroken, "item SPACEA-1 is held by both lane-1 and lane-2"):
            slots.check_invariant([working(1, "org/app", "SPACEA-1", "s1"), working(2, "org/app", "SPACEA-1", "s2")])


class Record(unittest.TestCase):
    def test_the_heartbeat_is_the_sessions_reported_activity(self):
        p = Pipe(self, lanes=1)
        s = p.plan()["spawn"][0]
        p.record({"spawned": [{"lane_id": "lane-1", "run_id": s["run_id"], "ok": True, "session_id": "sess-1"}]})
        p.record({"checks": [{"lane_id": "lane-1", "status": "working", "activity_ts": 4e9, "usage": {}}]})
        self.assertEqual(p.slot("lane-1")["run"]["heartbeat"], 4e9)
        p.record({"checks": [{"lane_id": "lane-1", "run_id": "r-0-stale", "status": "idle"}]})
        self.assertEqual(p.slot("lane-1")["actual"], "working", "a result for another run is ignored")

    def test_a_prototype_ledger_starts_the_slot_record_empty_and_says_so(self):
        p = Pipe(self, lanes=2)
        write(os.path.join(p.state, "lanes.json"), json.dumps([{"lane_id": "L1-abc", "status": "running", "item": "SPACEA-1"}]))
        rc, err = p.run("plan", "--out", os.path.join(p.state, "plan.json"))
        self.assertEqual(rc, 0)
        self.assertIn("1 row(s) of schema 1 or without slots: the slot record starts empty", err)
        self.assertEqual([l["lane_id"] for l in p.led().lanes()], ["lane-1", "lane-2"])
        with open(os.path.join(p.state, "lanes.prototype.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)[0]["lane_id"], "L1-abc")
        self.assertIn("slot_record", p.led().runs()[-1])

    def test_the_report_lists_the_slots(self):
        p = Pipe(self, lanes=2)
        s = p.plan()["spawn"][0]
        p.record({"spawned": [{"lane_id": s["lane_id"], "ok": False, "error": "no session"}]})
        out = os.path.join(p.state, "report.md")
        p.run("report", "--out", out)
        with open(out, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn(f"| {s['lane_id']} | {s['repo']} | idle |", text)
        self.assertIn(f"{s['item']} failed_spawn", text)
        self.assertIn("| lane-2 | — | idle |", text)


if __name__ == "__main__":
    unittest.main()
