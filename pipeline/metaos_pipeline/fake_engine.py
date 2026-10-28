"""The dry-run harness: a fake step engine, so the runner is tested without spending.

In process, `FakeEngine` stands in for `runner.OsEngine`. `spawn` gives each step a fake pid
and touches its log; a test then scripts what the step does, and each call writes what the
real step and its wrapper would: `progress` the log's mtime, `rate_limit` a `rate_limit`
event, `exit` a `step_exit` event. `kill` writes the `step_exit` the wrapper writes after a
forwarded SIGTERM. Nothing sleeps; the clock is the test's.

As a program it is a scripted step command for `step_wrap`:

    python3 -m metaos_pipeline.fake_engine [--line TEXT ...] [--exit N]

which prints each line (progress, a PR URL, a rate-limit JSON line) and exits N.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
from typing import Callable

from metaos_pipeline import events


class FakeEngine:
    def __init__(self, inbox: str, clock: Callable[[], float]):
        self.inbox, self.clock = inbox, clock
        self.steps: dict[str, dict] = {}
        self.spawned: list[list[str]] = []
        self.killed: list[int] = []
        self.runners_alive: set[int] = set()
        self._pid = 50000

    def spawn(self, argv: list[str]) -> int:
        rid, log = argv[argv.index("--run-id") + 1], argv[argv.index("--log") + 1]
        self._pid += 1
        self.steps[rid] = {"pid": self._pid, "log": log, "argv": argv, "alive": True}
        self.spawned.append(argv)
        self.progress(rid)
        return self._pid

    def find(self, run_id: str) -> int | None:
        st = self.steps.get(run_id)
        return st["pid"] if st and st["alive"] else None

    def runner_alive(self, pid: int) -> bool:
        return pid in self.runners_alive

    def kill(self, pid: int) -> None:
        self.killed.append(pid)
        for rid, st in self.steps.items():
            if st["pid"] == pid and st["alive"]:
                self.exit(rid, 128 + signal.SIGTERM, signal_name="SIGTERM")

    def progress(self, run_id: str) -> None:
        log = self.steps[run_id]["log"]
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "a", encoding="utf-8") as fh:
            fh.write("progress\n")
        os.utime(log, (self.clock(), self.clock()))

    def rate_limit(self, run_id: str, status: str = "rejected", resets_at: float | None = None,
                   window: str = "five_hour") -> None:
        events.write_event(self.inbox, "rate_limit", f"step_wrap:{run_id}",
                           {"run_id": run_id, "status": status, "window": window, "resets_at": resets_at})

    def exit(self, run_id: str, code: int = 0, pr_url: str | None = None, branch: str | None = None,
             signal_name: str | None = None) -> None:
        st = self.steps[run_id]
        st["alive"] = False
        events.write_event(self.inbox, "step_exit", f"step_wrap:{run_id}", {
            "run_id": run_id, "exit_code": code, "log": st["log"], "pr_url": pr_url, "outcome_branch": branch,
            "signal": signal_name, "killed": False})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="metaos_pipeline.fake_engine", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--line", action="append", default=[])
    ap.add_argument("--exit", type=int, default=0)
    a = ap.parse_args(argv)
    for line in a.line:
        print(line, flush=True)
    return a.exit


if __name__ == "__main__":
    sys.exit(main())
