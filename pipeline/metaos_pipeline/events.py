"""The runner's inbox: the event file format and its one writer.

The runner has no cadence; it blocks on an inbox directory and runs one pass per event.
Producers only write here: they never read the record, take the lease or start work.

An event is one file, `<at>-<kind>-<8 hex>.json`, where `<at>` is the UTC write time as
`yyyymmddTHHMMSS.ffffffZ`, so the names sort by time. The body is one JSON object:

    {"schema": 1, "id": "<the name without .json>", "kind": "...", "at": "<ISO 8601 UTC>",
     "source": "<who saw it>", "payload": {...}}

Kinds a producer writes: `step_exit`, `rate_limit`, `window_reset`, `vault_commit`,
`remote_change`. `control` and `stall` are reserved for the runner; the CLI refuses them.

A write is atomic: the body goes to `.tmp-<name>` in the inbox and is renamed into place, so
a reader sees a whole event or none. Names starting with `.` (`.tmp-*` partial writes, the
`.scheduled/` marker directory) are never events. The runner deletes an event only after the
pass that consumed it has committed.

    python3 -m metaos_pipeline.events emit <kind> --inbox DIR --source S [--payload JSON]
                                                  [--at EPOCH]  (sleep until then, then write)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Callable

SCHEMA = 1
KINDS = ("step_exit", "rate_limit", "window_reset", "vault_commit", "remote_change")
RESERVED = ("control", "stall")
PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write_event(inbox: str, kind: str, source: str, payload: dict | None = None,
                now: float | None = None) -> str:
    """Write one event atomically; return its path. Raises OSError if the inbox is unwritable."""
    if kind not in KINDS + RESERVED:
        raise ValueError(f"unknown event kind {kind!r}")
    if not source:
        raise ValueError("an event needs a source")
    t = datetime.fromtimestamp(time.time() if now is None else now, tz=timezone.utc)
    eid = f"{t.strftime('%Y%m%dT%H%M%S.%fZ')}-{kind}-{secrets.token_hex(4)}"
    body = {"schema": SCHEMA, "id": eid, "kind": kind,
            "at": t.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "source": source, "payload": payload or {}}
    os.makedirs(inbox, exist_ok=True)
    path = os.path.join(inbox, eid + ".json")
    tmp = os.path.join(inbox, ".tmp-" + eid + ".json")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(body, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.rename(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def list_events(inbox: str) -> list[dict]:
    """The inbox's events, oldest first, each with its `path`. Skips dot-files and unreadable files."""
    if not os.path.isdir(inbox):
        return []
    out = []
    for name in sorted(os.listdir(inbox)):
        path = os.path.join(inbox, name)
        if name.startswith(".") or not name.endswith(".json") or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                ev = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(ev, dict) and ev.get("schema") == SCHEMA:
            out.append({**ev, "path": path})
    return out


def _detached(argv: list[str]) -> None:
    env = {**os.environ, "PYTHONPATH": PKG_ROOT}  # importable whatever the caller's cwd and env
    subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL, cwd=PKG_ROOT,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, close_fds=True)


def schedule_window_reset(inbox: str, window: str, resets_at: int, source: str,
                          spawn: Callable[[list[str]], None] = _detached) -> bool:
    """Arrange ONE `window_reset` event at `resets_at` (epoch seconds) for this window.

    Idempotent per (window, resets_at): the marker `<inbox>/.scheduled/window-reset-<window>-
    <resets_at>` is created with O_EXCL, so a second step hitting the same limit schedules
    nothing. Each call prunes the markers whose reset has passed, and a reset already past is
    not scheduled. Returns True if this call scheduled it. The one-shot is a detached process
    that sleeps, writes, and exits.
    """
    now = time.time()
    if resets_at <= now:
        return False
    mdir = os.path.join(inbox, ".scheduled")
    os.makedirs(mdir, exist_ok=True)
    for name in os.listdir(mdir):
        m = re.match(r"^window-reset-.*-(\d+)$", name)
        if m and int(m.group(1)) < now:
            try:
                os.unlink(os.path.join(mdir, name))
            except FileNotFoundError:
                pass
    safe = re.sub(r"[^A-Za-z0-9_]", "_", window)[:40] or "unknown"
    marker = os.path.join(mdir, f"window-reset-{safe}-{int(resets_at)}")
    try:
        os.close(os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644))
    except FileExistsError:
        return False
    payload = json.dumps({"window": window, "resets_at": int(resets_at)})
    try:
        spawn([sys.executable, "-m", "metaos_pipeline.events", "emit", "window_reset",
               "--inbox", inbox, "--source", source, "--payload", payload, "--at", str(int(resets_at))])
    except Exception:
        os.unlink(marker)  # let the next step retry
        raise
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="metaos_pipeline.events", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("emit")
    e.add_argument("kind", choices=KINDS)
    e.add_argument("--inbox", required=True)
    e.add_argument("--source", required=True)
    e.add_argument("--payload", default="{}")
    e.add_argument("--at", type=float, help="epoch seconds: sleep until then, then write")
    a = ap.parse_args(argv)
    try:
        payload = json.loads(a.payload)
    except json.JSONDecodeError as exc:
        ap.error(f"--payload is not JSON: {exc}")
    if not isinstance(payload, dict):
        ap.error("--payload must be a JSON object")
    if a.at is not None:
        time.sleep(max(0.0, a.at - time.time()))
    print(write_event(a.inbox, a.kind, a.source, payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
