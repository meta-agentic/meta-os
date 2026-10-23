#!/usr/bin/env python3
"""The sentinel: notices that an expected event did not come, and tells a human once.

    sentinel.py inbox    --inbox DIR --state DIR [--stall-minutes M] [--runner-state FILE] [--notify-cmd ARGV...]
    sentinel.py progress --marker FILE --watch PATH [--watch PATH ...] --state DIR [--stall-minutes M] [--notify-cmd ARGV...]

It never starts work and never runs on an interval: launchd starts it on a file change
(a `WatchPaths` job), and its only clock is a quiet timer that fires when nothing happened.

`inbox`: launchd starts it when the runner's inbox changes. An event is a regular file in
the inbox; a name starting with `.` (above all `.tmp*`, a partial write) is not an event.
The runner deletes an event once it has consumed it. The sentinel waits until the oldest
unconsumed event is `--stall-minutes` old, re-checking only at that deadline. An event still
there at its deadline means the runner is hung: the notify command runs once for it. The
sentinel exits as soon as no event is waiting.

`progress`: for interactive runs before the runner exists. A run's start writes `--marker`
(launchd watches the marker's directory); removing it disarms the sentinel, which exits at
its next check. While armed, progress is any file under a `--watch` path changing (mtime).
Silence for `--stall-minutes` notifies once; the next progress re-arms it.

Notify: `--notify-cmd` takes the rest of the command line as an argv, and the message is
appended as its last argument. If it is absent or fails, the message goes to stderr and,
on macOS, to a local notification. What was notified is recorded under `--state`, so a
restarted sentinel never notifies twice for one stall.

Exit: 0 done (nothing waiting, or disarmed), 2 a usage error.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time

TITLE = "meta-os sentinel"


def default_notify(message: str) -> None:
    print(f"{TITLE}: {message}", file=sys.stderr, flush=True)
    if sys.platform == "darwin":
        # The message is an argv item, never spliced into the script, so it cannot inject.
        script = ["-e", "on run argv", "-e", f'display notification (item 1 of argv) with title "{TITLE}"',
                  "-e", "end run"]
        subprocess.run(["osascript", *script, message], check=False, timeout=30,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def notify(cmd: list[str], message: str) -> None:
    if cmd:
        try:
            if subprocess.run([*cmd, message], check=False, timeout=60).returncode == 0:
                return
            print(f"{TITLE}: notify command failed; falling back", file=sys.stderr)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"{TITLE}: notify command failed ({exc}); falling back", file=sys.stderr)
    default_notify(message)


class State:
    """A small JSON record of what was notified, written atomically."""

    def __init__(self, directory: str, name: str):
        os.makedirs(directory, exist_ok=True)
        self.path = os.path.join(directory, f"{name}.json")
        self.lock_path = os.path.join(directory, f"{name}.lock")

    def load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def save(self, data: dict) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, sort_keys=True)
        os.replace(tmp, self.path)

    def lock(self):
        """The single-instance lock, or None if another sentinel of this kind holds it."""
        fh = open(self.lock_path, "w")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return None
        return fh


def events(inbox: str) -> list[tuple[float, str, str]]:
    """(mtime, name, key) of every event in the inbox, oldest first."""
    out = []
    try:
        entries = list(os.scandir(inbox))
    except FileNotFoundError:
        return []
    for entry in entries:
        if entry.name.startswith(".") or not entry.is_file(follow_symlinks=False):
            continue
        try:
            st = entry.stat(follow_symlinks=False)
        except FileNotFoundError:          # consumed while we looked
            continue
        out.append((st.st_mtime, entry.name, f"{entry.name}@{st.st_mtime_ns}"))
    return sorted(out)


def last_action(runner_state: str | None) -> tuple[str, str]:
    """(actor, last action) from the runner's state file; unknown when absent or unreadable."""
    if not runner_state:
        return "runner", "unknown (no runner state file)"
    try:
        with open(runner_state, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return "runner", f"unknown ({runner_state} unreadable)"
    if not isinstance(data, dict):
        return "runner", "unknown (runner state is not an object)"
    return str(data.get("actor") or "runner"), str(data.get("last_action") or "unknown")


def run_inbox(args) -> int:
    stall = args.stall_minutes * 60
    state = State(args.state, "sentinel-inbox")
    lock = state.lock()
    if lock is None:
        return 0                                    # another sentinel is already watching
    with lock:
        while True:
            now = time.time()
            found = events(args.inbox)
            seen = state.load().get("notified", {})
            live = {key for _, _, key in found}
            pending = [e for e in found if e[2] not in seen]
            if not pending:
                state.save({"notified": {k: v for k, v in seen.items() if k in live}})
                return 0
            mtime, name, key = pending[0]
            if now - mtime < stall:
                time.sleep(mtime + stall - now)    # the quiet timer: re-check only at the deadline
                continue
            actor, action = last_action(args.runner_state)
            minutes = (now - mtime) / 60
            notify(args.notify_cmd, f"{actor} stalled: event {name} unconsumed for {minutes:.1f} min; "
                                    f"last action: {action}")
            seen = {k: v for k, v in seen.items() if k in live}
            seen[key] = int(now)
            state.save({"notified": seen})


def latest_mtime(paths: list[str]) -> tuple[float, str]:
    """The newest mtime under the watched paths (symlinks not followed), and the file that has it."""
    best, where = 0.0, ""
    stack = list(paths)
    while stack:
        path = stack.pop()
        try:
            st = os.stat(path, follow_symlinks=False)
            if st.st_mtime > best:
                best, where = st.st_mtime, path
            if os.path.isdir(path) and not os.path.islink(path):
                stack.extend(e.path for e in os.scandir(path))
        except OSError:                             # vanished or unreadable: not progress
            continue
    return best, where


def run_progress(args) -> int:
    stall = args.stall_minutes * 60
    state = State(args.state, "sentinel-progress")
    lock = state.lock()
    if lock is None:
        return 0
    with lock:
        while os.path.exists(args.marker):
            now = time.time()
            last, where = latest_mtime([args.marker, *args.watch])
            if now - last < stall:
                time.sleep(last + stall - now)
                continue
            if state.load().get("notified_for") != last:
                quiet = (now - last) / 60
                notify(args.notify_cmd, f"run stalled: no progress for {quiet:.1f} min; "
                                        f"last change: {where or 'none'}")
                state.save({"notified_for": last})
            time.sleep(stall)                       # silent and already notified: wait for progress
        return 0


def parse(argv: list[str] | None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    for name in ("inbox", "progress"):
        p = sub.add_parser(name)
        p.add_argument("--state", required=True, help="directory for the lock and the notified record")
        p.add_argument("--stall-minutes", type=float, default=5.0,
                       help="quiet time before a stall (the instance's swarm.stall_minutes); fractions allowed")
        if name == "inbox":
            p.add_argument("--inbox", required=True)
            p.add_argument("--runner-state", help="JSON file with the runner's actor and last_action")
        else:
            p.add_argument("--marker", required=True, help="the file whose presence arms the sentinel")
            p.add_argument("--watch", action="append", default=[], required=True,
                           help="a file or directory whose changes count as progress (repeatable)")
        p.add_argument("--notify-cmd", nargs=argparse.REMAINDER, default=[],
                       help="argv of the notifier; the message is appended. Must come last")
    args = ap.parse_args(argv)
    if args.stall_minutes <= 0:
        ap.error("--stall-minutes must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    return run_inbox(args) if args.mode == "inbox" else run_progress(args)


if __name__ == "__main__":
    sys.exit(main())
