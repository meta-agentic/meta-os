"""The review station's disciplines: the queue oldest first, the review-age SLA, the auto-merge tier.

The auto-merge tier is the one place the pipeline merges by itself, so its refusal paths come
first and each one is a must-fail test: off by default, outside the classes, any red or pending
check, no checks at all, a human-judgement flag, a draft, an unknown class, a moved head.

Run: python3 -m unittest discover -s pipeline/tests
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from metaos_pipeline import review  # noqa: E402
from metaos_pipeline.ledger import Ledger  # noqa: E402
from test_admission import put, read  # noqa: E402
from test_pipeline import CFG, FakeVault, write  # noqa: E402
import tick  # noqa: E402

DAY = 86400.0
NOW = 1_800_000_000.0
GREEN = [{"name": "build", "status": "COMPLETED", "conclusion": "SUCCESS"},
         {"context": "lint", "state": "SUCCESS"}]


def pr(files=("docs/guide.md",), checks=GREEN, labels=(), draft=False, state="OPEN", mergeable="MERGEABLE", sha="abc123"):
    return {"state": state, "isDraft": draft, "mergeable": mergeable, "headRefOid": sha,
            "labels": [{"name": n} for n in labels], "files": [{"path": p} for p in files],
            "statusCheckRollup": list(checks)}


class Refusals(unittest.TestCase):
    """Every path that must not merge, then the two that may."""

    def refused(self, doc, classes=("docs-only", "tests-only"), item_labels=()):
        d = review.decide(doc, list(classes), item_labels)
        self.assertFalse(d.merge, d.reason)
        return d.reason

    def test_empty_class_list_is_off(self):
        self.assertIn("off", self.refused(pr(), classes=()))

    def test_malformed_class_list_is_off(self):
        self.assertFalse(review.decide(pr(), "docs-only").merge)
        self.assertFalse(review.decide(pr(), None).merge)
        self.assertFalse(review.decide(pr(), [1]).merge)

    def test_outside_the_classes(self):
        self.assertIn("outside", self.refused(pr(files=("docs/guide.md", "src/app.py"))))
        self.assertIn("outside", self.refused(pr(files=("tests/test_x.py",)), classes=("docs-only",)))

    def test_agent_instructions_are_not_documentation(self):
        for path in ("CLAUDE.md", "skills/x/SKILL.md", ".github/README.md", ".claude/notes.md"):
            self.assertIn("outside", self.refused(pr(files=(path,))), path)

    def test_unknown_class_never_matches(self):
        self.assertIn("outside", self.refused(pr(), classes=("dependency-bumps",)))

    def test_a_red_check(self):
        red = GREEN + [{"name": "test", "status": "COMPLETED", "conclusion": "FAILURE"}]
        self.assertIn("test", self.refused(pr(checks=red)))

    def test_a_pending_check(self):
        pending = GREEN + [{"name": "test", "status": "IN_PROGRESS", "conclusion": ""}]
        self.assertIn("test", self.refused(pr(checks=pending)))

    def test_a_skipped_or_neutral_check_is_not_green(self):
        self.refused(pr(checks=GREEN + [{"name": "e2e", "status": "COMPLETED", "conclusion": "SKIPPED"}]))
        self.refused(pr(checks=GREEN + [{"name": "e2e", "status": "COMPLETED", "conclusion": "NEUTRAL"}]))

    def test_no_checks_proves_nothing(self):
        self.assertIn("no checks", self.refused(pr(checks=())))

    def test_human_judgement_on_the_pr_or_the_item(self):
        self.assertIn(review.HUMAN_FLAG, self.refused(pr(labels=(review.HUMAN_FLAG,))))
        self.assertIn(review.HUMAN_FLAG, self.refused(pr(), item_labels=[review.HUMAN_FLAG]))

    def test_draft_closed_or_unmergeable(self):
        self.refused(pr(draft=True))
        self.refused(pr(state="MERGED"))
        self.refused(pr(mergeable="CONFLICTING"))
        self.refused(pr(mergeable="UNKNOWN"))

    def test_no_files(self):
        self.refused(pr(files=()))

    def test_documentation_only_all_green_merges(self):
        d = review.decide(pr(files=("docs/guide.md", "README.md")), ["docs-only"])
        self.assertTrue(d.merge, d.reason)
        self.assertEqual(d.cls, "docs-only")

    def test_tests_only_all_green_merges(self):
        d = review.decide(pr(files=("tests/test_a.py", "pkg/tests/fixtures/x.json", "web/a.test.ts")), ["tests-only"])
        self.assertTrue(d.merge, d.reason)


class FakeGh:
    """The GitHub port, London style: answers `view`, records every `merge`."""

    def __init__(self, doc, merge_ok=True):
        self.doc, self.merge_ok, self.views, self.merges = doc, merge_ok, [], []

    def view(self, repo, number):
        self.views.append((repo, number))
        return self.doc

    def merge(self, repo, number, sha):
        self.merges.append((repo, number, sha))
        if not self.merge_ok:
            raise review.GhError("merge refused by the remote")


class AutomergePass(unittest.TestCase):
    """The tier inside the record pass: it reads only what the record registered, merges, transitions to DONE."""

    def setUp(self):
        self.vault = tempfile.mkdtemp(prefix="vault-")
        self.state = tempfile.mkdtemp(prefix="state-")
        self.addCleanup(shutil.rmtree, self.vault, True)
        self.addCleanup(shutil.rmtree, self.state, True)
        put(self.vault, "SPACEA-13", "IN REVIEW")
        self.led = Ledger(self.state)
        st = self.led.state({})
        st["review"] = {"SPACEA-13": {"repo": "org/app", "number": 7, "url": "https://github.com/org/app/pull/7", "since": NOW}}
        self.led.save_state(st)

    def record(self, gh, classes):
        cfg = dict(CFG, vault=self.vault, backlog_cli=None, vault_autocommit=False,
                   _swarm={"automerge_classes": classes} if classes is not None else {})
        with mock.patch.object(review, "github", return_value=gh):
            return tick.record_pass(cfg, self.led, {}, now=NOW + DAY)

    def test_default_is_off_and_never_asks_github(self):
        gh = FakeGh(pr())
        out = self.record(gh, None)
        self.assertEqual((gh.views, gh.merges, out["transitions"]), ([], [], []))

    def test_outside_the_class_never_merges(self):
        gh = FakeGh(pr(files=("src/app.py",)))
        out = self.record(gh, ["docs-only"])
        self.assertEqual(gh.merges, [])
        self.assertEqual(out["transitions"], [])
        self.assertIn("SPACEA-13", self.led.state()["review"], "the item stays in the PO's queue")
        self.assertTrue(any(e["kind"] == "automerge_refused" for e in self.led.events()))

    def test_in_class_and_green_merges_at_the_head_it_saw_and_goes_done(self):
        gh = FakeGh(pr(sha="feed42"))
        out = self.record(gh, ["docs-only"])
        self.assertEqual(gh.merges, [("org/app", 7, "feed42")])
        self.assertEqual(len(out["transitions"]), 1)
        self.assertIn("SPACEA-13 → DONE", out["transitions"][0])
        self.assertIn("auto-merged", out["transitions"][0])
        self.assertNotIn("SPACEA-13", self.led.state()["review"])
        merged = [e for e in self.led.events() if e["kind"] == "automerged"]
        self.assertEqual([(e["item"], e["cls"]) for e in merged], [("SPACEA-13", "docs-only")])

    def test_a_failed_merge_does_not_transition(self):
        gh = FakeGh(pr(), merge_ok=False)
        out = self.record(gh, ["docs-only"])
        self.assertEqual(out["transitions"], [])
        self.assertIn("SPACEA-13", self.led.state()["review"])

    def test_an_item_no_longer_in_review_is_dropped_unmerged(self):
        os.remove(os.path.join(self.vault, "spacea", "wiki", "SPACEA-13.md"))
        put(self.vault, "SPACEA-13", "IN PROGRESS")
        gh = FakeGh(pr())
        out = self.record(gh, ["docs-only"])
        self.assertEqual((gh.views, gh.merges, out["transitions"]), ([], [], []))
        self.assertNotIn("SPACEA-13", self.led.state()["review"])

    def test_a_pr_merged_by_the_po_leaves_the_queue_without_a_transition(self):
        gh = FakeGh(pr(state="MERGED"))
        out = self.record(gh, ["docs-only"])
        self.assertEqual((gh.merges, out["transitions"]), ([], []))
        self.assertNotIn("SPACEA-13", self.led.state()["review"])

    def test_a_failed_done_transition_is_retried_without_merging_again(self):
        gh, answers = FakeGh(pr()), [(1, "vault busy"), (0, "ok")]
        st, events = self.led.state(), []
        kw = dict(vault_status=lambda k: "IN REVIEW", item_labels=lambda k: [],
                  transition=lambda k, s: answers.pop(0), emit=lambda kind, **f: events.append(kind))
        with mock.patch.object(review, "github", return_value=gh):
            self.assertEqual(review.automerge(st, ["docs-only"], **kw), [])
            self.assertTrue(st["review"]["SPACEA-13"]["merged"])
            done = review.automerge(st, ["docs-only"], **kw)
        self.assertEqual(len(gh.merges), 1, "the merge is never repeated")
        self.assertEqual(len(done), 1)
        self.assertEqual(st["review"], {})

    def test_the_record_pass_registers_the_prs_it_moves_to_review(self):
        v = FakeVault(); cfgdir = tempfile.mkdtemp()
        self.addCleanup(v.cleanup); self.addCleanup(shutil.rmtree, cfgdir, True)
        model = os.path.join(os.path.dirname(os.path.dirname(HERE)), "systems", "pipeline", "queueing-model.py")
        cfg = dict(CFG, vault=v.dir, model_path=model, backlog_cli=None, vault_autocommit=False, lane_prompt="{id}",
                   regulator={"N0": 1, "N_min": 1, "N_max": 4, "budget": 20, "window_hours": 5, "lane_cap": 12})
        import yaml
        cfg_path = os.path.join(cfgdir, "config.yaml"); write(cfg_path, yaml.safe_dump(cfg))
        state = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, state, True)
        tick.main(["--config", cfg_path, "--state", state, "plan", "--out", os.path.join(state, "plan.json")])
        [sp] = json.loads(read(os.path.join(state, "plan.json")))["spawn"]
        for i, res in enumerate([{"spawned": [{"lane_id": sp["lane_id"], "ok": True, "session_id": "s1"}]},
                                 {"checks": [{"lane_id": sp["lane_id"], "status": "idle",
                                              "pr": {"url": "https://github.com/org/app/pull/9", "number": 9}}]}]):
            if i:  # what the backlog CLI does at this transition (none is configured here)
                os.remove(os.path.join(v.dir, "spacea", "raw", sp["item"] + ".md")); put(v.dir, sp["item"], "IN REVIEW")
            rp = os.path.join(state, f"r{i}.json"); write(rp, json.dumps(res))
            tick.main(["--config", cfg_path, "--state", state, "record", "--results", rp])
        entry = Ledger(state).state()["review"][sp["item"]]
        self.assertEqual((entry["repo"], entry["number"]), (sp["repo"], 9))

    def test_record_registers_a_pr_for_the_queue(self):
        state = {"review": {}}
        review.register(state, "SPACEA-2", {"url": "https://github.com/org/app/pull/9", "number": 9}, "org/app", NOW)
        self.assertEqual(state["review"]["SPACEA-2"], {"repo": "org/app", "number": 9, "url": "https://github.com/org/app/pull/9", "since": NOW})
        review.register(state, "SPACEA-3", {"url": "u"}, "org/app", NOW)
        self.assertNotIn("SPACEA-3", state["review"], "a PR without a number cannot be merged by the tier")


def git(cwd, *args, when=None):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    if when:
        env.update(GIT_AUTHOR_DATE=f"@{int(when)} +0000", GIT_COMMITTER_DATE=f"@{int(when)} +0000")
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, env=env)


class Queue(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp(prefix="vault-")
        self.addCleanup(shutil.rmtree, self.vault, True)

    def aged(self, id_, days, status="IN REVIEW"):
        put(self.vault, id_, status)
        tier = "wiki" if status == "IN REVIEW" else "raw"
        path = os.path.join(self.vault, id_.split("-")[0].lower(), tier, f"{id_}.md")
        os.utime(path, (NOW - days * DAY, NOW - days * DAY))

    def test_oldest_first_with_age_in_days(self):
        self.aged("SPACEA-2", 2); self.aged("SPACEA-30", 30.4); self.aged("SPACEB-10", 10)
        self.aged("SPACEA-5", 50, status="REFINED")
        rows = review.queue(self.vault, ["spacea", "spaceb"], NOW)
        self.assertEqual([(r.id, r.days) for r in rows], [("SPACEA-30", 30), ("SPACEB-10", 10), ("SPACEA-2", 2)])
        self.assertEqual({r.source for r in rows}, {"mtime"})

    def test_age_is_the_commit_that_set_in_review(self):
        git(self.vault, "init", "-q")
        put(self.vault, "SPACEA-1", "IN PROGRESS")
        git(self.vault, "add", "-A"); git(self.vault, "commit", "-qm", "start", when=NOW - 20 * DAY)
        os.remove(os.path.join(self.vault, "spacea", "wiki", "SPACEA-1.md"))
        put(self.vault, "SPACEA-1", "IN REVIEW")
        git(self.vault, "add", "-A"); git(self.vault, "commit", "-qm", "review", when=NOW - 8 * DAY)
        path = os.path.join(self.vault, "spacea", "wiki", "SPACEA-1.md")
        write(path, read(path) + "\nmore notes\n")
        git(self.vault, "commit", "-qam", "edit", when=NOW - 1 * DAY)
        [row] = review.queue(self.vault, ["spacea"], NOW)
        self.assertEqual((row.days, row.source), (8, "git"))

    def test_gauge_and_sla(self):
        self.aged("SPACEA-30", 6); self.aged("SPACEB-1", 4)
        rows = review.queue(self.vault, ["spacea", "spaceb", "spacec"], NOW)
        self.assertEqual(review.age_max_days(rows, ["spacea", "spaceb", "spacec"]), {"spacea": 6, "spaceb": 4, "spacec": 0})
        paused = review.over_sla(rows, 5)
        self.assertEqual(list(paused), ["spacea"])
        self.assertIn("SPACEA-30", paused["spacea"])
        self.assertEqual(review.over_sla(rows, 6), {}, "at the limit is not over it")


class SlaInThePlan(unittest.TestCase):
    """A space over the SLA takes no new work, and plan.json, the run line and the report say why."""

    def plan(self, review_days, sla=None):
        v = FakeVault(); state = tempfile.mkdtemp(); cfgdir = tempfile.mkdtemp()
        self.addCleanup(v.cleanup); self.addCleanup(shutil.rmtree, state, True); self.addCleanup(shutil.rmtree, cfgdir, True)
        put(v.dir, "SPACEA-40", "IN REVIEW")
        p = os.path.join(v.dir, "spacea", "wiki", "SPACEA-40.md")
        os.utime(p, (time.time() - review_days * DAY,) * 2)
        model = os.path.join(os.path.dirname(os.path.dirname(HERE)), "systems", "pipeline", "queueing-model.py")
        cfg = dict(CFG, vault=v.dir, model_path=model, backlog_cli=None, vault_autocommit=False, lane_prompt="{id}",
                   regulator={"N0": 3, "N_min": 1, "N_max": 4, "budget": 20, "window_hours": 5, "lane_cap": 12})
        import yaml
        write(os.path.join(cfgdir, "config.yaml"), yaml.safe_dump(cfg))
        if sla is not None:
            write(os.path.join(cfgdir, "meta-os.config.json"), json.dumps({"swarm": {"review_sla_days": sla}}))
        out = os.path.join(state, "plan.json")
        self.assertEqual(tick.main(["--config", os.path.join(cfgdir, "config.yaml"), "--state", state, "plan", "--out", out]), 0)
        report = os.path.join(state, "report.md")
        tick.main(["--config", os.path.join(cfgdir, "config.yaml"), "--state", state, "report", "--out", report])
        run = json.loads(read(os.path.join(state, "runs.ndjson")).splitlines()[-1])
        return json.loads(read(out)), run, read(report)

    def test_over_the_default_sla_the_space_is_skipped(self):
        plan, run, report = self.plan(6)
        self.assertEqual(plan["spawn"], [], "spacea is the only executable space with ready items")
        self.assertIn("spacea", plan["paused_spaces"])
        why = plan["paused_reasons"]["spacea"]
        self.assertIn("SPACEA-40", why); self.assertIn("6 d", why); self.assertIn("5 d", why)
        self.assertEqual(run["paused_reasons"]["spacea"], why)
        self.assertEqual(plan["review_age_max_days"]["spacea"], 6)
        self.assertIn("## Review queue (oldest first)", report)
        self.assertIn("| SPACEA-40 | spacea | 6 |", report)

    def test_under_the_sla_the_space_works(self):
        plan, _, _ = self.plan(4)
        self.assertNotIn("spacea", plan["paused_spaces"])
        self.assertTrue(plan["spawn"])

    def test_the_instance_sets_the_limit(self):
        plan, _, _ = self.plan(4, sla=3)
        self.assertIn("spacea", plan["paused_spaces"])

    def test_a_malformed_limit_stops_the_run(self):
        with self.assertRaises(SystemExit):
            self.plan(1, sla="five")


class WeeklyShare(unittest.TestCase):
    def test_q_per_week_is_the_auto_merged_share_of_the_prs_that_entered_review(self):
        mon = 1_799_625_600.0  # Monday 2027-01-11, 00:00 UTC
        events = [
            {"kind": "transition", "to": "IN REVIEW", "item": "A-1", "pr": "u1", "ts": mon + 1, "rc": 0},
            {"kind": "transition", "to": "IN REVIEW", "item": "A-2", "pr": "u2", "ts": mon + 2, "rc": 0},
            {"kind": "transition", "to": "IN REVIEW", "item": "A-3", "pr": "u3", "ts": mon + 7 * DAY, "rc": 0},
            {"kind": "transition", "to": "IN REVIEW", "item": "A-4", "pr": "u4", "ts": mon + 3, "rc": 1},
            {"kind": "automerged", "item": "A-1", "pr": "u1", "ts": mon + 8 * DAY},
        ]
        weeks = review.weekly_q(events)
        self.assertEqual([(w, n, a) for w, n, a, _ in weeks], [("2027-W02", 2, 1), ("2027-W03", 1, 0)])
        self.assertEqual(weeks[0][3], 0.5)


if __name__ == "__main__":
    unittest.main()
