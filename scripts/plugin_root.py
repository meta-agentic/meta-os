#!/usr/bin/env python3
"""Print the root of an installed Claude Code plugin, for `scripts/packs.sh config`.

    python3 scripts/plugin_root.py meta-discipline-agile@meta-agentic

A pack installed as a plugin has no mount, so its `pack.yaml` (the config schema and the
defaults) lives where Claude Code installed the plugin. Looked up in this order:

  1. `$CLAUDE_PLUGIN_ROOT`, when it is this plugin — set inside the plugin's own context;
  2. `<config dir>/plugins/installed_plugins.json` (config dir: `$CLAUDE_CONFIG_DIR`, else
     `~/.claude`), whose entry for `<plugin>@<marketplace>` names the active `installPath`
     (under `plugins/cache/<marketplace>/<plugin>/<version>/`). An install scoped to a
     project counts only for that project, the current directory; a user install counts
     everywhere, and the project's own install wins over it.

Prints nothing and exits 0 when the plugin is not installed: the caller decides what that
means. Only an installed root holding a `pack.yaml` is printed.
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


def installed_root(plugin_id: str, project: Path) -> Path | None:
    name = plugin_id.split("@", 1)[0]
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env and plugin_name_of(Path(env)) == name and (Path(env) / "pack.yaml").is_file():
        return Path(env)
    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    try:
        data = json.loads((config_dir / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        entries = data["plugins"][plugin_id]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    ranked = []
    for e in entries if isinstance(entries, list) else []:
        if not isinstance(e, dict) or not e.get("installPath"):
            continue
        at = e.get("projectPath")
        if at is None:
            ranked.append((1, Path(e["installPath"])))
        elif Path(at).resolve() == project:
            ranked.append((0, Path(e["installPath"])))
    for _, root in sorted(ranked, key=lambda r: r[0]):
        if (root / "pack.yaml").is_file():
            return root
    return None


def main() -> None:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        sys.exit("usage: plugin_root.py <plugin>@<marketplace>")
    root = installed_root(sys.argv[1], Path.cwd().resolve())
    if root:
        print(root)


if __name__ == "__main__":
    main()
