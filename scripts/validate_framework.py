#!/usr/bin/env python3
"""Framework self-check for meta-os — the gate this repo applies to itself.

meta-os is the *public* artifact of the estate: the skill library, the operating
model, the conventions. It states invariants about itself in `CLAUDE.md`,
`PROVENANCE.md`, `README.md` and the `_index.md` files, and until now nothing
checked that those statements were true. This script is that check.

Self-contained on purpose, and deliberately shaped like the vault's own
`scripts/validate_items.py` — same `front_matter()` helper, same error
accumulation, same exit convention — so one gate reads like the other across the
estate. Wired as .githooks/pre-commit; enable once per clone with:

    git config core.hooksPath .githooks

Severity model
--------------
The repo has real, pre-existing debt (a stale skill catalog, most of it). Failing
the whole gate on day one would just get the hook disabled, so:

  * a finding recorded in `scripts/framework-baseline.txt` is a **WARN** —
    known debt, already on the books;
  * anything else is an **ERROR** — a change introduced it;
  * `--strict` promotes every WARN to an ERROR (use in a cleanup pass);
  * `--update-baseline` re-records the current debt.

That makes the baseline a ratchet: existing debt is tolerated, new debt is not,
and debt that gets paid off can never quietly come back (removing its baseline
line is a reviewable diff). Two classes opt out of the ratchet entirely — see
`BASELINEABLE` below.

Framework paths, instance paths
-------------------------------
Since the instance template was folded in (`systems/distribution.md`), a
checkout is either the framework itself or a bootstrapped *instance* of it —
a private repository holding the framework's tree, with the instance's files
added at paths the framework never tracks. This gate therefore scopes itself to the framework's own paths
and refuses, in the framework, any tracked file at an instance path. The
instance paths are not a hand-kept list: they are read from
`instance-template/root/`, the payload `scripts/bootstrap.sh` instantiates.

Inside an instance, "the framework's own paths" is read from git, not guessed:
it is the tree of the framework commit last merged here (the merge base with
`$META_OS_FRAMEWORK_REF`, default `upstream/main`). An instance may add files
anywhere — a top-level folder of its own, a workflow beside the framework's in
`.github/workflows/` — and none of them is the framework's to judge. Without that
ref (no `upstream` remote yet) the scope falls back to "everything but the
template's instance paths", and the gate says so.
"""
from __future__ import annotations

import argparse
import functools
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    sys.exit("PyYAML required: pip3 install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
SKILLS_INDEX = SKILLS_DIR / "_index.md"
PROVENANCE = ROOT / "PROVENANCE.md"
SYSTEMS_DIR = ROOT / "systems"
ONTOLOGY = SYSTEMS_DIR / "ontology.yaml"
PACKS_REGISTRY = SYSTEMS_DIR / "packs.yaml"
PACKS_DIR = ROOT / ".packs"
BASELINE = ROOT / "scripts" / "framework-baseline.txt"

INDEX_NAME = "_index.md"
SKILL_NAME = "SKILL.md"

# ---------------------------------------------------------------------------
# Instance paths — derived, not declared. Every top-level entry of the instance
# template's payload lands at the same path under the repository root when an
# instance is bootstrapped, and from then on that path is the instance's. The
# framework may not track one; the gate may not judge one. Two paths the payload
# does not carry but the mount mechanism creates are added explicitly: the pack
# mounts and the submodule manifest `git submodule add` writes.
# ---------------------------------------------------------------------------
INSTANCE_TEMPLATE_ROOT = ROOT / "instance-template" / "root"
INSTANCE_ONLY_EXTRA = frozenset({".packs", ".gitmodules"})


def instance_paths() -> frozenset[str]:
    """Top-level names owned by an instance: the payload's entries plus the mounts."""
    names = set(INSTANCE_ONLY_EXTRA)
    if INSTANCE_TEMPLATE_ROOT.is_dir():
        names.update(p.name for p in INSTANCE_TEMPLATE_ROOT.iterdir())
    return frozenset(names)


def is_instance_path(rel: Path) -> bool:
    return bool(rel.parts) and rel.parts[0] in instance_paths()


# A bootstrapped checkout carries the instance contract; the framework repository
# never does. In instance mode the checks that cannot tell a framework skill from
# the instance's own are narrowed to what the catalog declares (see
# check_skill_registration) and the count assertion is skipped.
def instance_mode() -> bool:
    return (ROOT / ".claude" / "CLAUDE.md").is_file()


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                              check=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def is_own_framework() -> bool:
    """Is this checkout the framework repository itself, whatever it tracks?

    True when `origin` is the canonical framework, or when `upstream` is the same repository
    as `origin`. A change to the framework that tracks `.claude/CLAUDE.md` must not turn its
    own gate into an instance's: scoped to `main`, every file the change adds would escape it.
    """
    from ci_framework_ref import CANONICAL_URL, normalise_url
    origin = _git("remote", "get-url", "origin")
    if origin is None:
        return False
    upstream = _git("remote", "get-url", "upstream")
    mine = normalise_url(origin)
    return mine == normalise_url(CANONICAL_URL) or (upstream is not None and mine == normalise_url(upstream))


def own_framework_tracking_contract() -> bool:
    """The framework repository itself, with `.claude/CLAUDE.md` tracked: never an instance."""
    return (_git("ls-files", "--error-unmatch", ".claude/CLAUDE.md") is not None
            and is_own_framework())


@functools.lru_cache(maxsize=None)
def framework_scope() -> tuple[str, frozenset[str], frozenset[str]] | None:
    """In an instance: (ref, files, folders) the framework tracks at the last merged commit.

    None outside an instance (everything tracked is the framework's) and when no
    framework ref is reachable (the template-derived fallback applies). An instance
    COMMITS its contract; a framework developer's checkout (`bootstrap.sh --local`)
    only has it on disk, excluded — and must keep the full scope, or a file added on
    a branch there would escape the gate whenever an `upstream` remote exists.
    """
    if not instance_mode() or _git("ls-files", "--error-unmatch", ".claude/CLAUDE.md") is None:
        return None
    if is_own_framework():
        return None
    # An override can only widen the scope: the merge base with upstream/main still counts,
    # so a stale $META_OS_FRAMEWORK_REF cannot hide a file the framework added since.
    refs = dict.fromkeys(r for r in (os.environ.get("META_OS_FRAMEWORK_REF"), "upstream/main") if r)
    bases = [b.strip() for b in (_git("merge-base", "HEAD", r) for r in refs) if b]
    names: set[str] = set()
    for base in bases:
        names.update(n for n in (_git("ls-tree", "-r", "-z", "--name-only", base) or "").split("\0") if n)
    if not names:
        return None
    files = frozenset(names)
    folders = frozenset("/".join(Path(n).parts[:i]) for n in files
                        for i in range(1, len(Path(n).parts)))
    return " + ".join(b[:12] for b in dict.fromkeys(bases)), files, folders

# ---------------------------------------------------------------------------
# The `_index.md` convention, and the one ambiguity in it — resolved here.
# ---------------------------------------------------------------------------
# CLAUDE.md ("Conventions") says **every folder has an `_index.md`**, with no
# exemption written down. Read literally that indicts all 13 directories under
# `skills/`, because a skill directory does not carry one — its table of
# contents IS its `SKILL.md`: the front-matter `description` is the entry point
# and the progressive-disclosure body is the contents. A second index file
# inside `skills/<name>/` would be a duplicate nobody reads and nobody updates.
#
# So this gate reads the convention as: **every _navigational_ folder has an
# `_index.md`.** A skill directory is a self-describing unit, not a navigational
# folder, and is exempt together with its whole subtree (`references/`,
# `resources/`, the packaged `discipline-pack/` skeleton). `skills/` ITSELF is
# NOT exempt — it is the catalog folder and its index is load-bearing.
#
# This exemption is DECLARED, not buried: it lives in one named constant with
# this comment attached, so the reading is auditable and reversible. Set it to
# False and 13 directories start failing immediately — which is exactly the
# conversation to have if the project prefers the literal reading.
SKILL_DIRS_ARE_EXEMPT_FROM_INDEX = True

# The second reading of the same convention, declared the same way. `tests/fixtures/`
# holds the control packs for the pack conformance gate: they are INPUTS to a checker,
# not navigational folders in the vault, and a pack root does not carry an `_index.md`
# in the first place — the contract in `systems/pack.schema.json` says what a pack
# ships, and that is not it. So everything strictly BELOW `tests/fixtures/` is exempt,
# while `tests/` and `tests/fixtures/` themselves are ordinary folders and carry their
# own index. Set this to False and the fixture packs start failing immediately, which
# is the conversation to have if the project prefers the literal reading.
FIXTURE_PACKS_ARE_EXEMPT_FROM_INDEX = True
FIXTURES_DIR = ROOT / "tests" / "fixtures"

# Build output, not a folder anyone navigates. Gitignored, so it is never published —
# but the walk below reads the working tree, which may carry it after a gate has run.
TOOL_DIRS = {"__pycache__"}

# ---------------------------------------------------------------------------
# Public-safety scan. This repo is public; a leaked instance identifier is not
# retractable once pushed, so this class NEVER enters the baseline (see
# BASELINEABLE) and NEVER downgrades to a warning.
# ---------------------------------------------------------------------------
# `<PREFIX>-<number>` at a token boundary — the shape of an instance tracker key.
TRACKER_KEY_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,5}-[0-9]+)")
# An absolute macOS home path — a machine path, i.e. instance data.
ABS_HOME_RE = re.compile(r"/Users/[A-Za-z0-9._-]+")

# Narrow allow-list for the tracker-key pattern: EXACT tokens only, never
# prefixes and never regex, so widening it is always a visible one-line diff.
# Add a token here only when it is a published standard/encoding identifier that
# merely happens to look like a tracker key. Never add a real key: the correct
# fix for a real key is to remove it from the file.
PUBLIC_SAFETY_ALLOWED_TOKENS = frozenset({
    "UTF-8", "UTF-16", "UTF-32",     # character encodings
    "ISO-8601", "ISO-8859",          # date/charset standards
    "RFC-3339", "RFC-7231",          # IETF documents
    "SHA-1", "SHA-256", "SHA-512",   # digest algorithms
    "AES-128", "AES-256",            # ciphers
    "MIT-0",                         # SPDX licence identifier
})
# File suffixes worth scanning as text. Everything else (images, binaries) is
# skipped rather than decoded.
TEXT_SUFFIXES = {".md", ".markdown", ".yaml", ".yml", ".json", ".py", ".sh",
                 ".txt", ".toml", ".cfg", ".ini", ".xml", ".iml", ".js", ".ts", ""}

# ---------------------------------------------------------------------------
# Count assertions: prose claims that a machine can re-derive. Deliberately an
# explicit, tiny list rather than a regex sweep of every number in every doc —
# the scope of this check has to be obvious from reading it, or it becomes the
# check everyone turns off. Add a row only when the number has a single
# unambiguous source of truth in the tree.
# ---------------------------------------------------------------------------
COUNT_ASSERTIONS = (
    # (file, pattern with ONE capture group, human name of what is counted)
    ("README.md", re.compile(r"skill library \((\d+) skills?\)"),
     "skill directories in skills/"),
)

# Which classes may be silenced by the baseline. `public-safety` may not: a
# public-repo leak is the one failure mode with no undo, so it fails the gate on
# sight and its findings are never written to a committed file (that file would
# then carry the very string being flagged).
BASELINEABLE = {
    "skill-provenance": True,
    "skill-index": True,
    "index-phantom": True,
    "index-pack-table": True,
    # An unreadable registry is not debt anyone should accept: it switches the check off.
    "pack-registry": False,
    "systems-front-matter": True,
    "folder-index": True,
    "count-assertion": True,
    "public-safety": False,
    # The framework tracking an instance path is the one way an upgrade can collide
    # with an instance's files. Structural, so never tolerated as debt.
    "instance-path-tracked": False,
}


def front_matter(path: Path):
    """The YAML front-matter block of a note, or None. (Mirrors the vault gate.)"""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    try:
        fm = yaml.safe_load(text[4 : end + 1])
    except yaml.YAMLError:
        return None
    return fm if isinstance(fm, dict) else None


class Finding:
    __slots__ = ("check", "path", "detail")

    def __init__(self, check: str, path: str, detail: str):
        self.check, self.path, self.detail = check, path, detail

    @property
    def key(self) -> str:
        """Stable, greppable identity used by the baseline file."""
        return f"{self.check}\t{self.path}\t{self.detail}"

    def __str__(self) -> str:
        return f"{self.path}: {self.detail}  [{self.check}]"


# --- discovery helpers -----------------------------------------------------

def skill_dirs() -> list[Path]:
    """Real directories directly under skills/ that actually contain a SKILL.md.

    A symlink there is a pack skill `scripts/packs.sh sync` linked in beside the
    framework's own (one-repository layout) — mounted, not authored here, so it
    carries no provenance row and no catalog entry and is not a framework skill.
    """
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(d for d in SKILLS_DIR.iterdir()
                  if d.is_dir() and not d.is_symlink() and (d / SKILL_NAME).is_file())


def provenance_skills() -> set[str]:
    """Skill names named in the FIRST column of the `## Skill provenance` table.

    First column only, on purpose: `pack-builder` is mentioned in another row's
    Notes prose, and a skill being *talked about* is not a skill having a row.
    """
    if not PROVENANCE.is_file():
        return set()
    names: set[str] = set()
    in_table = False
    for line in PROVENANCE.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_table = line.strip().lower().startswith("## skill provenance")
            continue
        if not in_table or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or set(cells[0]) <= set("-: "):   # separator row
            continue
        if cells[0].lower().startswith("skill"):        # header row
            continue
        names.update(re.findall(r"`([^`]+)`", cells[0]))
    return names


def index_entries() -> set[str]:
    """Every skill name catalogued in skills/_index.md, from all its tables.

    Three shapes are catalogued there and all count as an entry:
      * core table  — a `[[skills/<name>/SKILL|…]]` wikilink;
      * pack-provided table — the backticked name in the first cell of a row under a
        `## Pack-provided …` heading (a pack skill has no folder here to link to; read,
        and its malformed rows reported, by scripts/pack_registry.py);
      * library table — a family row. A family cell ending in `-` (after the
        bold markers are stripped, e.g. `**agentdb-***`) is a PREFIX expanded
        over the `·`-separated members in the second cell; anything else (e.g.
        `**misc**`) lists the members verbatim.
    """
    from pack_registry import pack_table   # lazy: this module must import without it (test_run_tests copies it alone)
    if not SKILLS_INDEX.is_file():
        return set()
    text = SKILLS_INDEX.read_text(encoding="utf-8")
    entries = set(re.findall(r"\[\[skills/([^/\]|]+)/SKILL", text)) | pack_table(text)[0]

    in_library = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_library = "library" in line.lower()
            continue
        if not in_library or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= set("-: "):
            continue
        family = cells[0].strip("*` ")
        if family.lower() in ("family", "skill"):        # header row
            continue
        prefix = family if family.endswith("-") else ""
        for member in cells[1].split("·"):
            member = member.strip("*` ")
            if member:
                entries.add(prefix + member)
    return entries


def ontology_note_types() -> set[str]:
    if not ONTOLOGY.is_file():
        return set()
    try:
        data = yaml.safe_load(ONTOLOGY.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return set()
    types = data.get("note_types")
    return set(types) if isinstance(types, dict) else set()


def tracked_files() -> list[Path]:
    """Files git tracks — the scan is about what this repo PUBLISHES.

    Untracked and gitignored tool state (`.claude-flow/` session logs, IDE
    workspace files) is full of id-shaped strings and is never published, so
    asking git is both the correct scope and the cheap one. Outside a work tree
    the walk falls back to the tree minus every dot-directory, which is the same
    scope approximately.
    """
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                             capture_output=True, check=True).stdout
        files = [ROOT / n for n in out.decode("utf-8").split("\0") if n]
    except (OSError, subprocess.CalledProcessError):
        files = [p for p in ROOT.rglob("*")
                 if p.is_file()
                 and not any(part.startswith(".") for part in p.relative_to(ROOT).parts[:-1])]
    # An instance's own files are not the framework's to scan (and in the framework
    # repository the layout check below is what catches one being tracked at all).
    scope = framework_scope()
    if scope:
        return [p for p in files if p.relative_to(ROOT).as_posix() in scope[1]]
    return [p for p in files if not is_instance_path(p.relative_to(ROOT))]


def tracked_instance_paths() -> list[str]:
    """Tracked paths that sit at an instance path — must be empty in the framework."""
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return sorted(n for n in out.decode("utf-8").split("\0")
                  if n and is_instance_path(Path(n)))


def in_skill_subtree(d: Path) -> bool:
    """True for a skill directory itself, or anything nested inside one."""
    cur = d
    while cur != ROOT and ROOT in cur.parents:
        if (cur / SKILL_NAME).is_file():
            return True
        cur = cur.parent
    return False


# --- checks ----------------------------------------------------------------

def check_skill_registration(findings: list[Finding]) -> None:
    """1. Every skill on disk has a provenance row AND a catalog entry.

    In an instance, a real directory under skills/ may be the instance's own skill
    (allowed — see systems/packs.md), which has no business in the framework's
    provenance table. There the check runs over the catalogued framework skills
    instead: each still needs its provenance row, and index-phantom (below) still
    demands each resolves on disk. What is dropped is only "on disk but not
    catalogued", the one question that cannot be answered without knowing who
    owns the directory.
    """
    have_provenance, have_index = provenance_skills(), index_entries()
    if instance_mode():
        on_disk = {d.name for d in skill_dirs()}
        for name in sorted(have_index & on_disk):
            if name not in have_provenance:
                findings.append(Finding(
                    "skill-provenance", "PROVENANCE.md",
                    f"skill {name!r} is catalogued but has no row in the provenance table"))
        return
    for d in skill_dirs():
        if d.name not in have_provenance:
            findings.append(Finding(
                "skill-provenance", "PROVENANCE.md",
                f"skill {d.name!r} has a SKILL.md but no row in the provenance table "
                f"(PROVENANCE.md: 'No skill enters skills/ without a provenance row')"))
        if d.name not in have_index:
            findings.append(Finding(
                "skill-index", "skills/_index.md",
                f"skill {d.name!r} exists on disk but is absent from the catalog"))


def check_index_resolves(findings: list[Finding]) -> dict[str, str]:
    """2. Every catalogued entry resolves to a skill on disk or one a registered pack provides.

    A mounted pack's skill resolves from the pack's own tree (whether or not `packs.sh
    sync` linked it), and a mounted pack that stopped shipping a catalogued skill is a
    phantom. An entry whose pack is NOT mounted — never added, installed as a plugin, or an
    uninitialised (empty) submodule as in CI — resolves from the registry when an
    installable pack lists it in `provides:`; see scripts/pack_registry.py. A registry or a
    pack-provided row the gate cannot read is a finding of its own. Returns the
    pack-provided entries.
    """
    from pack_registry import mounted_packs, pack_table, provided_skills   # lazy, as in index_entries()
    on_disk = {d.name for d in skill_dirs()}
    if SKILLS_DIR.is_dir():
        on_disk |= {d.name for d in SKILLS_DIR.iterdir()
                    if d.is_symlink() and (d / SKILL_NAME).is_file()}
    provided, problems = provided_skills(PACKS_REGISTRY)
    findings.extend(Finding("pack-registry", "systems/packs.yaml", p) for p in problems)
    if SKILLS_INDEX.is_file():
        findings.extend(Finding("index-pack-table", "skills/_index.md", p)
                        for p in pack_table(SKILLS_INDEX.read_text(encoding="utf-8"))[1])
    mounted, pack_provided = mounted_packs(PACKS_DIR), {}
    on_disk |= set().union(*mounted.values())
    for name in sorted(index_entries()):
        pack = provided.get(name)
        if name in on_disk:
            continue
        if pack and pack not in mounted:
            pack_provided[name] = pack
            continue
        mounted = f" (pack {pack!r} is mounted and does not ship it)" if pack else ""
        findings.append(Finding(
            "index-phantom", "skills/_index.md",
            f"entry {name!r} does not resolve — no skills/{name}/{SKILL_NAME}{mounted}"))
    return pack_provided


def check_systems_front_matter(findings: list[Finding], note_types: set[str]) -> None:
    """3. Every systems/*.md carries non-empty type + tags, type declared in the ontology."""
    scope = framework_scope()
    for p in sorted(SYSTEMS_DIR.glob("*.md")):
        rel = str(p.relative_to(ROOT))
        if scope and p.relative_to(ROOT).as_posix() not in scope[1]:
            continue          # the instance's own note in systems/ — its own to shape
        fm = front_matter(p)
        if fm is None:
            findings.append(Finding("systems-front-matter", rel,
                                    "no parseable YAML front-matter block"))
            continue
        note_type = str(fm.get("type") or "").strip()
        tags = fm.get("tags")
        if not note_type:
            findings.append(Finding("systems-front-matter", rel, "missing or empty `type:`"))
        elif note_types and note_type not in note_types:
            findings.append(Finding(
                "systems-front-matter", rel,
                f"type {note_type!r} is not declared in systems/ontology.yaml note_types "
                f"({', '.join(sorted(note_types))})"))
        if not tags or (isinstance(tags, (list, str)) and len(tags) == 0):
            findings.append(Finding("systems-front-matter", rel, "missing or empty `tags:`"))


def check_folder_index(findings: list[Finding]) -> None:
    """4. Every navigational folder has an _index.md.

    Dot-directories and bytecode caches (`TOOL_DIRS`) are VCS/editor/tool state,
    not navigable content, and are never walked. Everything else is — including
    `scripts/` and `tests/`, which carry their own `_index.md` rather than an
    exemption written for their own benefit. There are exactly two real
    exemptions, each declared and explained where it is defined:
    `SKILL_DIRS_ARE_EXEMPT_FROM_INDEX` (a skill directory is self-describing) and
    `FIXTURE_PACKS_ARE_EXEMPT_FROM_INDEX` (a fixture pack is a gate's input).
    """
    scope = framework_scope()
    for d in sorted(p for p in ROOT.rglob("*") if p.is_dir()):
        rel_parts = d.relative_to(ROOT).parts
        if any(part.startswith(".") or part in TOOL_DIRS for part in rel_parts):
            continue
        if is_instance_path(Path(*rel_parts)):
            continue          # an instance's folders are the instance's to index
        if scope and "/".join(rel_parts) not in scope[2]:
            continue          # a folder the framework does not track: the instance's own
        if SKILL_DIRS_ARE_EXEMPT_FROM_INDEX and in_skill_subtree(d):
            continue
        if FIXTURE_PACKS_ARE_EXEMPT_FROM_INDEX and FIXTURES_DIR in d.parents:
            continue
        if not (d / INDEX_NAME).is_file():
            findings.append(Finding(
                "folder-index", str(d.relative_to(ROOT)),
                f"folder has no {INDEX_NAME} (CLAUDE.md, Conventions)"))


def check_public_safety(findings: list[Finding]) -> None:
    """5. No instance identifiers in tracked content. Never baselined, never a warning."""
    self_path = Path(__file__).resolve()
    for p in tracked_files():
        if p.resolve() == self_path or p == BASELINE:
            continue          # the gate states the patterns it hunts for
        if p.suffix.lower() not in TEXT_SUFFIXES or not p.is_file():
            continue
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(p.relative_to(ROOT))
        for n, line in enumerate(lines, 1):
            for token in TRACKER_KEY_RE.findall(line):
                if token in PUBLIC_SAFETY_ALLOWED_TOKENS:
                    continue
                findings.append(Finding(
                    "public-safety", f"{rel}:{n}",
                    f"looks like an instance tracker key: {token!r} — this repo is public "
                    f"(if it is a standards identifier, add the exact token to "
                    f"PUBLIC_SAFETY_ALLOWED_TOKENS)"))
            if ABS_HOME_RE.search(line):
                findings.append(Finding(
                    "public-safety", f"{rel}:{n}",
                    "absolute /Users/ home path — a machine path is instance data"))


def check_instance_paths_untracked(findings: list[Finding]) -> None:
    """7. The framework tracks no file at an instance path.

    The one-repository layout works only because the two owners' path sets are
    disjoint: an upgrade is a merge of the framework's paths, and a merge cannot
    touch a path the framework never tracks. This is the check that keeps the
    sets disjoint. Skipped in an instance, where those paths are exactly what is
    tracked, but not in the framework repository itself when it tracks the instance
    contract: that is the very path this check exists to refuse.
    """
    if instance_mode() and not own_framework_tracking_contract():
        return
    for n in tracked_instance_paths():
        findings.append(Finding(
            "instance-path-tracked", n,
            f"tracked at an instance path ({Path(n).parts[0]!r} is instantiated from "
            f"instance-template/root/ and belongs to the instance from then on)"))


def check_count_assertions(findings: list[Finding]) -> None:
    """6. Prose counts that a machine can re-derive actually match the tree."""
    if instance_mode():
        return                # the instance's own skills would inflate the count
    actual = {"skill directories in skills/": len(skill_dirs())}
    for filename, pattern, counted in COUNT_ASSERTIONS:
        p = ROOT / filename
        if not p.is_file():
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            m = pattern.search(line)
            if not m:
                continue
            claimed, real = int(m.group(1)), actual[counted]
            if claimed != real:
                findings.append(Finding(
                    "count-assertion", f"{filename}:{n}",
                    f"claims {claimed} where the tree has {real} ({counted})"))


# --- baseline / reporting --------------------------------------------------

def read_baseline() -> set[str]:
    if not BASELINE.is_file():
        return set()
    return {ln.rstrip("\n") for ln in BASELINE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")}


def write_baseline(findings: list[Finding]) -> int:
    keys = sorted({f.key for f in findings if BASELINEABLE.get(f.check, False)})
    header = (
        "# meta-os framework self-check — accepted debt (the ratchet).\n"
        "#\n"
        "# Each line is one KNOWN violation, recorded so it warns instead of failing\n"
        "# the gate. A violation NOT listed here is an error: debt can be paid down,\n"
        "# never grown. Removing a line is how debt gets retired — do that in the same\n"
        "# commit that fixes it. Regenerate with:\n"
        "#     python3 scripts/validate_framework.py --update-baseline\n"
        "# Format: <check>\\t<path>\\t<detail>\n"
        "# public-safety findings are never recorded here — see BASELINEABLE.\n"
    )
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(header + "\n".join(keys) + "\n", encoding="utf-8")
    return len(keys)


def main() -> None:
    ap = argparse.ArgumentParser(description="meta-os framework self-check")
    ap.add_argument("--strict", action="store_true",
                    help="promote every baselined warning to an error")
    ap.add_argument("--update-baseline", action="store_true",
                    help="re-record current violations as accepted debt")
    args = ap.parse_args()

    note_types = ontology_note_types()
    findings: list[Finding] = []
    check_skill_registration(findings)
    pack_provided = check_index_resolves(findings)
    check_systems_front_matter(findings, note_types)
    check_folder_index(findings)
    check_public_safety(findings)
    check_count_assertions(findings)
    check_instance_paths_untracked(findings)

    if args.update_baseline:
        n = write_baseline(findings)
        print(f"✓ baseline updated — {n} accepted violation(s) recorded in "
              f"{BASELINE.relative_to(ROOT)}")
        return

    if instance_mode() and _git("ls-files", "--error-unmatch", ".claude/CLAUDE.md") is not None:
        scope = framework_scope()
        if is_own_framework():
            print("  framework repository tracking .claude/CLAUDE.md — not an instance: "
                  "the gate keeps its full scope and refuses that path")
        else:
            print(f"  instance: checking the framework's paths at {scope[0]}" if scope else
                  "  instance: no framework ref (set META_OS_FRAMEWORK_REF or add the `upstream` "
                  "remote) — scope approximated by instance-template/root/")
    for name, pack in sorted(pack_provided.items()):
        print(f"  pack-provided: {name!r} — resolved from {PACKS_REGISTRY.relative_to(ROOT)} "
              f"(pack {pack!r}, not mounted here)")
    baseline = read_baseline()
    errors, warns = [], []
    for f in findings:
        silenced = (BASELINEABLE.get(f.check, False) and f.key in baseline and not args.strict)
        (warns if silenced else errors).append(f)

    for f in sorted(errors, key=lambda x: (x.check, x.path)):
        print(f"✗ {f}")
    for f in sorted(warns, key=lambda x: (x.check, x.path)):
        print(f"! {f}  (accepted debt)")

    per_class: dict[str, list[int]] = {}
    for bucket, idx in ((errors, 0), (warns, 1)):
        for f in bucket:
            per_class.setdefault(f.check, [0, 0])[idx] += 1
    if per_class:
        print("\n  check                  error   warn")
        for check in sorted(per_class):
            e, w = per_class[check]
            print(f"  {check:<22} {e:>5}  {w:>5}")

    # In an instance the baseline is the framework's: debt it records may well be absent
    # here (a catalogued pack skill resolves once its pack is mounted), and is not ours to drop.
    stale = set() if instance_mode() else baseline - {f.key for f in findings}
    if stale:
        print(f"\n  {len(stale)} baseline line(s) no longer match a violation — "
              f"fixed debt; drop them from {BASELINE.relative_to(ROOT)}:")
        for key in sorted(stale):
            check, path, detail = (key.split("\t") + ["", ""])[:3]
            print(f"    - [{check}] {path}: {detail}")

    if errors:
        sys.exit(f"\n✗ framework gate FAILED — {len(errors)} error(s), "
                 f"{len(warns)} accepted warning(s)")
    print(f"\n✓ framework valid — 0 errors, {len(warns)} accepted warning(s)")


if __name__ == "__main__":
    main()
