"""Append-only ledger and small state file, with atomic writes and a directory lock.

Files in the state directory (owned by the instance, never by the framework):

    state.json          N, tick counter, paused spaces, running calibration
    lanes.json          current lanes (materialised view)
    events.ndjson       every lane event, append-only
    runs.ndjson         one record per tick (plan + outcome)
    reflections.ndjson  one reflection record per tick
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
import time
from contextlib import contextmanager
from typing import Any, Iterator


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
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


class Ledger:
    def __init__(self, state_dir: str):
        self.dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        self.state_path = os.path.join(state_dir, "state.json")
        self.lanes_path = os.path.join(state_dir, "lanes.json")
        self.events_path = os.path.join(state_dir, "events.ndjson")
        self.runs_path = os.path.join(state_dir, "runs.ndjson")
        self.reflections_path = os.path.join(state_dir, "reflections.ndjson")
        self.lock_path = os.path.join(state_dir, ".lock")

    @contextmanager
    def locked(self) -> Iterator[None]:
        with open(self.lock_path, "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    # ---- state ----
    def state(self, defaults: dict | None = None) -> dict:
        if os.path.exists(self.state_path):
            with open(self.state_path, encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = {}
        base = dict(defaults or {})
        base.update(data)
        return base

    def save_state(self, state: dict) -> None:
        _atomic_write(self.state_path, json.dumps(state, indent=1, sort_keys=True))

    # ---- lanes ----
    def lanes(self) -> list[dict]:
        if not os.path.exists(self.lanes_path):
            return []
        with open(self.lanes_path, encoding="utf-8") as fh:
            return json.load(fh)

    def save_lanes(self, lanes: list[dict]) -> None:
        _atomic_write(self.lanes_path, json.dumps(lanes, indent=1, sort_keys=True))

    def event(self, kind: str, **fields: Any) -> None:
        _append(self.events_path, {"ts": time.time(), "kind": kind, **fields})

    def run(self, record: dict) -> None:
        _append(self.runs_path, {"ts": time.time(), **record})

    def runs(self) -> list[dict]:
        return _read_ndjson(self.runs_path)

    def reflection(self, record: dict) -> None:
        _append(self.reflections_path, {"ts": time.time(), **record})

    def reflections(self) -> list[dict]:
        return _read_ndjson(self.reflections_path)

    def events(self) -> list[dict]:
        return _read_ndjson(self.events_path)


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
