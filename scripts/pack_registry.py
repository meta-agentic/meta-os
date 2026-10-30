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


def _norm_url(url: str) -> str:
    return re.sub(r"\.git$", "", url.rstrip("/")).replace("git@github.com:", "https://github.com/")


def _plain_path(path: object) -> str | None:
    """The shell's rule (packs.sh pack_subpath): a relative directory, no `..`, no empty segment."""
    if not isinstance(path, str):
        return None
    sub = path.strip("/")
    if sub and (any(seg in ("", "..") for seg in sub.split("/"))):
        return None
    return sub or None


def _mount_urls(gitmodules: Path | None) -> dict[str, str]:
    """`.packs/<name>` -> the url its submodule was added from, from a .gitmodules file."""
    if gitmodules is None or not gitmodules.is_file():
        return {}
    out: dict[str, str] = {}
    for block in re.split(r"(?m)^\[submodule ", gitmodules.read_text(encoding="utf-8", errors="replace"))[1:]:
        path = re.search(r"(?m)^\s*path\s*=\s*(\S+)", block)
        url = re.search(r"(?m)^\s*url\s*=\s*(\S+)", block)
        if path and url:
            out[path.group(1)] = url.group(1)
    return out


def registry_paths(registry: Path, manifest: Path | None = None,
                   gitmodules: Path | None = None) -> tuple[dict[str, str], list[str]]:
    """Each pack key -> the pack's directory inside its mount, and the problems with a path.

    As `packs.sh` reads it: the manifest's `path:` wins; otherwise the registry's applies, to the
    key and to each key it used to have (`renamed-from:`), unless the mount was made from another
    repository than the registry's (an instance mounted before the monorepo): then it is the whole
    pack. A path with `..` or an empty segment is a problem and gives no entry. A registry that
    cannot be read yields nothing here: `provided_skills` reports that.
    """
    problems: list[str] = []
    try:
        packs = (yaml.safe_load(registry.read_text(encoding="utf-8")) or {}).get("packs")
    except (OSError, yaml.YAMLError, AttributeError):
        return {}, problems
    declared: dict[str, str] = {}
    if manifest is not None and manifest.is_file():
        try:
            mp = (yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}).get("packs") or {}
        except (OSError, yaml.YAMLError, AttributeError):
            mp = {}
        for name, entry in (mp.items() if isinstance(mp, dict) else []):
            if isinstance(entry, dict) and entry.get("path") is not None:
                declared[str(name)] = entry["path"]
    urls = _mount_urls(gitmodules)
    out: dict[str, str] = {}
    bad: set[str] = set()
    for name, raw in declared.items():
        sub = _plain_path(raw)
        if sub is None:
            problems.append(f"pack {name!r}: path {raw!r} must be a plain relative directory")
            bad.add(name)
        else:
            out[name] = sub
    for pack, entry in (packs.items() if isinstance(packs, dict) else []):
        if not isinstance(entry, dict) or entry.get("path") is None:
            continue
        sub = _plain_path(entry["path"])
        if sub is None:
            problems.append(f"pack {pack!r}: registry path {entry['path']!r} must be a plain relative directory")
            continue
        for key in [str(pack), *(str(k) for k in entry.get("renamed-from") or [])]:
            if key in out or key in bad:
                continue                                       # the manifest's own path wins
            src = urls.get(f".packs/{key}")
            if src is not None and _norm_url(src) != _norm_url(str(entry.get("repo") or "")):
                continue                                       # mounted from another repository: the whole pack
            out[key] = sub
    return out, problems


def mounted_packs(packs_dir: Path, subpaths: dict[str, str] | None = None) -> dict[str, set[str]]:
    """Each mount with content under `.packs/` -> the skill names it ships.

    Discovered as `scripts/packs.sh` (pack_skill_dirs) discovers them: the `./…` paths of
    `.claude-plugin/plugin.json` when the pack has one, otherwise every `SKILL.md` at any depth.
    A pack that lives in a subdirectory of its repository (`subpaths`, from `registry_paths`) is
    read from that directory, never from the whole mount: a sibling pack's skills are not its own.
    """
    out: dict[str, set[str]] = {}
    for d in sorted(packs_dir.iterdir()) if packs_dir.is_dir() else []:
        if not d.is_dir() or not any(d.iterdir()):
            continue
        root = d / (subpaths or {}).get(d.name, "")
        if not root.is_dir():
            out[d.name] = set()
            continue
        manifest = root / ".claude-plugin" / "plugin.json"
        if manifest.is_file():
            rels = re.findall(r'"\./([^"]*)"', manifest.read_text(encoding="utf-8", errors="replace"))
            out[d.name] = {Path(r).name for r in rels if (root / r / "SKILL.md").is_file()}
        else:
            out[d.name] = {f.parent.name for f in root.rglob("SKILL.md") if ".git" not in f.relative_to(root).parts}
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
