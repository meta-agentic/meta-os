"""What the pack registry says each pack ships — the `provides:` lists of `systems/packs.yaml`.

A pack reaches a checkout in more than one way: as a submodule mount (`scripts/packs.sh add`,
which links its skills into `skills/`) or as a Claude Code plugin from the marketplace, which
leaves nothing in the tree at all. The framework gate cannot see the second, and should not
have to: the registry is the curated statement of what a pack provides, so a catalogued skill
a registered pack provides is resolved by that statement, whichever way the pack arrives.

Only a pack that can be installed today counts. `status: planned` is refused by
`scripts/packs.sh add` (the repository may carry nothing yet), and any status this module does
not know is treated the same way: a registry entry that cannot be installed provides nothing.
"""
from __future__ import annotations

from pathlib import Path

import yaml

INSTALLABLE = frozenset({"available"})


def provided_skills(registry: Path) -> dict[str, str]:
    """Skill name -> the registry name of the installable pack that provides it.

    Empty when the registry is absent or unreadable: then nothing is pack-provided, and the
    gate falls back to what it can see on disk.
    """
    try:
        data = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    packs = data.get("packs") if isinstance(data, dict) else None
    out: dict[str, str] = {}
    for pack, entry in (packs or {}).items():
        if not isinstance(entry, dict) or entry.get("status") not in INSTALLABLE:
            continue
        for skill in entry.get("provides") or []:
            out.setdefault(str(skill), str(pack))
    return out
