"""The vault write lock: one advisory lock shared by every writer on this machine.

Whatever commits in the vault (an instance's sweep hook, its backlog tool, this pipeline) works in
one checkout and its worktrees, which share one index, so they used to meet at `.git/index.lock`.
This is the one lock they take instead; the convention is the file name and the place, so a
writer written elsewhere takes the same lock: `flock` on `vault-write.lock` in the repository's COMMON git
directory, which a linked worktree shares with the main checkout, so a writer in a worktree and a
writer in the main checkout serialise. It is held for one write or one commit-and-push, never for
an edit session. Stdlib only.

    with vault_lock(vault, "pipeline vault_commit"):
        ...

The holder writes who it is into the file, so a writer that gives up can say whom it waited for.
The lock is re-entrant inside a process. Never hold it across a subprocess that takes it too (a
tool run for its side effect): that is a deadlock.
"""
from __future__ import annotations

import fcntl
import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

LOCK_NAME = "vault-write.lock"


class Held(Exception):
    """The lock stayed held by someone else for the whole timeout; the message names them."""


_held: dict[str, int] = {}     # lock path -> depth, for re-entrancy inside one process
_fds: dict[str, int] = {}


def lock_path(vault: str | os.PathLike) -> str:
    out = subprocess.run(["git", "-C", str(vault), "rev-parse", "--git-common-dir"],
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise Held(f"{vault} is not a git checkout: {out.stderr.strip()}")
    common = Path(out.stdout.strip())
    if not common.is_absolute():
        common = Path(vault) / common
    return str(common.resolve() / LOCK_NAME)


def holder(path: str) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    return text or "an unknown writer"


@contextmanager
def vault_lock(vault: str | os.PathLike, who: str, timeout: float = 30.0):
    path = lock_path(vault)
    if _held.get(path):
        _held[path] += 1
        try:
            yield path
        finally:
            _held[path] -= 1
        return
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.monotonic() >= deadline:
                who_has = holder(path)
                os.close(fd)
                raise Held(f"the vault write lock is held by {who_has} (waited {timeout:g} s)")
            time.sleep(0.1)
    try:
        os.ftruncate(fd, 0)
        os.write(fd, f"pid {os.getpid()}: {who}, since {time.strftime('%H:%M:%S')}".encode())
        _held[path], _fds[path] = 1, fd
        yield path
    finally:
        _held.pop(path, None)
        _fds.pop(path, None)
        try:
            os.ftruncate(fd, 0)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
