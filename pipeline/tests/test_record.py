"""The record repository: git-backed ledger, schema versions, the read contract. Local bare repositories only."""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from metaos_pipeline import ledger as record  # noqa: E402
from metaos_pipeline.ledger import Ledger  # noqa: E402
import tick  # noqa: E402
from test_pipeline import CFG, FakeVault, write  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "pipeline-test", "GIT_AUTHOR_EMAIL": "pipeline@example.invalid",
           "GIT_COMMITTER_NAME": "pipeline-test", "GIT_COMMITTER_EMAIL": "pipeline@example.invalid",
           "GIT_CONFIG_NOSYSTEM": "1"}
_saved: dict = {}


def setUpModule():
    fd, empty = tempfile.mkstemp(prefix="gitconfig-")
    os.close(fd)
    for k, v in dict(GIT_ENV, GIT_CONFIG_GLOBAL=empty).items():
        _saved[k] = os.environ.get(k)
        os.environ[k] = v


def tearDownModule():
    os.unlink(os.environ["GIT_CONFIG_GLOBAL"])
    for k, v in _saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def load(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def git(path: str, *args: str) -> str:
    return subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, check=True).stdout.strip()


class RecordRepo:
    """A bare remote with one seed commit, in a temp dir; clones are made beside it."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="record-")
        self.url = os.path.join(self.root, "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.url], check=True)
        seed = os.path.join(self.root, "seed")
        subprocess.run(["git", "clone", "-q", self.url, seed], check=True, capture_output=True)
        write(os.path.join(seed, "README.md"), "record\n")
        git(seed, "add", "-A"); git(seed, "commit", "-q", "-m", "seed"); git(seed, "push", "-q", "origin", "HEAD:main")

    def clone(self, name: str) -> str:
        return os.path.join(self.root, name)

    def log(self) -> list[str]:
        return git(self.url, "log", "--format=%s", "main").splitlines()

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class GitLedgerTests(unittest.TestCase):
    def setUp(self):
        self.repo = RecordRepo()

    def tearDown(self):
        self.repo.cleanup()

    def test_one_commit_per_phase_and_a_no_op_when_nothing_changed(self):
        led = Ledger(self.repo.clone("a"), remote=self.repo.url)
        with led.locked("plan"):
            led.save_state({"tick": 1}); led.save_lanes([{"lane_id": "L1-x", "status": "spawning"}])
        self.assertEqual(self.repo.log()[0], "pass 1 plan: lanes changed: L1-x")
        with led.locked("plan"):
            led.save_state({"tick": 1})  # same bytes: nothing changed
        self.assertEqual(len(self.repo.log()), 2, "an unchanged phase leaves no commit")
        self.assertIsNone(_in_phase(led, lambda: led.commit_pass("nothing")))

    def test_push_race_replays_the_phase_from_the_new_state(self):
        a = Ledger(self.repo.clone("a"), remote=self.repo.url)
        b = Ledger(self.repo.clone("b"), remote=self.repo.url)
        attempts = []

        def phase_b():
            with b.locked("record"):
                attempts.append(len(b.events()))
                if len(attempts) == 1:  # the other writer pushes after b fetched
                    with a.locked("plan"):
                        a.save_state({"tick": 7}); a.event("from_a")
                b.save_state({**b.state(), "tick": 7}); b.event("from_b")
        b.replay(phase_b)
        self.assertEqual(attempts, [0, 1], "the replay starts from the state the other writer pushed")
        self.assertEqual(self.repo.log()[:2], ["pass 7 record: lanes changed: none", "pass 7 plan: lanes changed: none"])
        self.assertEqual([e["kind"] for e in b.events()], ["from_a", "from_b"])
        self.assertEqual(git(b.dir, "rev-parse", "HEAD"), git(self.repo.url, "rev-parse", "main"))

    def test_a_stale_clone_is_refused_before_anything_is_written(self):
        a = Ledger(self.repo.clone("a"), remote=self.repo.url)
        b = Ledger(self.repo.clone("b"), remote=self.repo.url)
        write(os.path.join(b.dir, "local.txt"), "x"); git(b.dir, "add", "-A"); git(b.dir, "commit", "-q", "-m", "local")
        with a.locked("plan"):
            a.event("moved")
        ran = []
        with self.assertRaisesRegex(record.StaleClone, "holds 1 commit.*holds 1 not here.*a human resolves it"):
            with b.locked("plan"):
                ran.append(1)
        self.assertEqual(ran, [])
        with self.assertRaisesRegex(record.StaleClone, "outside a fetched phase"):
            a.event("unlocked")
        git(a.dir, "remote", "set-url", "origin", os.path.join(self.repo.root, "gone.git"))
        with self.assertRaisesRegex(record.StaleClone, "fetch failed"):
            with a.locked("plan"):
                ran.append(2)
        self.assertEqual(ran, [])

    def test_a_failed_push_is_pushed_by_the_next_phase(self):
        a = Ledger(self.repo.clone("a"), remote=self.repo.url)
        moved = os.path.join(self.repo.root, "away.git")
        with self.assertRaisesRegex(record.LedgerError, "record push failed"):
            with a.locked("plan"):
                a.save_state({"tick": 4})
                os.rename(self.repo.url, moved)  # the remote is unreachable when the phase pushes
        os.rename(moved, self.repo.url)
        with a.locked("plan"):  # no StaleClone: the pending pass is pushed first, then the phase runs
            a.save_state({"tick": 5})
        self.assertEqual(self.repo.log()[:2], ["pass 5 plan: lanes changed: none", "pass 4 plan: lanes changed: none"])

    def test_unknown_schema_stops_with_its_reason(self):
        d = tempfile.mkdtemp()
        try:
            write(os.path.join(d, record.STATE_FILE), json.dumps({"schema": 99, "tick": 1}))
            with self.assertRaisesRegex(record.SchemaError, "state.json: schema 99"):
                Ledger(d).state()
            write(os.path.join(d, record.STATE_FILE), json.dumps({"tick": 1}))
            self.assertEqual(Ledger(d).state()["tick"], 1, "a file without schema is the prototype's, version 1")
        finally:
            shutil.rmtree(d, ignore_errors=True)


def _in_phase(led: Ledger, fn):
    with led.locked():
        return fn()


class ReadContractTests(unittest.TestCase):
    def test_every_file_the_contract_names_round_trips(self):
        with open(os.path.join(os.path.dirname(HERE), "record.md"), encoding="utf-8") as fh:
            doc = fh.read()
        named = re.findall(r"^\| `([^`]+)` \|", doc, re.M)
        self.assertEqual(sorted(named), sorted(record.RECORD_FILES))
        d = tempfile.mkdtemp()
        try:
            led = Ledger(d)
            with led.locked():
                led.save_state({"tick": 3, "N": 2}); led.save_lanes([{"lane_id": "L3-a", "kind": "work"}])
                led.event("lane_started", lane_id="L3-a"); led.run({"phase": "plan", "tick": 3})
                led.reflection({"tick": 3}); led.write_pass_file("plan", 3, 0.0, {"tick": 3, "spawn": []})
                led.write_pass_file("results", 3, 0.0, {"spawned": []})
            reads = {record.STATE_FILE: led.state(), record.LANES_FILE: led.lanes()[0], record.EVENTS_FILE: led.events()[0],
                     record.RUNS_FILE: led.runs()[0], record.REFLECTIONS_FILE: led.reflections()[0],
                     record.PLAN_FILE: led.read_pass_file("plan", 3, 0.0), record.RESULTS_FILE: led.read_pass_file("results", 3, 0.0)}
            self.assertEqual(sorted(reads), sorted(named))
            for name, obj in reads.items():
                self.assertEqual(obj["schema"], record.SCHEMA, name)
            self.assertTrue(os.path.exists(os.path.join(d, "passes", "1970-01-01", "plan-3.json")))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TickRecordTests(unittest.TestCase):
    def setUp(self):
        self.repo = RecordRepo(); self.v = FakeVault(); self.inst = tempfile.mkdtemp(prefix="instance-")
        model = os.path.join(os.path.dirname(os.path.dirname(HERE)), "systems", "pipeline", "queueing-model.py")
        cfg = dict(CFG, vault=self.v.dir, model_path=model, backlog_cli=None, vault_autocommit=False,
                   lane_prompt="Work on {id}\n{item_body}",
                   regulator={"N0": 2, "N_min": 1, "N_max": 4, "budget": 20, "window_hours": 5, "lane_cap": 12})
        import yaml
        self.cfg_path = os.path.join(self.inst, "pipeline", "config.yaml")
        write(self.cfg_path, yaml.safe_dump(cfg))
        self.cfg = cfg

    def tearDown(self):
        self.repo.cleanup(); self.v.cleanup(); shutil.rmtree(self.inst, ignore_errors=True)

    def estate(self, path: str, **rr) -> None:
        write(os.path.join(self.inst, "meta-os.config.json"),
              json.dumps({"vars": {"rec": self.repo.root}, "swarm": {"record_repository": {"url": self.repo.url, "path": path, **rr}}}))

    def tick(self, *args: str) -> str:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tick.main(["--config", self.cfg_path, *args]), 0)
        return err.getvalue()

    def test_key_unset_runs_on_the_plain_directory_and_says_so(self):
        state = os.path.join(self.inst, "state")
        self.assertIn("record in the plain directory", self.tick("--state", state, "plan", "--out", os.path.join(self.inst, "p.json")))
        self.assertFalse(os.path.isdir(os.path.join(state, ".git")))
        self.assertEqual(Ledger(state).state()["schema"], record.SCHEMA)

    def test_key_set_one_commit_per_phase_naming_pass_phase_and_lanes(self):
        self.estate("${rec}/clone")
        plan_out = os.path.join(self.inst, "p.json")
        self.assertIn("record repository's git clone", self.tick("plan", "--out", plan_out))
        plan = load(plan_out)
        ids = sorted(s["lane_id"] for s in plan["spawn"])
        self.assertTrue(ids)
        self.assertEqual(self.repo.log()[0], "pass 1 plan: lanes changed: " + ", ".join(ids))
        clone = os.path.join(self.repo.root, "clone")
        stored = json.dumps(load(Ledger(clone).pass_path("plan", 1, plan["ts"])))
        self.assertNotIn("body of", stored, "the record names the item body by hash, never copies it")
        self.assertNotIn("prompt", stored)
        self.assertIn(plan["spawn"][0]["item_ref"]["sha256"], stored)
        res = os.path.join(self.inst, "r.json")
        write(res, json.dumps({"spawned": [{"lane_id": i, "ok": True, "session_id": "s-" + i} for i in ids], "checks": []}))
        self.tick("record", "--results", res)
        self.assertEqual(self.repo.log()[0], "pass 1 record: lanes changed: " + ", ".join(ids))
        self.assertEqual(len(self.repo.log()), 3)

    def test_unknown_schema_stops_the_run(self):
        self.estate("${rec}/clone")
        clone = os.path.join(self.repo.root, "clone")
        Ledger(clone, remote=self.repo.url)
        write(os.path.join(clone, record.STATE_FILE), json.dumps({"schema": 3}))
        git(clone, "add", "-A"); git(clone, "commit", "-q", "-m", "future"); git(clone, "push", "-q", "origin", "HEAD:main")
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            tick.main(["--config", self.cfg_path, "plan", "--out", os.path.join(self.inst, "p.json")])
        self.assertIn("schema 3", str(cm.exception))

    def test_nested_record_is_refused_unless_allowed(self):
        # Must fail if the check is missing: the clone sits inside the instance's own git tree.
        subprocess.run(["git", "init", "-q", self.inst], check=True)
        self.estate("record")
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            tick.main(["--config", self.cfg_path, "plan", "--out", os.path.join(self.inst, "p.json")])
        msg = str(cm.exception)
        self.assertIn("inside the instance's own git tree", msg)
        self.assertIn("record-migration step", msg)
        self.assertIsNone(re.search(r"\b[A-Z]{2,}-\d+\b", msg), "the message names no tracker key")
        import yaml
        write(self.cfg_path, yaml.safe_dump(dict(self.cfg, record_repository={"allow_nested": True})))
        self.assertIn("record repository's git clone", self.tick("plan", "--out", os.path.join(self.repo.root, "p.json")))


if __name__ == "__main__":
    unittest.main()
