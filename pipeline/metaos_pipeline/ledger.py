"""The pipeline's record: atomic state, append-only logs, a lock, and optionally a git clone.

The record's files, their shapes and their writers are named in `pipeline/record.md` (the
read contract). The names live here, once, so renaming one is a one-line change.

Two modes:

- **plain directory** (no record repository configured): files are written in place, as the
  prototype did;
- **git clone** of the record repository: every phase fetches and fast-forwards before it
  writes, refuses to write on a clone it cannot prove current, and ends in at most one commit,
  pushed at once. A push rejected as non-fast-forward discards the phase's local commit,
  re-fetches and replays the phase from the new state; nothing is ever force-pushed.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import tempfile
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

SCHEMA = 2
# 1 is the prototype's state directory (files without a `schema` field): read, never written.
KNOWN_SCHEMAS = (1, 2)

STATE_FILE = "state.json"
LANES_FILE = "lanes.json"
EVENTS_FILE = "events.ndjson"
RUNS_FILE = "runs.ndjson"
REFLECTIONS_FILE = "reflections.ndjson"
PASSES_DIR = "passes"
PLAN_FILE = PASSES_DIR + "/<date>/plan-<n>.json"
RESULTS_FILE = PASSES_DIR + "/<date>/results-<n>.json"
RUN_DIR = "runs"
RUN_FILE = RUN_DIR + "/run-<n>.json"
RECORD_FILES = (STATE_FILE, LANES_FILE, EVENTS_FILE, RUNS_FILE, REFLECTIONS_FILE, PLAN_FILE, RESULTS_FILE, RUN_FILE)


class LedgerError(Exception):
    """Base of every refusal; its message is the reason the run stops with."""


class SchemaError(LedgerError):
    pass


class StaleClone(LedgerError):
    pass


class PushRejected(LedgerError):
    pass


class NestedRecord(LedgerError):
    pass


def _check(obj: Any, where: str) -> Any:
    schema = obj.get("schema", 1) if isinstance(obj, dict) else 1
    if schema not in KNOWN_SCHEMAS:
        raise SchemaError(f"{where}: schema {schema!r} is not one this pipeline reads {KNOWN_SCHEMAS}; "
                          "upgrade the framework before running on this record")
    return obj


def _atomic_write(path: str, data: str) -> None:
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _append(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, sort_keys=True) + "\n")


def _read_ndjson(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if line:
                try:
                    out.append(_check(json.loads(line), f"{os.path.basename(path)} line {n}"))
                except json.JSONDecodeError:
                    continue
    return out


def _fingerprint(lane: dict) -> str:
    return json.dumps({k: v for k, v in lane.items() if k != "schema"}, sort_keys=True)


def _git(path: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, timeout=180)


def item_ref(vault: str, path: str) -> dict:
    """How the record names an item body: the vault commit and the body's hash, never its text."""
    with open(path, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    head = _git(vault, "rev-parse", "HEAD")
    return {"path": os.path.relpath(path, vault), "vault_sha": head.stdout.strip() if head.returncode == 0 else None,
            "sha256": digest}


def check_not_nested(record_path: str, instance_dir: str, allow: bool) -> None:
    """Refuse a record clone inside the instance's own git tree unless `allow_nested` is set."""
    top = _git(instance_dir, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        return
    tree = os.path.realpath(top.stdout.strip())
    rec = os.path.realpath(record_path)
    if (rec == tree or rec.startswith(tree + os.sep)) and not allow:
        raise NestedRecord(f"the record repository's clone {record_path} sits inside the instance's own git tree "
                           f"{tree}, so its commits would mix with the instance's history. Move the record out of "
                           "the instance with the instance's record-migration step, or set "
                           "`record_repository.allow_nested: true` in the pipeline's configuration to accept it.")


class _Clone:
    """The record repository's local clone; every refusal happens before anything is written."""

    def __init__(self, path: str, url: str):
        self.path, self.url = path, url

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return _git(self.path, *args)

    def ensure(self) -> None:
        if not os.path.isdir(os.path.join(self.path, ".git")):
            if os.path.isdir(self.path) and os.listdir(self.path):
                raise StaleClone(f"{self.path} exists and is not a git clone; refusing to write the record there")
            r = subprocess.run(["git", "clone", "-q", self.url, self.path], capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                raise StaleClone(f"cannot clone the record repository into {self.path}: {r.stderr.strip()[-300:]}")
        origin = self._run("remote", "get-url", "origin").stdout.strip()
        if origin != self.url:
            raise StaleClone(f"{self.path} is a clone of {origin or 'nothing'}, not of the configured record repository")

    def branch(self) -> str:
        return self._run("symbolic-ref", "--short", "HEAD").stdout.strip() or "main"

    def sync(self) -> None:
        f = self._run("fetch", "-q", "origin")
        if f.returncode != 0:
            raise StaleClone(f"fetch failed, so the clone may be stale; refusing to write: {f.stderr.strip()[-300:]}")
        if self._run("status", "--porcelain").stdout.strip():
            raise StaleClone(f"{self.path} has uncommitted changes from an earlier run; refusing to write over them")
        remote = f"origin/{self.branch()}"
        has_head = self._run("rev-parse", "--verify", "-q", "HEAD").returncode == 0
        if self._run("rev-parse", "--verify", "-q", remote).returncode != 0:
            if has_head:
                self._push_pending(remote, 0)
            return  # an empty record repository: the first phase makes its first commit
        if not has_head:
            self._run("reset", "-q", "--hard", remote)
            return
        ahead, behind = (int(x) for x in self._run("rev-list", "--left-right", "--count", f"HEAD...{remote}").stdout.split())
        if ahead and behind:
            raise StaleClone(f"{self.path} holds {ahead} commit(s) not on {remote}, which holds {behind} not here: "
                             "a pending pass cannot be replayed without its phase, so a human resolves it")
        if ahead:
            self._push_pending(remote, ahead)
        if behind and self._run("merge", "-q", "--ff-only", remote).returncode != 0:
            raise StaleClone(f"cannot fast-forward {self.path} to {remote}; refusing to write")

    def _push(self) -> None:
        p = self._run("push", "-q", "origin", f"HEAD:refs/heads/{self.branch()}")
        if p.returncode != 0:
            if any(s in p.stderr for s in ("non-fast-forward", "fetch first", "rejected")):
                raise PushRejected(p.stderr.strip()[-300:])
            raise LedgerError(f"record push failed; the commit stays local and the next phase pushes it: {p.stderr.strip()[-300:]}")

    def _push_pending(self, remote: str, ahead: int) -> None:
        """An earlier push failed and the remote has not moved since: push those commits first (never forced)."""
        try:
            self._push()
        except PushRejected:
            raise StaleClone(f"{self.path} holds {ahead or 'its'} commit(s) not on {remote}, and the remote moved before "
                             "they were pushed: a pending pass cannot be replayed without its phase, so a human resolves it") from None
        except LedgerError as exc:
            raise LedgerError(f"record push pending, retried and failed again; the next run retries: {exc}") from None

    def commit_and_push(self, message: str) -> str | None:
        self._run("add", "-A")
        if not self._run("status", "--porcelain").stdout.strip():
            return None
        c = self._run("commit", "-q", "-m", message)
        if c.returncode != 0:
            raise LedgerError(f"record commit failed: {(c.stdout + c.stderr).strip()[-300:]}")
        self._push()
        return self._run("rev-parse", "HEAD").stdout.strip()

    def discard_uncommitted(self) -> None:
        self._run("reset", "-q", "--hard")
        self._run("clean", "-qfd")

    def discard_local(self) -> None:
        """Drop the phase's own unpushed commit and take the remote's state (never a force-push)."""
        self._run("fetch", "-q", "origin")
        self._run("reset", "-q", "--hard", f"origin/{self.branch()}")


class Ledger:
    def __init__(self, state_dir: str, remote: str | None = None):
        self.dir = state_dir
        self.remote = remote
        self._clone = _Clone(state_dir, remote) if remote else None
        if self._clone:
            self._clone.ensure()
        else:
            os.makedirs(state_dir, exist_ok=True)
        self.state_path = os.path.join(state_dir, STATE_FILE)
        self.lanes_path = os.path.join(state_dir, LANES_FILE)
        self.events_path = os.path.join(state_dir, EVENTS_FILE)
        self.runs_path = os.path.join(state_dir, RUNS_FILE)
        self.reflections_path = os.path.join(state_dir, REFLECTIONS_FILE)
        # In a clone the lock lives under .git, so it is never part of the record.
        self.lock_path = os.path.join(state_dir, ".git" if remote else "", "ledger.lock" if remote else ".lock")
        self._synced = not remote
        self._lanes_before: dict[str, str] | None = None
        self._lanes_after: dict[str, str] = {}
        self._pass: Any = None

    def describe(self) -> str:
        if self._clone:
            return f"the record repository's git clone {self.dir}"
        return f"the plain directory {self.dir} (swarm.record_repository unset)"

    @contextmanager
    def locked(self, phase: str | None = None) -> Iterator[None]:
        """Hold the lock for one phase; in a clone, fetch first and, for a named phase, end in its commit.

        A clean exit of a named phase calls `commit_pass` with a message naming the pass, the phase
        and every lane it changed; it raises `PushRejected` when the remote moved (see `replay`).
        A phase that fails leaves no uncommitted file behind.
        """
        with open(self.lock_path, "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                if self._clone:
                    self._clone.sync()
                    self._synced = True
                self._lanes_before, self._lanes_after, self._pass = None, {}, None
                try:
                    yield
                except BaseException:
                    if self._clone:
                        self._clone.discard_uncommitted()
                    raise
                if phase:
                    lanes = ", ".join(self.changed_lanes()) or "none"
                    try:
                        self.commit_pass(f"pass {self._pass if self._pass is not None else '?'} {phase}: lanes changed: {lanes}")
                    except PushRejected:
                        self._clone.discard_local()  # still under the lock: the tree is clean when it is free
                        raise
            finally:
                self._synced = not self._clone
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _writable(self) -> None:
        if not self._synced:
            raise StaleClone("a write outside a fetched phase was refused: the clone may be stale")

    def commit_pass(self, message: str) -> str | None:
        """Commit and push what the phase changed, at once; a no-op (None) when nothing changed or no clone."""
        self._writable()
        return self._clone.commit_and_push(message) if self._clone else None

    def replay(self, phase: Callable[[], Any], attempts: int = 3) -> Any:
        """Run a phase; on a non-fast-forward push drop its local commit and run it again from the new state."""
        for _ in range(attempts):
            try:
                return phase()
            except PushRejected:
                continue
        raise StaleClone(f"the record's push was rejected {attempts} times; the remote moved under every replay")

    def changed_lanes(self) -> list[str]:
        """Lane ids this phase changed, for the commit message."""
        before = self._lanes_before or {}
        return sorted(k for k, v in self._lanes_after.items() if before.get(k) != v)

    # ---- state ----
    def state(self, defaults: dict | None = None) -> dict:
        if os.path.exists(self.state_path):
            with open(self.state_path, encoding="utf-8") as fh:
                data = _check(json.load(fh), STATE_FILE)
        else:
            data = {}
        base = dict(defaults or {})
        base.update(data)
        return base

    def save_state(self, state: dict) -> None:
        self._writable()
        self._pass = state.get("tick", self._pass)
        _atomic_write(self.state_path, json.dumps({**state, "schema": SCHEMA}, indent=1, sort_keys=True))

    # ---- lanes ----
    def lanes(self) -> list[dict]:
        if not os.path.exists(self.lanes_path):
            lanes: list[dict] = []
        else:
            with open(self.lanes_path, encoding="utf-8") as fh:
                lanes = [_check(l, f"{LANES_FILE} lane {l.get('lane_id')}") for l in json.load(fh)]
        if self._lanes_before is None:
            self._lanes_before = {l["lane_id"]: _fingerprint(l) for l in lanes if "lane_id" in l}
        return lanes

    def save_lanes(self, lanes: list[dict]) -> None:
        self._writable()
        lanes = [{**l, "schema": SCHEMA} for l in lanes]
        self._lanes_after = {l["lane_id"]: _fingerprint(l) for l in lanes if "lane_id" in l}
        _atomic_write(self.lanes_path, json.dumps(lanes, indent=1, sort_keys=True))

    def _log(self, path: str, record: dict) -> None:
        self._writable()
        _append(path, {"ts": time.time(), **record, "schema": SCHEMA})

    def event(self, kind: str, **fields: Any) -> None:
        self._log(self.events_path, {"kind": kind, **fields})

    def run(self, record: dict) -> None:
        self._log(self.runs_path, record)

    def runs(self) -> list[dict]:
        return _read_ndjson(self.runs_path)

    def reflection(self, record: dict) -> None:
        self._log(self.reflections_path, record)

    def reflections(self) -> list[dict]:
        return _read_ndjson(self.reflections_path)

    def events(self) -> list[dict]:
        return _read_ndjson(self.events_path)

    # ---- the pass's plan and results ----
    def pass_path(self, kind: str, n: int, ts: float) -> str:
        return os.path.join(self.dir, PASSES_DIR, time.strftime("%Y-%m-%d", time.gmtime(ts)), f"{kind}-{n}.json")

    def write_pass_file(self, kind: str, n: int, ts: float, doc: dict) -> str:
        self._writable()
        path = self.pass_path(kind, n, ts)
        _atomic_write(path, json.dumps({**doc, "schema": SCHEMA}, indent=1, sort_keys=True))
        return path

    def read_pass_file(self, kind: str, n: int, ts: float) -> dict:
        with open(self.pass_path(kind, n, ts), encoding="utf-8") as fh:
            return _check(json.load(fh), f"{kind}-{n}.json")

    # ---- finished runs: one immutable file each, numbered by the run counter in state.json ----
    def finished_run(self, state: dict, doc: dict) -> int:
        """File a finished run as `runs/run-<n>.json` and its line in `runs/_index.md`; the caller saves `state`."""
        self._writable()
        counters = state.setdefault("counters", {})
        n = int(counters.get("run", 0)) + 1
        counters["run"] = n
        _atomic_write(os.path.join(self.dir, RUN_DIR, f"run-{n}.json"), json.dumps({**doc, "n": n, "schema": SCHEMA}, indent=1, sort_keys=True))
        idx = os.path.join(self.dir, RUN_DIR, "_index.md")
        if not os.path.exists(idx):
            _atomic_write(idx, "# Finished runs\n\n")
        with open(idx, "a", encoding="utf-8") as fh:
            fh.write(f"- run-{n}: {doc.get('run_id')} {doc.get('lane_id')} {doc.get('item') or doc.get('decision')} {doc.get('outcome')}\n")
        return n

    def read_run(self, n: int) -> dict:
        with open(os.path.join(self.dir, RUN_DIR, f"run-{n}.json"), encoding="utf-8") as fh:
            return _check(json.load(fh), f"run-{n}.json")


def usage_delta(lane: dict) -> tuple[float, float]:
    """(cost delta, token delta) between the last two usage snapshots of a lane."""
    snaps = lane.get("usage") or []
    if len(snaps) < 2:
        if len(snaps) == 1:
            s = snaps[-1]
            return float(s.get("cost_usd", 0.0)), float(s.get("tokens", 0.0))
        return 0.0, 0.0
    a, b = snaps[-2], snaps[-1]
    return (max(0.0, float(b.get("cost_usd", 0.0)) - float(a.get("cost_usd", 0.0))),
            max(0.0, float(b.get("tokens", 0.0)) - float(a.get("tokens", 0.0))))
