"""What the pack registry says each pack ships, what a mounted pack really ships, and the
catalog rows that rely on both.

A pack reaches a checkout in more than one way: as a submodule mount (`scripts/packs.sh add`,
which links its skills into `skills/`) or as a Claude Code plugin from the marketplace, which
leaves nothing in the tree at all. The framework gate cannot see the second, and should not
have to: the registry (`systems/packs.yaml`) is the curated statement of what a pack provides,
so a catalogued skill a registered pack provides is resolved by that statement when the pack
is not mounted. A mounted pack answers for itself, from its own tree — not from the links in
`skills/`, which are local, excluded from git, and absent until `packs.sh sync` runs.

"Mounted" means a mount with content. An uninitialised submodule is an empty `.packs/<pack>/`
— what every CI checkout without `submodules:` holds — and counts as not mounted.

Only a pack that can be installed today counts. `status: planned` is refused by
`scripts/packs.sh add` (the repository may carry nothing yet), and any status this module does
not know is treated the same way: a registry entry that cannot be installed provides nothing.

Every reader fails closed: whatever it cannot read is returned as a problem for the gate to
report, never skipped quietly. Problems name no local path: they may reach a tracked file.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

INSTALLABLE = frozenset({"available"})
PACK_TABLE_HEADING = "## pack-provided"           # compared lower-cased, as a prefix
NAME_CELL = re.compile(r"`([a-z0-9][a-z0-9-]*)`")
PLUGIN_CELL = re.compile(r"`[A-Za-z0-9._-]+@[A-Za-z0-9._-]+`")
SEPARATOR_CELL = re.compile(r":?-+:?")


def provided_skills(registry: Path) -> tuple[dict[str, str], list[str]]:
    """(skill name -> the installable pack that provides it, problems reading the registry)."""
    try:
        data = yaml.safe_load(registry.read_text(encoding="utf-8"))
    except OSError as e:
        return {}, [f"registry unreadable — {e.strerror or type(e).__name__}"]
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        at = f" at line {mark.line + 1}" if mark else ""
        return {}, [f"registry unparseable — {getattr(e, 'problem', None) or type(e).__name__}{at}"]
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


def mounted_packs(packs_dir: Path) -> dict[str, set[str]]:
    """Each mount with content under `.packs/` -> the skill names it ships.

    Discovered as `scripts/packs.sh` (pack_skill_dirs) discovers them: the `./…` paths of
    `.claude-plugin/plugin.json` when the pack has one, otherwise every `SKILL.md` at any depth.
    """
    out: dict[str, set[str]] = {}
    for d in sorted(packs_dir.iterdir()) if packs_dir.is_dir() else []:
        if not d.is_dir() or not any(d.iterdir()):
            continue
        manifest = d / ".claude-plugin" / "plugin.json"
        if manifest.is_file():
            rels = re.findall(r'"\./([^"]*)"', manifest.read_text(encoding="utf-8", errors="replace"))
            out[d.name] = {Path(r).name for r in rels if (d / r / "SKILL.md").is_file()}
        else:
            out[d.name] = {f.parent.name for f in d.rglob("SKILL.md") if ".git" not in f.relative_to(d).parts}
    return out


def _row_like(line: str) -> bool:
    """A line that reads as a table row once wikilinks and escaped pipes are set aside."""
    bare = re.sub(r"\[\[[^\]]*\]\]", "", line).replace("\\|", "")
    return bare.count("|") >= 2


def pack_table(text: str) -> tuple[set[str], list[str]]:
    """(names in the catalog's `## Pack-provided` table, problems with that table).

    A row there is one skill: its first cell is exactly one backticked name, and the row is a
    real table row (a leading `|` at column 0). Anything row-like there that is not is a
    problem. Outside that heading, a row of a table with a Plugin column naming a
    `<plugin>@<marketplace>` is a pack row whose heading went missing — also a problem. A row
    the gate cannot read is a row it cannot check.
    """
    names: set[str] = set()
    problems: list[str] = []
    in_section, header = False, None
    for line in text.splitlines():
        if line.startswith("## "):
            in_section, header = line.lower().startswith(PACK_TABLE_HEADING), None
            continue
        if not line.startswith("|"):
            header = None
            if in_section and _row_like(line):
                problems.append(f"pack-provided row {line.strip()!r} is not a table row "
                                f"(indented, or no leading pipe)")
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:                                   # a table's first row is its header
            header = [c.lower() for c in cells]
            continue
        if all(SEPARATOR_CELL.fullmatch(c) for c in cells):
            continue
        if not in_section:
            col = header.index("plugin") if "plugin" in header else None
            if col is not None and col < len(cells) and PLUGIN_CELL.search(cells[col]):
                problems.append(f"pack row {cells[0]!r} sits outside a `## Pack-provided` table")
            continue
        m = NAME_CELL.fullmatch(cells[0])
        if m:
            names.add(m.group(1))
        else:
            problems.append(f"pack-provided row {cells[0]!r} does not start with one backticked skill name")
    return names, problems
