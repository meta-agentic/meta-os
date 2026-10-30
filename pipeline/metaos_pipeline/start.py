"""The proven start: an unattended start reports *started* only once four things have been seen.

* **runner**: a runner holds the lease, took it after the start began, and its process is alive;
* **sentinel**: the sentinel's job is loaded in the service manager;
* **step**: a lane step started after the start began and its process is alive;
* **progress**: that step's log was written after the step started (the runner's own measure of
  progress: its start, its heartbeat, its log's mtime).

Each proof is cited (process or job, run id, event or log file, time). A proof older than the start
is not one: what an earlier run left in the record proves nothing about this start. Until all four
are seen the report says *not started* and names each missing one; the start command's own exit
never decides it, because the command only asks a service manager to begin.

The order is fixed: the pre-flight (`preflight.py`) first, and a refusal stops the start with its
reason before anything is launched. The launch command is started and not waited for (a launch that
stays in the foreground cannot hold the verdict back). The wait after it is bounded and declared: it
looks every `look` seconds for at most `deadline` seconds, once per start, and then reports. The
verdict is said before it is recorded, and a record that cannot be written is said too.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from typing import Callable

from .ledger import LedgerError

PROOFS = ("runner", "sentinel", "step", "progress")


def _stamp(t: float | None) -> str:
    return "?" if t is None else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def observe(led, *, since: float, engine, sentinel: Callable[[], dict | None], host: str,
            clock: Callable[[], float] = time.time) -> dict[str, dict | None]:
    """Look once: for each proof, its citation, or None when it is not (yet) seen. Writes nothing."""
    state = led.state()
    loop = state.get("loop") or {}
    out: dict[str, dict | None] = dict.fromkeys(PROOFS)
    pid = loop.get("pid")
    if (loop.get("holder") and pid and loop.get("host") == host and float(loop.get("started") or 0) >= since
            and engine.runner_alive(int(pid))):
        out["runner"] = {"process": f"pid {pid} on {host}", "holder": loop["holder"], "epoch": loop.get("epoch"),
                         "at": loop["started"], "file": led.events_path}
    job = sentinel()
    if job:
        out["sentinel"] = {"job": job["job"], "at": job.get("at") or clock(), "file": job.get("file")}
    runs = [s["run"] for s in led.lanes() if isinstance(s.get("run"), dict)]
    steps = [r for r in runs if r.get("started") and float(r["started"]) >= since and r.get("pid")
             and engine.find(r["run_id"]) is not None]
    if steps:
        r = steps[0]
        out["step"] = {"run_id": r["run_id"], "process": f"pid {r['pid']}", "at": r["started"], "file": r.get("log")}
    for r in steps:
        try:
            st = os.stat(r["log"])
        except (KeyError, TypeError, OSError):
            continue
        if st.st_size > 0 and st.st_mtime >= max(since, float(r["started"])):
            out["progress"] = {"run_id": r["run_id"], "file": r["log"], "bytes": st.st_size, "at": st.st_mtime}
            break
    return out


def report(proofs: dict[str, dict | None]) -> dict:
    """The verdict from the four proofs: started only when none is missing, each missing one named."""
    missing = [p for p in PROOFS if not proofs.get(p)]
    return {"started": not missing, "missing": missing, "proofs": {p: proofs.get(p) for p in PROOFS}}


def render(rep: dict) -> str:
    if rep.get("refused"):
        return f"NOT STARTED: the pre-flight refused: {rep['refused']}"
    lines = []
    for p in PROOFS:
        c = rep["proofs"].get(p)
        if not c:
            lines.append(f"  {p}: NOT SEEN")
            continue
        what = c.get("process") or c.get("job")
        extra = f", run {c['run_id']}" if c.get("run_id") else ""
        extra += f", file {c['file']}" if c.get("file") else ""
        lines.append(f"  {p}: seen {what}{extra}, at {_stamp(c.get('at'))}")
    head = "STARTED" if rep["started"] else f"NOT STARTED: missing {', '.join(rep['missing'])}"
    return "\n".join([head, *lines])


def start(led, *, preflight: Callable[[], tuple[int, str]], launch: Callable[[], object],
          look: Callable[[float], dict[str, dict | None]], wait: Callable[[float], None],
          clock: Callable[[], float] = time.time, deadline: float = 120.0, every: float = 5.0,
          say: Callable[[str], None] = lambda text: None) -> dict:
    """Pre-flight, launch, then look until the four proofs are seen or `deadline` seconds have passed.

    `look(since)` is `observe` bound to the instance's engine and sentinel probe. `launch()` starts
    the command and returns at once with its exit code or a handle with `poll()` (None while it
    runs). The verdict goes to `say` first, then to the record as a `start_proven`,
    `start_not_proven` or `start_refused` event; a record that cannot be written is said too.
    """
    rc, text = preflight()
    if rc != 0:
        rep = {"started": False, "refused": text.strip() or f"exit {rc}", "missing": list(PROOFS), "proofs": {}}
        return _conclude(led, "start_refused", rep, say)
    since = clock()
    handle = launch()
    end = since + deadline
    while True:
        rep = report(look(since))
        if rep["started"] or clock() >= end:
            break
        wait(min(every, max(0.0, end - clock())))
    rep["launch_exit"] = handle.poll() if hasattr(handle, "poll") else handle
    return _conclude(led, "start_proven" if rep["started"] else "start_not_proven", rep, say)


def _conclude(led, kind: str, rep: dict, say: Callable[[str], None]) -> dict:
    say(render(rep))
    try:
        led.replay(lambda: _record(led, kind, rep))
    except LedgerError as exc:
        rep["not_recorded"] = str(exc)
        say(f"the verdict above could not be recorded: {exc}")
    return rep


def _record(led, kind: str, rep: dict) -> None:
    with led.locked("start"):
        led.event(kind, **{k: rep[k] for k in rep if k != "text"})


def _watched(text: str) -> list[str]:
    """The paths a launchd job watches, from `launchctl print`'s `watch paths = { ... }` block; [] when absent."""
    m = re.search(r"watch paths = \{([^}]*)\}", text)
    return [ln.strip() for ln in m.group(1).splitlines() if ln.strip()] if m else []


def _same(a: str, b: str) -> bool:
    return os.path.realpath(a) == os.path.realpath(b)


def service_job(label: str, inbox: str | None = None, run: Callable = subprocess.run, platform: str = sys.platform,
                uid: int | None = None) -> Callable[[], dict | None]:
    """A probe for `observe`: the service manager's own answer whether `label` is loaded. Read-only.

    When the manager also shows the job's file and the paths it watches, the file is cited and the
    job counts only if it watches `inbox` (a sentinel for another inbox is not this run's); when it
    shows no watch paths, the loaded job is the minimum.
    """
    def ask(argv: list[str]):
        try:
            return run(argv, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None

    def probe() -> dict | None:
        if platform == "darwin":
            r = ask(["launchctl", "print", f"gui/{os.getuid() if uid is None else uid}/{label}"])
            if r is None or r.returncode != 0:
                return None
            out = r.stdout or ""
            m = re.search(r"^\s*path = (.+)$", out, re.M)
            file, watched = (m.group(1).strip() if m else None), _watched(out)
        else:
            r = ask(["systemctl", "--user", "is-active", "--quiet", label])
            if r is None or r.returncode != 0:
                return None
            show = ask(["systemctl", "--user", "show", "-p", "FragmentPath", "-p", "PathChanged", "-p", "PathModified",
                        "-p", "DirectoryNotEmpty", label])
            props = dict(ln.split("=", 1) for ln in (show.stdout or "").splitlines() if "=" in ln) if show else {}
            file = props.get("FragmentPath") or None
            watched = [v for k, v in props.items() if k != "FragmentPath" and v]
        if inbox and watched and not any(_same(w, inbox) for w in watched):
            return None
        return {"job": label, "at": time.time(), "file": file}
    return probe
