"""Must-fail tests for the admission gate, one per rule, on small fixture vaults.

Run: python3 -m unittest discover -s pipeline/tests
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from metaos_pipeline import admission, readyset  # noqa: E402
from test_pipeline import CFG, FakeVault, graph_index, write  # noqa: E402
import tick  # noqa: E402

TIER = {"TO DO": "raw", "REFINED": "raw", "IN PROGRESS": "wiki", "IN REVIEW": "wiki", "DONE": "output", "NO GO": "output"}


def put(vault: str, id_: str, status: str, deps=(), kind="story", labels=(), epic="", title="", points=3, priority="P2"):
    space = id_.split("-")[0].lower()
    write(os.path.join(vault, space, TIER[status], f"{id_}.md"), f"""---
kind: {kind}
id: {id_}
title: '{title or "[SPA] " + id_.lower()}'
status: {status}
space: {space}
storyPoints: {points}
priority: {priority}
epic: {epic or "null"}
labels: [{", ".join(labels)}]
dependencies: [{", ".join(deps)}]
---
body
""")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def sprint(vault: str, space: str, committed=()) -> None:
    write(os.path.join(vault, space, "sprints", f"{space.upper()}-S1.md"),
          f"---\nkind: sprint\nspace: {space}\nsprintId: {space.upper()}-S1\nstate: active\n"
          f"committed: [{', '.join(committed)}]\n---\n")


class GateRules(unittest.TestCase):
    """Each rule excludes an item that would otherwise be admitted, with its reason verbatim."""

    def setUp(self):
        self.vault = tempfile.mkdtemp(prefix="vault-")
        v = self.vault
        sprint(v, "spacea")
        put(v, "SPACEA-1", "REFINED")
        put(v, "SPACEA-12", "TO DO"); put(v, "SPACEA-2", "REFINED", deps=["SPACEA-12"])
        put(v, "SPACEA-13", "IN REVIEW"); put(v, "SPACEA-3", "REFINED", deps=["SPACEA-13"])
        put(v, "SPACEA-14", "NO GO"); put(v, "SPACEA-4", "REFINED", deps=["SPACEA-14"])
        put(v, "SPACEA-15", "TO DO", deps=["SPACEA-14"]); put(v, "SPACEA-5", "REFINED", deps=["SPACEA-15"])
        put(v, "SPACEA-20", "IN PROGRESS", kind="epic"); put(v, "SPACEA-6", "REFINED", deps=["SPACEA-20"])
        put(v, "SPACEA-7", "REFINED"); put(v, "SPACEA-8", "REFINED")
        put(v, "SPACEA-21", "TO DO", kind="epic", labels=["parked"])
        put(v, "SPACEA-22", "TO DO", kind="epic", epic="SPACEA-21")
        put(v, "SPACEA-9", "REFINED", epic="SPACEA-22")
        put(v, "SPACEA-16", "IN PROGRESS")
        sprint(v, "spacec"); put(v, "SPACEC-1", "REFINED")
        graph_index(v)
        self.cfg = {**CFG, "spaces": {**CFG["spaces"], "spacec": {"repo": "org/c", "executable": False}}}

    def tearDown(self):
        shutil.rmtree(self.vault, ignore_errors=True)

    def admit(self, lanes=(), **kw):
        return admission.admit(self.vault, self.cfg, list(lanes), **kw)

    def test_clean_item_is_admitted(self):
        self.assertEqual([i.id for i in self.admit().admitted], ["SPACEA-1", "SPACEA-7", "SPACEA-8"])

    def test_blocker_to_do(self):
        self.assertEqual(self.admit().excluded["SPACEA-2"], "blocked by SPACEA-12 (TO DO)")

    def test_blocker_in_review(self):
        self.assertEqual(self.admit().excluded["SPACEA-3"], "in pipeline behind SPACEA-13 (IN REVIEW)")

    def test_blocker_no_go_and_the_item_behind_it(self):
        ex = self.admit().excluded
        self.assertEqual(ex["SPACEA-4"], "blocked by SPACEA-14 (NO GO): its premise is gone")
        self.assertEqual(ex["SPACEA-5"], "behind SPACEA-15, blocked by SPACEA-14 (NO GO): its premise is gone")

    def test_blocker_on_an_unfinished_epic(self):
        self.assertEqual(self.admit().excluded["SPACEA-6"], "blocked by epic SPACEA-20 (IN PROGRESS), which is not finished")

    def test_item_held_by_a_paused_lane(self):
        lanes = [{"lane_id": "L1-a", "item": "SPACEA-7", "status": "paused"},
                 {"lane_id": "lane-2", "actual": "paused", "run": {"item": "SPACEA-8"}}]
        ex = self.admit(lanes).excluded
        self.assertEqual(ex["SPACEA-7"], "held by lane L1-a (paused)")
        self.assertEqual(ex["SPACEA-8"], "held by lane lane-2 (paused)", "a slot record holds its run's item too")

    def test_parked_epic_two_levels_up(self):
        self.assertEqual(self.admit().excluded["SPACEA-9"], "epic SPACEA-21 is parked")

    def test_non_executable_space(self):
        self.assertEqual(self.admit().excluded["SPACEC-1"], "not executable")

    def test_stale_index_refuses(self):
        put(self.vault, "SPACEA-1", "REFINED", deps=["SPACEA-12"])  # a dependency the index does not carry
        with self.assertRaises(admission.Refused) as cm:
            self.admit()
        self.assertIn("missing SPACEA-1 -> SPACEA-12", str(cm.exception))

    def test_missing_index_refuses(self):
        os.remove(os.path.join(self.vault, "_graphindex.md"))
        self.assertRaises(admission.Refused, self.admit)

    def test_retry_cap_holds(self):
        self.assertEqual(self.admit(retries={"SPACEA-1": 2}).excluded["SPACEA-1"], "held after 2 retries (cap 2)")

    def test_orphan_is_reported_not_admitted(self):
        adm = self.admit()
        self.assertEqual(adm.orphans, ["SPACEA-16"])
        lanes = [{"lane_id": "L1-b", "item": "SPACEA-16", "status": "running"}]
        self.assertEqual(self.admit(lanes).orphans, [])

    def test_planner_orders_but_never_widens(self):
        adm = self.admit(planner_order=["SPACEA-8", "SPACEA-2", "SPACEA-1", "SPACEA-7"])
        self.assertEqual([i.id for i in adm.admitted], ["SPACEA-8", "SPACEA-1", "SPACEA-7"])
        self.assertEqual(adm.planner_ignored, {"SPACEA-2": "listed by the planner, not admitted: blocked by SPACEA-12 (TO DO)"})


class DefaultOrder(unittest.TestCase):
    def test_without_a_planner_the_order_is_unchanged(self):
        v = FakeVault()
        try:
            self.assertEqual([i.id for i in admission.admit(v.dir, CFG, []).admitted],
                             [i.id for i in readyset.ready_items(v.dir, CFG)])
        finally:
            v.cleanup()


# The prototype window's ready set, in its order, rebuilt with synthetic ids: thirteen items in
# two spaces, three of them behind blockers that were DONE (one behind two). The window's own
# ledger and vault history show no blocker that was not DONE, so the two that have one here are
# synthetic, added to prove the gate admits the hand-driven set minus exactly those two.
WINDOW_RUN = ["SPACEX-1", "SPACEX-2", "SPACEX-3", "SPACEX-4", "SPACEX-5", "SPACEY-1", "SPACEY-2",
              "SPACEY-3", "SPACEX-6", "SPACEY-4", "SPACEY-5", "SPACEY-6", "SPACEY-7"]
WINDOW_BLOCKED = {"SPACEX-7": "blocked by SPACEX-90 (TO DO)", "SPACEY-8": "in pipeline behind SPACEY-90 (IN REVIEW)"}


class Window(unittest.TestCase):
    def test_window_ready_set(self):
        v = tempfile.mkdtemp(prefix="vault-")
        try:
            sprint(v, "spacex"); sprint(v, "spacey")
            for k in ("SPACEX-80", "SPACEX-81", "SPACEX-82", "SPACEX-83"):
                put(v, k, "DONE")
            put(v, "SPACEX-90", "TO DO"); put(v, "SPACEY-90", "IN REVIEW")
            deps = {"SPACEX-1": ["SPACEX-80"], "SPACEX-2": ["SPACEX-81", "SPACEX-82"], "SPACEX-5": ["SPACEX-83"],
                    "SPACEX-7": ["SPACEX-90"], "SPACEY-8": ["SPACEY-90"]}
            for n, k in enumerate(WINDOW_RUN + list(WINDOW_BLOCKED)):
                put(v, k, "REFINED", deps=deps.get(k, ()), points=n + 1, title=f"[T{n}] item {n}")
            graph_index(v)
            cfg = {"spaces": {"spacex": {"repo": "org/x"}, "spacey": {"repo": "org/y"}}, "ready_statuses": ["REFINED"]}
            adm = admission.admit(v, cfg, [])
            self.assertEqual([i.id for i in adm.admitted], WINDOW_RUN)
            self.assertEqual(adm.excluded, WINDOW_BLOCKED)
        finally:
            shutil.rmtree(v, ignore_errors=True)


class TickPlan(unittest.TestCase):
    """The reasons reach plan.json, the run line and the end-of-run report verbatim."""

    def run_plan(self, mutate=None):
        v = FakeVault(); state = tempfile.mkdtemp(); cfgdir = tempfile.mkdtemp()
        self.addCleanup(v.cleanup); self.addCleanup(shutil.rmtree, state, True); self.addCleanup(shutil.rmtree, cfgdir, True)
        if mutate:
            mutate(v.dir)
        model = os.path.join(os.path.dirname(os.path.dirname(HERE)), "systems", "pipeline", "queueing-model.py")
        cfg = dict(CFG, vault=v.dir, model_path=model, backlog_cli=None, vault_autocommit=False, lane_prompt="{id}",
                   regulator={"N0": 3, "N_min": 1, "N_max": 4, "budget": 20, "window_hours": 5, "lane_cap": 12})
        cfg_path = os.path.join(cfgdir, "config.yaml")
        import yaml
        write(cfg_path, yaml.safe_dump(cfg))
        plan_path = os.path.join(state, "plan.json")
        rc = tick.main(["--config", cfg_path, "--state", state, "plan", "--out", plan_path])
        report = os.path.join(state, "report.md")
        tick.main(["--config", cfg_path, "--state", state, "report", "--out", report])
        run = json.loads(read(os.path.join(state, "runs.ndjson")).splitlines()[-1])
        return rc, json.loads(read(plan_path)), run, read(report), state

    def test_reasons_are_verbatim_everywhere(self):
        rc, plan, run, report, _ = self.run_plan()
        self.assertEqual(rc, 0)
        why = "blocked by SPACEA-5 (TO DO)"
        self.assertEqual(plan["excluded"]["SPACEA-3"], why)
        self.assertEqual(run["excluded"]["SPACEA-3"], why)
        self.assertIn(f"- SPACEA-3: {why}", report)
        self.assertEqual(plan["admitted"], plan["ready_set"])

    def test_stale_index_refuses_the_plan(self):
        def stale(vault):
            with open(os.path.join(vault, "_graphindex.md"), "a", encoding="utf-8") as fh:
                fh.write("[[SPACEA-1]] -> [[SPACEA-9]]\n")
        rc, plan, run, report, state = self.run_plan(stale)
        self.assertEqual(rc, 2)
        self.assertIn("extra SPACEA-1 -> SPACEA-9", plan["refused"])
        self.assertEqual(run["refused"], plan["refused"])
        self.assertIn("the plan refused: " + plan["refused"], report)
        self.assertNotIn("spawn", plan)
        self.assertFalse(os.path.exists(os.path.join(state, "lanes.json")), "a refused plan writes no lanes")


if __name__ == "__main__":
    unittest.main()
