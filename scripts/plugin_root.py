#!/usr/bin/env python3
"""Print the root of an installed Claude Code plugin, for `scripts/packs.sh config`.

    python3 scripts/plugin_root.py meta-discipline-agile@meta-agentic

A pack installed as a plugin has no mount, so its `pack.yaml` (the config schema and the
defaults) lives where Claude Code installed the plugin. Looked up in this order:

  1. `$CLAUDE_PLUGIN_ROOT`, when it is this plugin from this marketplace — its
     `.claude-plugin/plugin.json` names the plugin and it sits in the cache layout
     `<marketplace>/<plugin>/<version>/`; set inside the plugin's own context;
  2. `<config dir>/plugins/installed_plugins.json` (config dir: `$CLAUDE_CONFIG_DIR`, else
     `~/.claude`), whose entry for `<plugin>@<marketplace>` names the active `installPath`
     (under `plugins/cache/<marketplace>/<plugin>/<version>/`). An install scoped to a
     project counts only when its `projectPath` is the current directory; a user install
     counts everywhere, and the project's own install wins over it.

Found: the root is printed on stdout. Not found: nothing on stdout, one line on stderr saying
why (not installed, recorded where nothing is, or an unreadable record), exit 0 either way —
the caller decides what that means. Only a root holding a `pack.yaml` counts as found.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def plugin_name_of(root: Path) -> str | None:
    try:
        return json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")).get("name")
    except (OSError, ValueError, AttributeError):
        return None


def installed_root(plugin_id: str, project: Path) -> tuple[Path | None, str]:
    """(the plugin's root, or None and the reason it was not found)."""
    name, marketplace = plugin_id.split("@", 1)
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        root = Path(env)
        if (plugin_name_of(root) == name and root.parent.parent.name == marketplace
                and (root / "pack.yaml").is_file()):
            return root, ""
    record = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "plugins" / "installed_plugins.json"
    try:
        entries = json.loads(record.read_text(encoding="utf-8"))["plugins"].get(plugin_id)
    except OSError:
        return None, "not installed here"
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        return None, f"unreadable {record.name} ({type(e).__name__})"
    if entries is None:
        return None, "not installed here"
    ranked: list[tuple[int, Path]] = []
    malformed = 0                       # a bad entry is skipped, not allowed to void a good one
    for e in entries if isinstance(entries, list) else [entries]:
        at = e.get("projectPath") if isinstance(e, dict) else None
        if not isinstance(e, dict) or not isinstance(e.get("installPath"), str) or not e["installPath"] \
                or not (at is None or (isinstance(at, str) and at)):
            malformed += 1
            continue
        try:
            if at is None:
                ranked.append((1, Path(e["installPath"])))
            elif Path(at).resolve() == project:
                ranked.append((0, Path(e["installPath"])))
        except (OSError, ValueError):   # e.g. a NUL in a path
            malformed += 1
    if not ranked:
        return None, f"malformed entry for it in {record.name}" if malformed else "not installed for this project"
    for _, root in sorted(ranked, key=lambda r: r[0]):
        if (root / "pack.yaml").is_file():
            return root, ""
    return None, f"not found at its recorded installPath {sorted(ranked, key=lambda r: r[0])[0][1]}"


def main() -> None:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        sys.exit("usage: plugin_root.py <plugin>@<marketplace>")
    root, why = installed_root(sys.argv[1], Path.cwd().resolve())
    if root:
        print(root)
    else:
        print(why, file=sys.stderr)


if __name__ == "__main__":
    main()
