"""What the pack registry says each pack ships, and the catalog rows that rely on it.

A pack reaches a checkout in more than one way: as a submodule mount (`scripts/packs.sh add`,
which links its skills into `skills/`) or as a Claude Code plugin from the marketplace, which
leaves nothing in the tree at all. The framework gate cannot see the second, and should not
have to: the registry (`systems/packs.yaml`) is the curated statement of what a pack provides,
so a catalogued skill a registered pack provides is resolved by that statement when the pack
is not mounted. A mounted pack answers for itself, through its links.

Only a pack that can be installed today counts. `status: planned` is refused by
`scripts/packs.sh add` (the repository may carry nothing yet), and any status this module does
not know is treated the same way: a registry entry that cannot be installed provides nothing.

Both readers fail closed: whatever they cannot read is returned as a problem for the gate to
report, never skipped quietly.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

INSTALLABLE = frozenset({"available"})
PACK_TABLE_HEADING = "## pack-provided"           # compared lower-cased, as a prefix
NAME_CELL = re.compile(r"`([a-z0-9][a-z0-9-]*)`")
PLUGIN_CELL = re.compile(r"`[A-Za-z0-9._-]+@[A-Za-z0-9._-]+`")


def provided_skills(registry: Path) -> tuple[dict[str, str], list[str]]:
    """(skill name -> the installable pack that provides it, problems reading the registry)."""
    try:
        data = yaml.safe_load(registry.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        return {}, [f"registry unreadable — {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"]
    packs = data.get("packs") if isinstance(data, dict) else None
    if not isinstance(packs, dict):
        return {}, ["registry has no `packs:` mapping"]
    out: dict[str, str] = {}
    problems: list[str] = []
    for pack, entry in packs.items():
        if not isinstance(entry, dict):
            problems.append(f"pack {pack!r} is not a mapping")
            continue
        provides = entry.get("provides") or []
        if not isinstance(provides, list):
            problems.append(f"pack {pack!r}: `provides:` must be a list, not {type(provides).__name__}")
            continue
        if entry.get("status") in INSTALLABLE:
            for skill in provides:
                out.setdefault(str(skill), str(pack))
    return out, problems


def pack_table(text: str) -> tuple[set[str], list[str]]:
    """(names in the catalog's `## Pack-provided` table, problems with that table).

    A row there is one skill: its first cell is exactly one backticked name. A row anywhere
    else that names a plugin (`<plugin>@<marketplace>`) is a pack row whose heading went
    missing; both are problems, because a row the gate cannot read is a row it cannot check.
    """
    names: set[str] = set()
    problems: list[str] = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_table = line.lower().startswith(PACK_TABLE_HEADING)
            continue
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if set(cells[0]) <= set("-: ") or cells[0].lower() == "skill":   # separator, header
            continue
        if not in_table:
            if any(PLUGIN_CELL.search(c) for c in cells):
                problems.append(f"pack row {cells[0]!r} sits outside a `## Pack-provided` table")
            continue
        m = NAME_CELL.fullmatch(cells[0])
        if m:
            names.add(m.group(1))
        else:
            problems.append(f"pack-provided row {cells[0]!r} does not start with one backticked skill name")
    return names, problems
