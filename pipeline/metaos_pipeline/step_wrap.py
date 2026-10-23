"""The step wrapper: run one step and turn what it reports into inbox events.

    python3 -m metaos_pipeline.step_wrap --inbox DIR --run-id R [--log FILE] -- <cmd...>

The step's output passes through unchanged (into FILE if `--log` is given, stderr merged).
Each output line that parses as JSON and carries a rate-limit status writes one
`rate_limit` event (status, window, reset time, the raw line); a repeat of the same reading
within the step writes nothing. A reset time schedules one `window_reset` event for that
time (`events.schedule_window_reset`). On exit the wrapper writes `step_exit`: run id, exit
code, start and end, log path, and the last PR URL and outcome branch the step printed.

The rate-limit shape is unverified. The parser accepts what the agent CLI's session records
show (`rate_limit_info: {status, resetsAt, rateLimitType}`, reset in epoch seconds), at any
depth of the line, under either spelling, and ignores anything else.

A producer failure is reported on stderr and never changes the step's exit code.

The step runs in its own process group. SIGTERM, SIGINT or SIGHUP to the wrapper (the
runner reaping a silent step) terminates that group, kills it after `GRACE_SECONDS`, writes
`step_exit` with the `signal` (and `killed` if SIGKILL was needed), and exits 128 + signal.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

from metaos_pipeline import events

PR_RE = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")
BRANCH_RE = re.compile(r"outcome[-_ ]branch\W{1,4}([\w./-]+)", re.I)
INFO_KEYS = ("rate_limit_info", "rateLimitInfo")
RESET_KEYS = ("resetsAt", "resets_at", "resetAt", "reset_at")
WINDOW_KEYS = ("rateLimitType", "rate_limit_type", "window")
RAW_MAX = 4000
GRACE_SECONDS = 5.0
FORWARDED = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)


def _find_info(obj, depth: int = 0):
    if depth > 6:
        return None
    if isinstance(obj, dict):
        for k in INFO_KEYS:
            if isinstance(obj.get(k), dict) and obj[k].get("status"):
                return obj[k]
        if obj.get("type") == "rate_limit_event" and obj.get("status"):
            return obj
        children = obj.values()
    elif isinstance(obj, list):
        children = obj
    else:
        return None
    for v in children:
        found = _find_info(v, depth + 1)
        if found is not None:
            return found
    return None


def _epoch(v) -> int | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v / 1000) if v > 1e11 else int(v)  # milliseconds, if that is what it is
    if isinstance(v, str):
        if v.strip().isdigit():
            return _epoch(int(v))
        try:
            return int(datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return None
    return None


def parse_rate_limit(line: str) -> dict | None:
    """The rate-limit reading a JSON output line carries, or None."""
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        info = _find_info(json.loads(line))
    except (json.JSONDecodeError, RecursionError):
        return None
    if info is None:
        return None
    reset = next((_epoch(info[k]) for k in RESET_KEYS if k in info), None)
    window = next((str(info[k]) for k in WINDOW_KEYS if info.get(k)), "unknown")
    return {"status": str(info["status"]), "window": window, "resets_at": reset, "raw": line[:RAW_MAX]}


class Wrapper:
    def __init__(self, inbox: str, run_id: str, log: str | None):
        self.inbox, self.run_id, self.log = inbox, run_id, log
        self.source = f"step_wrap:{run_id}"
        self.seen: set[tuple] = set()
        self.pr_url = self.branch = None
        self.proc: subprocess.Popen | None = None
        self.signum: int | None = None
        self.killed = False

    def _terminate(self, signum, _frame) -> None:
        self.signum = signum
        if self.proc is None or self.proc.poll() is not None:
            return
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
            self.proc.wait(timeout=GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            self.killed = True
            os.killpg(self.proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def _safe(self, what: str, fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as exc:  # a producer never blocks the step
            print(f"step_wrap: {what} failed: {exc}", file=sys.stderr)

    def observe(self, line: str) -> None:
        for m in PR_RE.finditer(line):
            self.pr_url = m.group(0)
        for m in BRANCH_RE.finditer(line):
            self.branch = m.group(1)
        rl = parse_rate_limit(line)
        if rl is None:
            return
        key = (rl["status"], rl["window"], rl["resets_at"])
        if key in self.seen:
            return
        self.seen.add(key)
        self._safe("rate_limit event", events.write_event, self.inbox, "rate_limit", self.source,
                   {"run_id": self.run_id, **rl})
        if rl["resets_at"]:
            self._safe("window_reset scheduling", events.schedule_window_reset,
                       self.inbox, rl["window"], rl["resets_at"], self.source)

    def run(self, cmd: list[str]) -> int:
        started = time.time()
        out = None
        try:
            out = open(self.log, "ab") if self.log else None
            proc = self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, start_new_session=True,
                                                stderr=subprocess.STDOUT if out else None)
            previous = {s: signal.signal(s, self._terminate) for s in FORWARDED}
        except OSError as exc:
            print(f"step_wrap: cannot start step: {exc}", file=sys.stderr)
            code = 127
        else:
            sink = out or sys.stdout.buffer
            with proc.stdout:
                for raw in proc.stdout:
                    sink.write(raw)
                    sink.flush()
                    self._safe("output parse", self.observe, raw.decode("utf-8", "replace"))
            rc = proc.wait()
            for s, h in previous.items():
                signal.signal(s, h)
            code = 128 + self.signum if self.signum else (128 - rc if rc < 0 else rc)
        finally:
            if out:
                out.close()
        self._safe("step_exit event", events.write_event, self.inbox, "step_exit", self.source, {
            "run_id": self.run_id, "exit_code": code, "log": self.log,
            "started": started, "ended": time.time(), "pr_url": self.pr_url, "outcome_branch": self.branch,
            "signal": signal.Signals(self.signum).name if self.signum else None, "killed": self.killed})
        return code


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="metaos_pipeline.step_wrap", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inbox", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--log")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    if not cmd:
        ap.error("no step command after --")
    return Wrapper(a.inbox, a.run_id, a.log).run(cmd)


if __name__ == "__main__":
    sys.exit(main())
