#!/usr/bin/env python3
"""Pre-flight: refuse an unattended start if any step's command could ask for approval.

    preflight.py --dir DIR --commands FILE [--permission-mode MODE] [--user-settings FILE]

A prompt nobody sees is a stall, so before an unattended run starts this reads the Claude
Code permission settings a session started in DIR would get (user `~/.claude/settings.json`,
then DIR's `.claude/settings.json` and `.claude/settings.local.json`; the later file's
`defaultMode` wins, the `allow`, `ask` and `deny` lists add up) and checks every command
template in FILE, one per line (`#` comments and blank lines skipped). `--permission-mode`
overrides the mode, as `claude --permission-mode` does.

A command needs approval when a deny or ask rule matches it, when it is a compound or `cd`
command (operators, substitutions or redirections, which rules cannot cover), or when no
allow rule matches it. Rules follow Claude Code's documented forms: `Bash` or `Bash(*)` (any
command), `Bash(prefix:*)` (the prefix, alone or followed by arguments), and `Bash(pattern)`
where `*` matches anything (otherwise exact). The check is conservative: what it cannot
read is reported as needing approval. Under `bypassPermissions` it passes with a caveat, and
names the commands that may still prompt.

Not covered: managed (enterprise) settings, non-Bash tools, and hooks that ask.

Exit: 0 every command runs without approval, 1 at least one could ask (each named, with why),
2 a usage error or unreadable settings.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

MODES = ("default", "acceptEdits", "plan", "bypassPermissions", "dontAsk", "auto")
BYPASS_CAVEAT = ("caveat: under bypassPermissions an approval prompt can still occur (some compound "
                 "commands ask anyway) and may not reach a remote-control client, so any step that "
                 "would prompt is a silent stall")


def load_settings(paths: list[str]) -> tuple[str | None, dict[str, list[str]]]:
    mode, rules = None, {"allow": [], "ask": [], "deny": []}
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"preflight: cannot read {path}: {exc}")
        perms = data.get("permissions") or {} if isinstance(data, dict) else {}
        if not isinstance(perms, dict):
            raise SystemExit(f"preflight: {path}: permissions is not an object")
        mode = perms.get("defaultMode") or mode
        for kind in rules:
            value = perms.get(kind) or []
            if not isinstance(value, list) or not all(isinstance(r, str) for r in value):
                raise SystemExit(f"preflight: {path}: permissions.{kind} is not a list of strings")
            rules[kind] += value
    return mode, rules


def compound_reason(cmd: str) -> str | None:
    """Why rules cannot cover this command, or None. Quote-aware; unsure means compound."""
    if re.match(r"\s*cd(\s|$)", cmd):
        return "a cd command: rules cannot cover what runs after it"
    if re.match(r"\s*[A-Za-z_][A-Za-z0-9_]*=", cmd):
        return "a leading variable assignment: rules match the command name, not this"
    quote = None
    i = 0
    while i < len(cmd):
        c, pair = cmd[i], cmd[i:i + 2]
        if quote == "'":
            quote = None if c == "'" else quote
        elif c == "\\":
            i += 1
        elif pair == "$(" or c == "`":
            return "a command substitution"
        elif quote == '"':
            quote = None if c == '"' else quote
        elif c in "'\"":
            quote = c
        elif pair in ("&&", "||") or c in ";|&\n":
            return f"a compound command ({pair if pair in ('&&', '||') else repr(c)})"
        elif c in "<>":
            return "a redirection"
        i += 1
    if quote:
        return "an unterminated quote"
    return None


def rule_matches(rule: str, cmd: str) -> bool:
    """Does a permission rule match this (single, non-compound) Bash command?"""
    if rule in ("Bash", "Bash(*)"):
        return True
    m = re.fullmatch(r"Bash\((.*)\)", rule, re.S)
    if not m:
        return False                                # another tool's rule
    spec, cmd = m.group(1).strip(), cmd.strip()
    if spec.endswith(":*"):
        prefix = spec[:-2]
        return cmd == prefix or cmd.startswith(prefix + " ")
    if "*" in spec:
        pattern = ".*".join(re.escape(part) for part in spec.split("*"))
        return re.fullmatch(pattern, cmd, re.S) is not None
    return cmd == spec


def check(cmd: str, mode: str, rules: dict[str, list[str]]) -> str | None:
    """None if the command runs without asking, else why it could ask (or be refused)."""
    for kind in ("deny", "ask"):
        hit = next((r for r in rules[kind] if rule_matches(r, cmd)), None)
        if hit:
            return f"matched {kind} rule {hit}"
    if mode == "plan":
        return "plan mode runs no commands"
    reason = compound_reason(cmd)
    if reason:
        return reason
    if any(rule_matches(r, cmd) for r in rules["allow"]):
        return None
    return "refused: no allow rule matches (dontAsk)" if mode == "dontAsk" else "no allow rule matches"


def read_commands(path: str) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        return [ln.strip() for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", required=True, help="the directory the unattended session starts in")
    ap.add_argument("--commands", required=True, help="file of command templates, one per line")
    ap.add_argument("--permission-mode", choices=MODES, help="overrides every settings file")
    ap.add_argument("--user-settings", default=os.path.expanduser("~/.claude/settings.json"))
    args = ap.parse_args(argv)
    try:
        commands = read_commands(args.commands)
    except OSError as exc:
        print(f"preflight: cannot read {args.commands}: {exc}", file=sys.stderr)
        return 2
    claude = os.path.join(args.dir, ".claude")
    try:
        mode, rules = load_settings([args.user_settings, os.path.join(claude, "settings.json"),
                                     os.path.join(claude, "settings.local.json")])
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2
    mode = args.permission_mode or mode or "default"
    if mode not in MODES:
        print(f"preflight: unknown permission mode {mode!r}: treated as default", file=sys.stderr)
        mode = "default"
    findings = [(c, r) for c in commands if (r := check(c, "default" if mode == "bypassPermissions" else mode, rules))]
    if mode == "bypassPermissions":
        print(f"preflight: pass (bypassPermissions, {len(commands)} commands); {BYPASS_CAVEAT}")
        for cmd, why in findings:
            print(f"  may still prompt or be refused: {cmd}  ({why})")
        return 0
    for cmd, why in findings:
        print(f"NEEDS APPROVAL: {cmd}  ({why})")
    if findings:
        print(f"preflight: refused ({len(findings)} of {len(commands)} commands could ask; mode {mode})")
        return 1
    print(f"preflight: pass ({len(commands)} commands; mode {mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
