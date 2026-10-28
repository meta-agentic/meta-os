"""The runner: the pipeline's loop, driven by events, with no cadence (ADR D1).

    tick.py --config CFG [--state DIR] run --inbox DIR [--work DIR]

It takes the lease, then blocks on the inbox and runs one pass per batch of events. The wait
costs nothing while idle: the kernel's file events on the inbox directory (kqueue on macOS and
the BSDs, inotify on Linux), and only where neither exists a look every `POLL_SECONDS`, the
declared fallback, which says so when the runner starts. No event, no pass.

A pass, under the record's lock (one fetch, one commit, pushed at once):

1. check the lease; a higher epoch or another holder ends the runner;
2. reconcile: adopt each `spawning` run a lost pass left whose step is found by its run id and
   fail an absent one (`failed_spawn`, its item never transitioned); read step exits; hold new
   starts on a rate-limit stop until `window_reset`, or until a pass past the recorded reset;
   kill and reap a step with no progress for `stall_minutes` (no `step_exit`, log unchanged),
   giving its item back with `retry+1` and the reason;
3. record that; plan into the free slots (nothing while starts are held);
4. checkpoint the planned runs as `spawning`, start each step under `step_wrap`, record the starts;
5. start the supervisor step for what needs judgement (`supervisor_command`, the instance's choice);
6. commit, then delete the events the pass consumed.

Quiet timers are the only clocks: when the earliest step deadline passes with no progress, the
runner writes a `stall` event and the next pass reaps. The runner never merges, never moves an
item to DONE or NO GO, never creates an item and never changes its configuration.

A step is `step_command` from the pipeline config, an argv whose `{prompt_file}`, `{run_id}`,
`{lane_id}`, `{repo}`, `{branch}`, `{item}` and `{log}` are filled in; the supervisor's
`supervisor_command` gets `{evidence_file}`, `{run_id}` and `{record}`.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import json
import os
import select
import signal
import socket
import subprocess
import sys
import time
import uuid
from typing import Callable

from . import events, slots
from .ledger import Ledger, PushRejected, StaleClone

STALL_MINUTES = 5.0
POLL_SECONDS = 2.0
OK_STATUSES = ("allowed", "allowed_warning")  # a rate-limit status that does not stop starts
PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class LeaseLost(Exception):
    """Another runner holds the lease or took it; the message says which."""


class _Stop(Exception):
    pass


class OsEngine:
    """Steps as processes. A step's wrapper carries `--run-id <id>` in its argv, so a restarted runner finds it."""

    def __init__(self):
        self.procs: list[subprocess.Popen] = []

    def spawn(self, argv: list[str]) -> int:
        p = subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, env={**os.environ, "PYTHONPATH": PKG_ROOT}, close_fds=True)
        self.procs.append(p)
        return p.pid

    def reap(self) -> None:
        self.procs = [p for p in self.procs if p.poll() is None]

    def _ps(self, *args: str) -> str:
        return subprocess.run(["ps", *args], capture_output=True, text=True).stdout

    def find(self, run_id: str) -> int | None:
        self.reap()
        for line in self._ps("-axo", "pid=,command=").splitlines():
            pid, _, cmd = line.strip().partition(" ")
            if "metaos_pipeline.step_wrap" in cmd and f"--run-id {run_id} " in cmd + " ":
                return int(pid)
        return None

    def kill(self, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGTERM)  # the wrapper forwards it to the step's process group
        except ProcessLookupError:
            pass

    def runner_alive(self, pid: int) -> bool:
        cmd = self._ps("-p", str(pid), "-o", "command=")
        return "tick.py" in cmd and " run" in cmd


class KqueueWaiter:
    """Wakes on any write to the inbox directory, or at the timeout; costs nothing while idle."""

    def __init__(self, inbox: str):
        self.fd = os.open(inbox, os.O_RDONLY)
        self.kq = select.kqueue()
        self.kq.control([select.kevent(self.fd, select.KQ_FILTER_VNODE, select.KQ_EV_ADD | select.KQ_EV_CLEAR,
                                       select.KQ_NOTE_WRITE)], 0)

    def wait(self, timeout: float | None) -> None:
        self.kq.control(None, 1, timeout)


class PollWaiter:
    """The declared fallback where the platform has no kernel file events: looks every `seconds`."""

    def __init__(self, inbox: str, seconds: float = POLL_SECONDS,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        self.inbox, self.seconds, self.clock, self.sleep = inbox, seconds, clock, sleep

    def wait(self, timeout: float | None) -> None:
        end = None if timeout is None else self.clock() + timeout
        while not events.list_events(self.inbox):
            left = None if end is None else end - self.clock()
            if left is not None and left <= 0:
                return
            self.sleep(self.seconds if left is None else min(self.seconds, left))


class InotifyWaiter:
    """Linux: wakes on a file created, moved in, written or removed in the inbox, or at the timeout.

    Through the C library's inotify calls (ctypes, no dependency); costs nothing while idle.
    """

    IN_CLOSE_WRITE, IN_MOVED_TO, IN_CREATE, IN_DELETE = 0x8, 0x80, 0x100, 0x200
    IN_NONBLOCK, IN_CLOEXEC = 0o4000, 0o2000000

    def __init__(self, inbox: str, libc=None):
        self.libc = libc or inotify_libc()
        if self.libc is None:
            raise OSError("inotify is not available on this platform")
        self.fd = self.libc.inotify_init1(self.IN_NONBLOCK | self.IN_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1 failed")
        mask = self.IN_CLOSE_WRITE | self.IN_MOVED_TO | self.IN_CREATE | self.IN_DELETE
        if self.libc.inotify_add_watch(self.fd, os.fsencode(inbox), mask) < 0:
            err = ctypes.get_errno()
            os.close(self.fd)
            raise OSError(err, f"inotify_add_watch failed on {inbox}")

    def wait(self, timeout: float | None) -> None:
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if ready:
            try:
                while os.read(self.fd, 65536):  # drain: the events only say that something changed
                    pass
            except BlockingIOError:
                pass


def inotify_libc():
    """The C library with inotify, on Linux; None elsewhere."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
    except OSError:
        return None
    return libc if hasattr(libc, "inotify_init1") and hasattr(libc, "inotify_add_watch") else None


def waiter_for(inbox: str):
    """The platform's kernel file events on the inbox; the poll only where it has none, said once."""
    if hasattr(select, "kqueue"):
        return KqueueWaiter(inbox)
    if inotify_libc() is not None:
        return InotifyWaiter(inbox)
    print(f"tick run: no kernel file events on this platform: looking at the inbox every {POLL_SECONDS:g} s",
          file=sys.stderr)
    return PollWaiter(inbox)


def fill(template: list[str], fields: dict) -> list[str]:
    out = []
    for arg in template:
        for k, v in fields.items():
            arg = str(arg).replace("{" + k + "}", str(v))
        out.append(arg)
    return out


class Runner:
    def __init__(self, cfg: dict, led: Ledger, inbox: str, work: str, *, plan: Callable, record: Callable,
                 vault: Callable | None = None, stall_minutes: float = STALL_MINUTES, engine=None, waiter=None,
                 clock: Callable[[], float] = time.time, host: str | None = None, pid: int | None = None):
        if not cfg.get("step_command"):
            raise SystemExit("tick run: the pipeline config sets no `step_command`, so no step can start")
        self.cfg, self.led, self.inbox, self.work = cfg, led, inbox, work
        os.makedirs(inbox, exist_ok=True)
        os.makedirs(work, exist_ok=True)
        self.plan, self.record, self.vault = plan, record, vault
        self.stall = float(stall_minutes) * 60
        self.engine = engine or OsEngine()
        self.waiter = waiter or waiter_for(inbox)
        self.clock = clock
        self.host, self.pid = host or socket.gethostname(), pid or os.getpid()
        self.holder = f"runner-{uuid.uuid4().hex[:8]}"
        self.epoch: int | None = None
        self.stopping = self._waiting = False
        self.passes = 0

    # ---------------------------------------------------------------- the lease
    def take_lease(self) -> None:
        """Take the lease or raise LeaseLost, recording the loss; the record's push arbitrates two takers."""
        why = self.led.replay(self._take)
        if why:
            raise LeaseLost(why)

    def _take(self) -> str | None:
        with self.led.locked("lease"):
            state = self.led.state()
            loop = state.get("loop") or {}
            why = self._refusal(loop)
            if why:
                self.led.event("lease_lost", holder=self.holder, host=self.host, pid=self.pid, reason=why)
                return why
            self.epoch = int(loop.get("epoch") or 0) + 1
            state["loop"] = {"holder": self.holder, "host": self.host, "pid": self.pid, "started": self.clock(),
                             "epoch": self.epoch}
            self.led.event("lease_taken", **state["loop"])
            self.led.save_state(state)
        return None

    def _refusal(self, loop: dict) -> str | None:
        if loop.get("host") and loop["host"] != self.host:
            return (f"the lease is held for {loop['host']} (epoch {loop.get('epoch')}); a runner never takes it from "
                    "another host: a human moves it with `tick.py control lease take`")
        if loop.get("holder") and loop.get("pid") and int(loop["pid"]) != self.pid and self.engine.runner_alive(int(loop["pid"])):
            return f"the runner {loop['holder']} (pid {loop['pid']}) on this host holds the lease"
        return None

    def check_lease(self, state: dict) -> None:
        loop = state.get("loop") or {}
        if loop.get("holder") != self.holder or loop.get("epoch") != self.epoch:
            raise LeaseLost(f"the lease is now epoch {loop.get('epoch')} for {loop.get('holder') or loop.get('host')}")

    def release(self) -> None:
        def _release() -> None:
            with self.led.locked("release"):
                state = self.led.state()
                loop = state.get("loop") or {}
                if loop.get("holder") == self.holder and loop.get("epoch") == self.epoch:
                    state["loop"] = {**loop, "holder": None, "host": None, "pid": None, "released": self.clock()}
                    self.led.event("lease_released", holder=self.holder, epoch=self.epoch)
                    self.led.save_state(state)
        self.led.replay(_release)

    # ---------------------------------------------------------------- the loop
    def stop(self, *_args) -> None:
        self.stopping = True
        if self._waiting:
            raise _Stop()

    def run(self, max_passes: int | None = None) -> int:
        """Serve the inbox until stopped. A lost lease exits 0 too, so KeepAlive restarts only a crashed runner."""
        try:
            self.take_lease()
            if any(not r.get("started") for r in self._runs()):
                self.run_pass([])  # a pass was lost after its plan: adopt or fail its runs now
            while not self.stopping and (max_passes is None or self.passes < max_passes):
                evs = events.list_events(self.inbox)
                if evs:
                    self.run_pass(evs)
                    continue
                self._waiting = True
                try:
                    if self.stopping:
                        break
                    self.waiter.wait(self.next_deadline())
                except _Stop:
                    break
                finally:
                    self._waiting = False
                self.quiet_timers()
        except LeaseLost as exc:
            print(f"tick run: stopped: {exc}", file=sys.stderr)
            return 0
        self.release()
        return 0

    def _runs(self) -> list[dict]:
        return [s["run"] for s in self.led.lanes() if isinstance(s.get("run"), dict)]

    def _watched(self) -> list[dict]:
        """Every started step under a quiet timer: the slots' runs and the supervisor."""
        out = [r for r in self._runs() if r.get("started")]
        sup = self.led.state().get("supervisor")
        return out + ([sup] if sup else [])

    def progress(self, rec: dict) -> float:
        """The step's last sign of progress: its start, its heartbeat, its log's mtime."""
        t = max(float(rec.get("started") or 0), float(rec.get("heartbeat") or 0))
        try:
            t = max(t, os.stat(rec["log"]).st_mtime)
        except (KeyError, TypeError, OSError):
            pass
        return t

    def next_deadline(self) -> float | None:
        """Seconds to the earliest quiet-timer deadline, or None: nothing running, wait for an event."""
        recs = self._watched()
        if not recs:
            return None
        return max(0.0, min(self.progress(r) for r in recs) + self.stall - self.clock())

    def quiet_timers(self) -> None:
        """At the end of a wait: a step silent past its deadline becomes a `stall` event, and the next pass reaps it."""
        now = self.clock()
        stalled = [r["run_id"] for r in self._watched() if now - self.progress(r) >= self.stall]
        if stalled:
            events.write_event(self.inbox, "stall", "runner", {"run_ids": stalled}, now=now)

    # ---------------------------------------------------------------- the pass
    def run_pass(self, evs: list[dict]) -> list[str]:
        """One pass over a batch of events; their files are deleted once it has committed."""
        for _ in range(3):
            started: list[int] = []
            try:
                transitions = self._pass(evs, started)
                break
            except PushRejected:
                for pid in started:  # the record naming them was not pushed: no step may outlive its record
                    self.engine.kill(pid)
        else:
            raise StaleClone("the record's push was rejected 3 times; the remote moved under every pass")
        self.passes += 1
        if transitions and self.vault:
            self.vault(self.cfg, {"tick": self.led.state().get("tick"), "transitions": transitions})
        for ev in evs:
            try:
                os.unlink(ev["path"])
            except FileNotFoundError:
                pass
        return transitions

    def _pass(self, evs: list[dict], started: list[int]) -> list[str]:
        now = self.clock()
        transitions: list[str] = []
        with self.led.locked("pass"):
            state = self.led.state()
            self.check_lease(state)
            res, judge = self._reconcile(state, self.led.lanes(), evs, now)
            self.led.save_state(state)
            if res["spawned"] or res["checks"]:
                transitions += self.record(self.cfg, self.led, res, now)["transitions"]
            lanes = self.led.lanes()
            n_lanes = int(self.cfg.get("_swarm_lanes", 5))
            if not self.led.state().get("rate_hold") and (not lanes or any(slots.eligible(s, n_lanes) for s in lanes)):
                plan = self.plan(self.cfg, self.led, now)
                todo = (plan.get("spawn") or []) + (plan.get("spec_spawn") or [])
                if todo:
                    self.led.checkpoint(f"pass {plan['tick']}: runs planned as spawning, before their steps start")
                    spawned = [self._start(s, started) for s in todo]
                    transitions += self.record(self.cfg, self.led, {"spawned": spawned}, now)["transitions"]
            if judge:
                self._supervise(judge, now, started)
        return transitions

    def _reconcile(self, state: dict, lanes: list[dict], evs: list[dict], now: float) -> tuple[dict, list[dict]]:
        res: dict = {"spawned": [], "checks": []}
        judge: list[dict] = []
        runs = {s["run"]["run_id"]: s for s in lanes if isinstance(s.get("run"), dict)}
        exits = {(e.get("payload") or {}).get("run_id"): e["payload"] for e in evs if e["kind"] == "step_exit"}
        # A pass lost after its plan: a step found by its run id (or whose exit is waiting) is adopted.
        for rid, s in runs.items():
            if not s["run"].get("started"):
                pid = self.engine.find(rid)
                if pid is not None or rid in exits:
                    res["spawned"].append({"lane_id": s["lane_id"], "run_id": rid, "ok": True, "session_id": rid,
                                           "pid": pid, "log": self._log(rid)})
                else:
                    res["spawned"].append({"lane_id": s["lane_id"], "run_id": rid, "ok": False,
                                           "error": "no step process carries this run id after a restart"})
        sup = state.get("supervisor")
        for rid, p in exits.items():
            if sup and rid == sup["run_id"]:
                self.led.event("supervisor_exited", run_id=rid, exit_code=p.get("exit_code"))
                state["supervisor"] = sup = None
            elif rid in runs:
                check = {"lane_id": runs[rid]["lane_id"], "run_id": rid, "ended": True,
                         "status": "completed" if p.get("exit_code") == 0 else "failed",
                         "branch_pushed": bool(p.get("outcome_branch"))}
                if p.get("pr_url"):
                    check["pr"] = {"url": p["pr_url"]}
                elif p.get("exit_code") != 0:
                    judge.append({"run_id": rid, "why": "step failed", "exit_code": p.get("exit_code"), "log": p.get("log")})
                res["checks"].append(check)
        for e in evs:
            p = e.get("payload") or {}
            if e["kind"] == "rate_limit" and str(p.get("status")) not in OK_STATUSES:
                state["rate_hold"] = {"status": p.get("status"), "window": p.get("window"),
                                      "resets_at": p.get("resets_at"), "since": now, "run_id": p.get("run_id")}
                self.led.event("starts_held", **state["rate_hold"])
            elif e["kind"] == "window_reset" and state.get("rate_hold"):
                self.led.event("starts_resumed", why="window_reset", window=p.get("window"))
                del state["rate_hold"]
        hold = state.get("rate_hold")
        if hold and hold.get("resets_at") and now >= float(hold["resets_at"]):
            self.led.event("starts_resumed", why="the pass is past the recorded reset", resets_at=hold["resets_at"])
            del state["rate_hold"]
        why = f"no progress for {self.stall / 60:g} min: no step exit and its log unchanged"
        for rid, s in runs.items():
            run = s["run"]
            if run.get("started") and rid not in exits and now - self.progress(run) >= self.stall:
                if run.get("pid"):
                    self.engine.kill(int(run["pid"]))
                self.led.event("step_stalled", lane_id=s["lane_id"], run_id=rid, reason=why)
                res["checks"].append({"lane_id": s["lane_id"], "run_id": rid, "ended": True, "status": "failed",
                                      "outcome": "stalled", "reason": why})
                judge.append({"run_id": rid, "why": "stalled", "log": run.get("log")})
        if sup and now - self.progress(sup) >= self.stall:
            self.engine.kill(int(sup["pid"]))
            self.led.event("supervisor_stalled", run_id=sup["run_id"], reason=why)
            state["supervisor"] = None
        return res, judge

    def _log(self, rid: str) -> str:
        return os.path.join(self.work, rid, "step.log")

    def _wrapped(self, rid: str, template: list[str], fields: dict) -> list[str]:
        return [sys.executable, "-m", "metaos_pipeline.step_wrap", "--inbox", self.inbox, "--run-id", rid,
                "--log", self._log(rid), "--", *fill(template, fields)]

    def _start(self, s: dict, started: list[int]) -> dict:
        rid = s["run_id"]
        os.makedirs(os.path.join(self.work, rid), exist_ok=True)
        prompt = os.path.join(self.work, rid, "prompt.md")
        with open(prompt, "w", encoding="utf-8") as fh:
            fh.write(s.get("prompt") or "")
        argv = self._wrapped(rid, self.cfg["step_command"], {
            "prompt_file": prompt, "run_id": rid, "lane_id": s["lane_id"], "repo": s.get("repo") or "",
            "branch": s.get("branch") or "", "item": s.get("item") or s.get("decision") or "", "log": self._log(rid)})
        try:
            pid = self.engine.spawn(argv)
        except OSError as exc:
            return {"lane_id": s["lane_id"], "run_id": rid, "ok": False, "error": str(exc)}
        started.append(pid)
        return {"lane_id": s["lane_id"], "run_id": rid, "ok": True, "session_id": rid, "pid": pid, "log": self._log(rid)}

    def _supervise(self, judge: list[dict], now: float, started: list[int]) -> None:
        """Start the supervisor step for what needs judgement: one at a time, on the instance's engine."""
        state = self.led.state()
        if not self.cfg.get("supervisor_command") or state.get("supervisor"):
            busy = state.get("supervisor")
            self.led.event("needs_judgement", evidence=judge,
                           note=f"the supervisor {busy['run_id']} is running" if busy else "no supervisor_command configured")
            return
        rid = f"sup-{uuid.uuid4().hex[:8]}"
        os.makedirs(os.path.join(self.work, rid), exist_ok=True)
        evidence = os.path.join(self.work, rid, "evidence.json")
        with open(evidence, "w", encoding="utf-8") as fh:
            json.dump({"ts": now, "evidence": judge, "record": self.led.dir}, fh, indent=1)
        argv = self._wrapped(rid, self.cfg["supervisor_command"], {"evidence_file": evidence, "run_id": rid, "record": self.led.dir})
        try:
            pid = self.engine.spawn(argv)
        except OSError as exc:
            self.led.event("supervisor_failed_spawn", run_id=rid, error=str(exc))
            return
        started.append(pid)
        state["supervisor"] = {"run_id": rid, "pid": pid, "log": self._log(rid), "started": now}
        self.led.event("supervisor_started", run_id=rid, evidence=judge)
        self.led.save_state(state)
