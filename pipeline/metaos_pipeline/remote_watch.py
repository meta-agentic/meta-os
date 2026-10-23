"""The remote watcher: the one poll in the design, and it only produces events.

    python3 -m metaos_pipeline.remote_watch --inbox DIR --targets FILE
                                            [--poll-seconds 60] [--state FILE] [--once]

GitHub cannot push to a private machine, so every `--poll-seconds` this asks for each target
with a conditional request (`If-None-Match` and the stored ETag). A `304` costs no rate limit
and writes nothing. A `200` whose value changed (a branch's head SHA; a pull request's head
SHA or `updated_at`) writes one `remote_change` event and stores the new ETag and value. The
first answer for a target counts as a change: at most one pass per target after a restart. An error is reported and retried at the next
poll, never fatal. The watcher never starts a pass and never writes the record.

The targets file is the instance's: a JSON list of `owner/repo@branch` and `owner/repo#n`.
The token comes from `GH_TOKEN`, `GITHUB_TOKEN`, or `gh auth token`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from metaos_pipeline import events

API = "https://api.github.com"
TARGET_RE = re.compile(r"^([\w.-]+)/([\w.-]+)(?:@([\w./-]+)|#(\d+))$")


def parse_targets(items) -> list[dict]:
    if not isinstance(items, list):
        raise ValueError("the targets file must hold a JSON list")
    out = []
    for t in items:
        m = TARGET_RE.match(t) if isinstance(t, str) else None
        if not m:
            raise ValueError(f"bad target {t!r}: expected owner/repo@branch or owner/repo#n")
        owner, repo, branch, pr = m.groups()
        path = (f"/repos/{owner}/{repo}/branches/{urllib.parse.quote(branch, safe='')}" if branch
                else f"/repos/{owner}/{repo}/pulls/{pr}")
        out.append({"target": t, "path": path, "pr": pr is not None})
    return out


def token() -> str | None:
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if tok:
        return tok
    try:
        r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=20)
        return (r.stdout.strip() or None) if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def value_of(body: dict, pr: bool) -> dict:
    if pr:
        return {"sha": (body.get("head") or {}).get("sha"), "updated_at": body.get("updated_at"),
                "state": body.get("state")}
    return {"sha": (body.get("commit") or {}).get("sha")}


def poll_once(targets: list[dict], state: dict, inbox: str, api: str = API,
              tok: str | None = None) -> int:
    """One conditional request per target; returns the number of events written."""
    written = 0
    for t in targets:
        prev = state.get(t["target"]) or {}
        req = urllib.request.Request(api + t["path"], headers={
            "Accept": "application/vnd.github+json", "User-Agent": "meta-os-remote-watch"})
        if prev.get("etag"):
            req.add_header("If-None-Match", prev["etag"])
        if tok:
            req.add_header("Authorization", f"Bearer {tok}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                etag, body = resp.headers.get("ETag"), json.load(resp)
        except urllib.error.HTTPError as exc:
            exc.close()
            if exc.code != 304:
                print(f"remote_watch: {t['target']}: HTTP {exc.code}", file=sys.stderr)
            continue
        except (OSError, ValueError) as exc:
            print(f"remote_watch: {t['target']}: {exc}", file=sys.stderr)
            continue
        val = value_of(body if isinstance(body, dict) else {}, t["pr"])
        if val == prev.get("value"):
            state[t["target"]] = {"etag": etag, "value": val}
            continue
        try:
            events.write_event(inbox, "remote_change", "remote_watch",
                               {"target": t["target"], "previous": prev.get("value"), **val})
        except OSError as exc:  # leave the state alone so the next poll writes it again
            print(f"remote_watch: event for {t['target']} not written: {exc}", file=sys.stderr)
            continue
        state[t["target"]] = {"etag": etag, "value": val}
        written += 1
    return written


def _load(path: str | None) -> dict:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"remote_watch: state {path} unreadable, starting empty: {exc}", file=sys.stderr)
        return {}


def _save(path: str | None, state: dict) -> None:
    if not path:
        return
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except OSError as exc:
        print(f"remote_watch: state not saved: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="metaos_pipeline.remote_watch", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inbox", required=True)
    ap.add_argument("--targets", required=True)
    ap.add_argument("--poll-seconds", type=float, default=60.0)
    ap.add_argument("--state", help="where ETags and values survive a restart")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--api", default=API, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.poll_seconds <= 0:
        ap.error("--poll-seconds must be positive")
    try:
        with open(a.targets, encoding="utf-8") as fh:
            targets = parse_targets(json.load(fh))
    except (OSError, ValueError) as exc:
        ap.error(f"targets: {exc}")
    state, tok = _load(a.state), token()
    while True:
        poll_once(targets, state, a.inbox, a.api, tok)
        _save(a.state, state)
        if a.once:
            return 0
        time.sleep(a.poll_seconds)


if __name__ == "__main__":
    sys.exit(main())
