"""Unit tests for the deterministic half of the pipeline. Run: python3 -m unittest discover -s pipeline/tests"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from metaos_pipeline import controller, readyset, speculate  # noqa: E402
from metaos_pipeline.ledger import Ledger, usage_delta  # noqa: E402
import tick  # noqa: E402


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def item(id_: str, status: str, title: str, deps=(), kind="story", labels=(), points=3):
    tier = {"TO DO": "raw", "REFINED": "raw", "PLANNED": "raw", "IN PROGRESS": "wiki", "DONE": "output"}[status]
    return tier, f"""---
kind: {kind}
id: {id_}
title: '{title}'
status: {status}
space: {id_.split('-')[0].lower()}
storyPoints: {points}
priority: P2
labels: [{', '.join(labels)}]
dependencies: [{', '.join(deps)}]
---
body of {id_}
"""


class FakeVault:
    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="vault-")
        write(os.path.join(self.dir, "aaa", "sprints", "AAA-S1.md"),
              "---\nkind: sprint\nspace: aaa\nsprintId: AAA-S1\nstate: active\ncommitted:\n- AAA-2\n---\n")
        for id_, st, title, deps, labels in [
            ("AAA-1", "REFINED", "[SPA] first thing", (), ()),
            ("AAA-2", "REFINED", "[SPA] second thing committed", (), ()),
            ("AAA-3", "REFINED", "[INF] infra thing", ("AAA-5",), ()),
            ("AAA-4", "REFINED", "[INF] infra other", (), ()),
            ("AAA-5", "TO DO", "[SPA] not ready", (), ()),
            ("AAA-6", "REFINED", "[SPA] blocked one", (), ("blocked",)),
            ("AAA-9", "DONE", "done dep", (), ()),
        ]:
            tier, text = item(id_, st, title, deps, labels=labels)
            write(os.path.join(self.dir, "aaa", tier, f"{id_}.md"), text)
        # a space without an active sprint: never ready
        tier, text = item("BBB-1", "REFINED", "[X] orphan")
        write(os.path.join(self.dir, "bbb", tier, "BBB-1.md"), text)

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


CFG = {
    "spaces": {"aaa": {"repo": "org/app", "repo_by_tag": {"INF": "org/infra"}, "branch_prefix": "AAA/"},
               "bbb": {"repo": "org/b"}},
    "ready_statuses": ["REFINED"], "fairness_share": 0.5,
    "regulator": {"N": 4},
}


class ReadySetTests(unittest.TestCase):
    def setUp(self):
        self.v = FakeVault()

    def tearDown(self):
        self.v.cleanup()

    def test_ready_filters_and_orders(self):
        ready = readyset.ready_items(self.v.dir, CFG)
        ids = [i.id for i in ready]
        self.assertEqual(ids[0], "AAA-2", "committed item first")
        self.assertIn("AAA-1", ids); self.assertIn("AAA-4", ids)
        self.assertNotIn("AAA-3", ids, "dependency not DONE")
        self.assertNotIn("AAA-5", ids, "TO DO is not ready")
        self.assertNotIn("AAA-6", ids, "blocked label")
        self.assertNotIn("BBB-1", ids, "no active sprint")
        infra = next(i for i in ready if i.id == "AAA-4")
        self.assertEqual(infra.repo, "org/infra"); self.assertTrue(infra.branch.startswith("AAA/AAA-4-"))

    def test_public_repo_branch_carries_no_id(self):
        cfg = {**CFG, "spaces": {"aaa": {**CFG["spaces"]["aaa"], "public": True, "branch_prefix": "pipeline/"}}}
        ready = readyset.ready_items(self.v.dir, cfg)
        for it in ready:
            self.assertTrue(it.branch.startswith("pipeline/")); self.assertNotIn(it.id, it.branch)

    def test_assign_one_rule_and_fairness(self):
        ready = readyset.ready_items(self.v.dir, CFG)
        chosen = readyset.assign(ready, [], 4, CFG)
        keys = {(c.space, c.repo, c.primary_tag) for c in chosen}
        self.assertEqual(len(keys), len(chosen), "one lane per (space, repo, tag)")
        self.assertLessEqual(len(chosen), 2, "fairness: aaa may hold at most half of N=4")
        # a running SPA lane blocks further SPA items
        running = [{"space": "aaa", "repo": "org/app", "primary_tag": "SPA", "status": "running"}]
        chosen2 = readyset.assign(ready, running, 3, CFG)
        self.assertTrue(all(c.primary_tag != "SPA" for c in chosen2))
        self.assertEqual(readyset.assign(ready, [], 0, CFG), [])
        self.assertEqual(readyset.assign(ready, [], 3, CFG, paused_spaces=["aaa"]), [])


class ControllerTests(unittest.TestCase):
    def test_aimd(self):
        d = controller.regulate(4, burn=10.0, target=5.0, rate_status="allowed", lanes_saturated=True, N_min=1, N_max=6)
        self.assertEqual(d.N_new, 2); self.assertFalse(d.freeze)
        d = controller.regulate(2, burn=1.0, target=5.0, rate_status="allowed", lanes_saturated=True, N_min=1, N_max=6)
        self.assertEqual(d.N_new, 3)
        d = controller.regulate(2, burn=1.0, target=5.0, rate_status="allowed", lanes_saturated=False, N_min=1, N_max=6)
        self.assertEqual(d.N_new, 2, "no increase when lanes are not saturated")
        d = controller.regulate(3, burn=5.2, target=5.0, rate_status="allowed", lanes_saturated=True, N_min=1, N_max=6)
        self.assertEqual(d.N_new, 3, "inside the deadband: hold")
        d = controller.regulate(3, burn=0.0, target=5.0, rate_status="rejected", lanes_saturated=True, N_min=1, N_max=6)
        self.assertEqual(d.N_new, 1); self.assertTrue(d.freeze)
        d = controller.regulate(5, burn=0.0, target=5.0, rate_status="allowed_warning", lanes_saturated=True, N_min=1, N_max=6, warn_cap=3)
        self.assertEqual(d.N_new, 3); self.assertFalse(d.freeze, "a warning caps, it does not freeze")
        d = controller.regulate(3, burn=0.0, target=5.0, rate_status="allowed_warning", lanes_saturated=True, N_min=1, N_max=6, warn_cap=3)
        self.assertEqual(d.N_new, 3, "under the warn cap the +1 rule is bounded by the cap")
        d = controller.regulate(1, burn=99.0, target=5.0, rate_status="allowed", lanes_saturated=True, N_min=1, N_max=6)
        self.assertEqual(d.N_new, 1, "never below N_min")
        d = controller.regulate(2, burn=99.0, target=5.0, rate_status="allowed", lanes_saturated=True, N_min=1, N_max=6, active_lanes=4)
        self.assertEqual(d.N_new, 2, "refractory: no second halving while lanes still drain above the cap")
        d = controller.regulate(2, burn=99.0, target=5.0, rate_status="allowed", lanes_saturated=True, N_min=1, N_max=6, active_lanes=2)
        self.assertEqual(d.N_new, 1, "decrease resumes once the plant has caught up")

    def test_setpoint_and_caps(self):
        self.assertAlmostEqual(controller.setpoint(40.0, 5.0, 0.15), 6.8)
        self.assertTrue(controller.over_cap(13.0, 12.0)); self.assertFalse(controller.over_cap(1.0, 0.0))
        self.assertTrue(controller.budget_exhausted(40.0, 40.0)); self.assertFalse(controller.budget_exhausted(1.0, 0.0))


class SpeculationTests(unittest.TestCase):
    def test_rule(self):
        go, _ = speculate.should_speculate(0.5, 5.0, 5.0, latency_days=0.5, value_per_day=20.0)
        self.assertTrue(go, "wasted 5 < value 10")
        go, why = speculate.should_speculate(0.5, 30.0, 30.0, 0.5, 20.0)
        self.assertFalse(go)
        go, why = speculate.should_speculate(0.95, 1.0, 1.0, 0.5, 100.0)
        self.assertFalse(go); self.assertIn("extreme", why)

    def test_plan_respects_share(self):
        decisions = [{"id": "D1", "pi": 0.5, "value_per_day": 40.0,
                      "branches": [{"key": "A", "cost": 3, "repo": "r", "outcome_branch": "spec/a", "prompt": "a"},
                                   {"key": "B", "cost": 3, "repo": "r", "outcome_branch": "spec/b", "prompt": "b"}]}]
        plans = speculate.plan_speculation(decisions, [], N=6, free_tokens=4, share=0.34)
        self.assertTrue(plans[0].go)
        plans = speculate.plan_speculation(decisions, [], N=3, free_tokens=3, share=0.34)
        self.assertFalse(plans[0].go, "share of N=3 is one token: both branches do not fit")
        running = [{"kind": "spec", "decision": "D1", "status": "running"}]
        self.assertEqual(speculate.plan_speculation(decisions, running, 6, 4), [])


class LedgerTests(unittest.TestCase):
    def test_roundtrip_and_usage(self):
        d = tempfile.mkdtemp()
        try:
            led = Ledger(d)
            with led.locked():
                led.save_state({"N": 2}); led.save_lanes([{"lane_id": "L1", "usage": [{"cost_usd": 1.0, "tokens": 10}, {"cost_usd": 3.5, "tokens": 40}]}])
                led.event("x", a=1); led.run({"phase": "plan"})
            self.assertEqual(led.state()["N"], 2)
            self.assertEqual(usage_delta(led.lanes()[0]), (2.5, 30.0))
            self.assertEqual(len(led.events()), 1); self.assertEqual(len(led.runs()), 1)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TickEndToEnd(unittest.TestCase):
    def test_plan_record_report(self):
        v = FakeVault(); state = tempfile.mkdtemp(); cfgdir = tempfile.mkdtemp()
        try:
            model = os.path.join(os.path.dirname(os.path.dirname(HERE)), "systems", "swarm-pipeline-model.py")
            cfg = dict(CFG, vault=v.dir, model_path=model, backlog_cli=None, vault_autocommit=False,
                       lane_prompt="Work on {id}: {title} in {repo} on {branch}\n{item_body}",
                       regulator={"N0": 3, "N_min": 1, "N_max": 4, "budget": 20, "window_hours": 5, "lane_cap": 12},
                       speculation={"share": 0.34, "decisions": [{"id": "D1", "pi": 0.5, "value_per_day": 50, "branches": [
                           {"key": "A", "cost": 2, "repo": "org/x", "outcome_branch": "spec/d1-a", "prompt": "A"},
                           {"key": "B", "cost": 2, "repo": "org/x", "outcome_branch": "spec/d1-b", "prompt": "B"}]}]})
            cfg_path = os.path.join(cfgdir, "config.yaml")
            import yaml
            write(cfg_path, yaml.safe_dump(cfg))
            plan_path = os.path.join(state, "plan.json")
            self.assertEqual(tick.main(["--config", cfg_path, "--state", state, "plan", "--out", plan_path]), 0)
            plan = json.load(open(plan_path))
            self.assertEqual(plan["tick"], 1); self.assertEqual(plan["N"], 3)
            self.assertGreaterEqual(len(plan["spawn"]), 1)
            self.assertIn("body of", plan["spawn"][0]["prompt"])
            self.assertEqual(len(plan["spec_spawn"]), 0, "N=3 leaves one speculative token: both branches do not fit")
            # a second plan before record must not double-assign
            plan2_path = os.path.join(state, "plan2.json")
            tick.main(["--config", cfg_path, "--state", state, "plan", "--out", plan2_path])
            plan2 = json.load(open(plan2_path))
            self.assertEqual(set(s["item"] for s in plan2["spawn"]) & set(s["item"] for s in plan["spawn"]), set())
            results = {"spawned": [{"lane_id": s["lane_id"], "ok": True, "session_id": "sess_" + s["lane_id"]} for s in plan["spawn"] + plan2["spawn"]],
                       "checks": []}
            rp = os.path.join(state, "r1.json"); write(rp, json.dumps(results))
            self.assertEqual(tick.main(["--config", cfg_path, "--state", state, "record", "--results", rp]), 0)
            lanes = Ledger(state).lanes()
            self.assertTrue(all(l["status"] == "running" for l in lanes))
            # usage check: over budget → next plan halves N and freezes when budget exhausted
            checks = [{"lane_id": l["lane_id"], "session_id": l["session_id"], "status": "working",
                       "usage": {"cost_usd": 20.0, "tokens": 1e6}, "rate_status": "allowed"} for l in lanes]
            rp2 = os.path.join(state, "r2.json"); write(rp2, json.dumps({"checks": checks}))
            tick.main(["--config", cfg_path, "--state", state, "record", "--results", rp2])
            plan3_path = os.path.join(state, "plan3.json")
            tick.main(["--config", cfg_path, "--state", state, "plan", "--out", plan3_path])
            plan3 = json.load(open(plan3_path))
            self.assertTrue(plan3["freeze"]); self.assertLess(plan3["N"], 3)
            self.assertEqual(plan3["spawn"], [])
            self.assertTrue(plan3["interrupt"], "lanes over the per-lane cap are listed for interruption")
            # ended with PR → in_review
            l0 = lanes[0]
            rp3 = os.path.join(state, "r3.json")
            write(rp3, json.dumps({"checks": [{"lane_id": l0["lane_id"], "status": "idle", "usage": {"cost_usd": 21.0}, "pr": {"url": "u", "number": 1}}]}))
            tick.main(["--config", cfg_path, "--state", state, "record", "--results", rp3])
            self.assertEqual(Ledger(state).lanes()[0]["status"], "in_review")
            out = os.path.join(state, "report.md")
            tick.main(["--config", cfg_path, "--state", state, "report", "--out", out])
            text = open(out).read()
            self.assertIn("## Regulator trace", text); self.assertIn("in_review", text)
        finally:
            v.cleanup(); shutil.rmtree(state, ignore_errors=True); shutil.rmtree(cfgdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
