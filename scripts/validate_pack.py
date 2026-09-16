#!/usr/bin/env python3
"""Pack conformance gate for meta-os — the check `systems/pack.schema.json` asks for.

`systems/pack.schema.json` is the machine-readable contract for a pack's
`pack.yaml`, and until now nothing invoked it. Worse, its `required_files` block
is explicitly NOT JSON Schema — its own `$comment` calls it "the conformance
checklist a reviewer *or script* applies", and no such script existed. So the
half of the contract that says which files a pack must ship was enforced by
nobody. This is that script.

Deliberately shaped like `validate_framework.py` next to it (and the vault's
`validate_items.py` / `validate_sprints.py`) — same `Finding`, same baseline
ratchet, same exit convention — so one gate reads like the other across the
estate. It borrows exactly three names from that sibling (the tracker-key
pattern, its allow-list, and the text-suffix set) so that widening the
allow-list stays ONE visible diff for the whole estate rather than two that can
drift apart.

This script is the single home of the pack conformance checker: a pack lives in
its own repository and adopts it with a one-file caller workflow that points at
`.github/workflows/pack-conformance.yml` here. Nothing about a pack's conformance
may depend on a script that exists only on someone's machine.

What it checks
--------------
1. `pack.yaml` validates against `systems/pack.schema.json`.
2. Every path the schema's `required_files` block names exists in the pack —
   `always:` unconditionally, `conditional:` where the manifest triggers it.
3. Each skill matches the `per_skill` shape the same block spells out
   (front-matter `name`/`description`, and the named `##` sections).
4. `meta-os.config.json` validates against `systems/meta-os.config.schema.json`
   wherever one is present.
5. The pack is **estate-neutral** — it carries no instance-specific identifier.
   Same rule `validate_framework.py` applies to meta-os itself, applied to a pack
   tree, including the ratified LICENSE exemption. See ESTATE-NEUTRAL below.

Usage
-----
    python3 scripts/validate_pack.py                       # discover packs in-repo
    python3 scripts/validate_pack.py path/to/pack          # one pack directory
                                                           # (works from any repo)
    python3 scripts/validate_pack.py --strict              # every warning is an error
    python3 scripts/validate_pack.py --update-baseline     # re-record accepted debt

Severity model
--------------
Identical to `validate_framework.py`:

  * a finding recorded in `scripts/pack-baseline.txt` is a **WARN** — known debt;
  * anything else is an **ERROR** — a change introduced it;
  * `--strict` promotes every WARN to an ERROR;
  * `--update-baseline` re-records the current debt.

Three classes opt out of the ratchet (see `BASELINEABLE`), for the same reason
`validate_framework.py` exempts its public-safety scan: accepting them as debt
would mean accepting that the gate itself is not running.

A note on the JSON Schema draft
-------------------------------
`pack.schema.json` declares draft 2020-12. The available `jsonschema` is 3.2.0,
whose newest supported draft is 7 — it does not carry the 2020-12 meta-schema at
all. Left to autodetect, `jsonschema` emits a DeprecationWarning and silently
falls back to Draft7Validator, which is exactly the kind of quiet
under-validation a gate must not do. So the validator class is chosen
explicitly, and `POST_DRAFT7_KEYWORDS` guards the fallback: if the schema ever
starts using a keyword Draft 7 does not understand, this gate fails loudly
instead of ignoring it. Upgrading `jsonschema` past 4.x is the real fix and is
deliberately NOT done here — it is a dependency decision, not a gate decision.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    sys.exit("PyYAML required: pip3 install pyyaml")

try:
    import jsonschema
except ModuleNotFoundError:  # pragma: no cover
    sys.exit("jsonschema required: pip3 install jsonschema")

# The sibling gate owns the estate's public-safety primitives; this one reuses them
# rather than restating them, so the allow-list has a single home. Both scripts ship
# together in scripts/ — the reusable workflow checks out this repo, never one file.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_framework import (  # noqa: E402  (path set up immediately above)
    PUBLIC_SAFETY_ALLOWED_TOKENS,
    TEXT_SUFFIXES,
    TRACKER_KEY_RE,
)

ROOT = Path(__file__).resolve().parent.parent
PACK_SCHEMA = ROOT / "systems" / "pack.schema.json"
CONFIG_SCHEMA = ROOT / "systems" / "meta-os.config.schema.json"
BASELINE = ROOT / "scripts" / "pack-baseline.txt"

MANIFEST_NAME = "pack.yaml"
CONFIG_NAME = "meta-os.config.json"
SKILL_NAME = "SKILL.md"

# Directories never walked when discovering packs in-repo: VCS/editor/tool state.
SKIP_DIRS = {".git", ".idea", ".obsidian", ".claude", ".claude-flow",
             "node_modules", "__pycache__"}

# Keywords introduced after draft-07. If `pack.schema.json` grows one of these,
# Draft7Validator would silently ignore it — so the gate stops instead. Listing
# them explicitly (rather than trusting autodetection) is the whole point.
POST_DRAFT7_KEYWORDS = frozenset({
    "$defs", "$anchor", "$recursiveRef", "$recursiveAnchor",
    "$dynamicRef", "$dynamicAnchor", "$vocabulary",
    "prefixItems", "unevaluatedItems", "unevaluatedProperties",
    "dependentRequired", "dependentSchemas",
    "minContains", "maxContains",
})

# A `<placeholder>` inside a required_files entry.
PLACEHOLDER_RE = re.compile(r"<([a-z_]+)>")

# Path prefixes the in-repo sweep never descends into. `tests/fixtures` holds this
# gate's own positive and negative controls, and one of those packs is
# non-conformant BY DESIGN — discovering it here would make meta-os fail its own
# gate for shipping a test input. The fixtures are checked by pointing the gate at
# them explicitly, which is what tests/test_validate_pack.py does.
EXCLUDED_FROM_DISCOVERY = (("tests", "fixtures"),)

# ---------------------------------------------------------------------------
# ESTATE-NEUTRAL — a pack must carry no instance-specific identifier.
# ---------------------------------------------------------------------------
# A pack is published on its own, so whatever estate authored it must not be
# legible from its contents. This is `validate_framework.py`'s `public-safety`
# rule applied to a pack tree, and like its sibling it NEVER enters the baseline
# (see BASELINEABLE): a leak in a published pack has no undo, so it fails the gate
# on sight rather than warning.
#
# Three identifier classes, and exactly one exemption:
#
#   1. tracker keys        `<PREFIX>-<number>`     — no exemption, LICENSE included
#   2. absolute home paths `/Users/…`, `/home/…`   — no exemption, LICENSE included
#   3. the LICENSE copyright holder                — EXEMPT IN LICENSE, nowhere else
#
# Class 3 encodes the ratified LICENSE exemption (product-owner decision,
# 2026-09-14): *a copyright holder's name in LICENSE is not an instance
# identifier*. It is encoded rather than asserted in a review comment — the gate
# reads the holder out of the pack's own LICENSE and then hunts that exact string
# through every OTHER file. So the adversarial pair is decided by the checker: the
# holder in LICENSE passes, the same holder in a skill file fails.
#
# The exemption is NARROW in both directions, which is the point. It exempts one
# file from one class: a tracker key or a machine path inside LICENSE still fails,
# and the holder name in PROVENANCE.md still fails. Widening it (a third-party
# pack whose PROVENANCE.md must name its upstream is the obvious candidate) is a
# one-line change to this constant, reviewable as such.
HOLDER_EXEMPT_FILES = frozenset({"LICENSE"})

# Broader than the sibling gate's equivalent on purpose: meta-os is authored in one
# estate, whereas a pack can be authored anywhere, and `/home/<user>` is as much a
# machine path as `/Users/<user>`.
HOME_PATH_RE = re.compile(r"(?:/Users|/home|/export/home)/[A-Za-z0-9._-]+")

# The attribution line of a licence: the word, an optional (c)/© marker, an optional
# year or year span, then the holder. The marker-or-year is REQUIRED (enforced in
# `license_holder`) so that prose in the licence body — "The above copyright notice
# and this permission notice shall be included…" — is not read as an attribution.
COPYRIGHT_RE = re.compile(
    r"copyright\b\s*(?P<marker>\(c\)|©)?\s*"
    r"(?P<years>[0-9]{4}(?:\s*[-–,]\s*[0-9]{4})*)?\s*"
    r"(?P<holder>\S.*?)\s*$",
    re.IGNORECASE)

# A trailing rights reservation is boilerplate, not part of the holder's name.
ALL_RIGHTS_RE = re.compile(r"[.,;]?\s*all rights reserved\.?\s*$", re.IGNORECASE)

# Holders that name nobody. An unfilled licence template ("<name of copyright
# owner>") or a generic phrase must never become the string this gate hunts — it
# would match half the tree and the gate would be reporting on itself.
HOLDER_BOILERPLATE = frozenset({
    "author", "authors", "the author", "the authors",
    "copyright holder", "copyright holders",
    "the copyright holder", "the copyright holders",
    "name of copyright owner", "copyright owner", "the copyright owner",
    "owner", "the owner", "notice", "year", "the year",
})

# Below this length a "holder" is too generic to hunt without false positives.
MIN_HOLDER_LEN = 4

# Which classes may be silenced by the baseline.
#
# `checklist-placeholder` may not: it fires when this gate cannot interpret the
# schema's own checklist, and a silenced finding there means the checklist is
# being skipped rather than applied. `pack-manifest` may not either: when the
# manifest does not parse, nothing below it can run, and a YAML parse message is
# not a stable baseline key anyway. `estate-neutral` may not, for the reason its
# own section gives: a published leak has no undo, and recording one in a
# committed baseline file would make that file carry the very string being
# flagged.
BASELINEABLE = {
    "pack-manifest": False,
    "pack-schema": True,
    "pack-required-file": True,
    "pack-conditional-file": True,
    "pack-skill-shape": True,
    "config-schema": True,
    "checklist-placeholder": False,
    "estate-neutral": False,
}


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


# Directories a finding's path may be rendered against, beyond ROOT. main() adds the
# parent of every pack named on the command line, so a pack checked from OUTSIDE this
# repo — the reusable workflow's whole purpose — still reports `<pack-dir>/skills/…`
# rather than the runner's absolute path. A gate whose own output carries a machine
# path is not estate-neutral either.
DISPLAY_ROOTS: list[Path] = []


def rel(p: Path) -> str:
    """Path rendered against a known root — baseline keys must not carry a machine path."""
    resolved = p.resolve()
    for base in (ROOT, *DISPLAY_ROOTS):
        try:
            return str(resolved.relative_to(base))
        except ValueError:
            continue
    return resolved.name


def front_matter(path: Path):
    """The YAML front-matter block of a note, or None. (Mirrors the sibling gates.)"""
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


# --- schema loading --------------------------------------------------------

def load_schema(path: Path, findings: list[Finding], check: str):
    """Load a JSON Schema and pick its validator class EXPLICITLY.

    Returns (validator, schema) or (None, None) when the schema cannot be used.
    """
    if not path.is_file():
        findings.append(Finding(check, rel(path), "schema file not found"))
        return None, None
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        findings.append(Finding(check, rel(path), f"schema is not readable JSON: {exc}"))
        return None, None

    used = post_draft7_keywords_used(schema)
    if used:
        findings.append(Finding(
            check, rel(path),
            f"schema uses post-draft-07 keyword(s) {sorted(used)} but the installed "
            f"jsonschema is {jsonschema.__version__}, whose newest draft is 7 — those "
            f"keywords would be IGNORED. Upgrade jsonschema, or drop the keyword."))
        return None, None

    validator_cls = jsonschema.Draft7Validator
    try:
        validator_cls.check_schema(schema)
    except jsonschema.SchemaError as exc:
        findings.append(Finding(check, rel(path), f"schema is itself invalid: {exc.message}"))
        return None, None
    return validator_cls(schema), schema


def post_draft7_keywords_used(node) -> set:
    """Every POST_DRAFT7_KEYWORDS name appearing as a key anywhere in the schema."""
    found: set = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if k in POST_DRAFT7_KEYWORDS:
                found.add(k)
            found |= post_draft7_keywords_used(v)
    elif isinstance(node, list):
        for v in node:
            found |= post_draft7_keywords_used(v)
    return found


def describe(err) -> str:
    """A jsonschema error rendered as a stable one-liner (no line numbers, no addresses)."""
    where = "/".join(str(p) for p in err.absolute_path) or "<root>"
    return f"{where}: {err.message}"


# --- discovery -------------------------------------------------------------

def discover_packs() -> list[Path]:
    """Every directory in the repo carrying a pack.yaml.

    In meta-os itself that is the authoring skeleton shipped inside
    skills/pack-builder/resources/ — real packs live in their own repositories
    and are validated by pointing this script at a checkout.
    `EXCLUDED_FROM_DISCOVERY` says which subtrees the sweep refuses to enter.
    """
    packs: list[Path] = []
    for p in ROOT.rglob(MANIFEST_NAME):
        parts = p.relative_to(ROOT).parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        if any(parts[:len(prefix)] == prefix for prefix in EXCLUDED_FROM_DISCOVERY):
            continue
        packs.append(p.parent)
    return sorted(packs)


def skill_dirs(pack: Path) -> list[Path]:
    """Directories under the pack's skills/ that actually contain a SKILL.md."""
    skills = pack / "skills"
    if not skills.is_dir():
        return []
    return sorted(d for d in skills.iterdir() if d.is_dir() and (d / SKILL_NAME).is_file())


# --- the required_files checklist ------------------------------------------

def check_always(pack: Path, always, manifest, findings: list[Finding]) -> None:
    """required_files.always — every entry must exist, placeholders expanded."""
    for entry in always or []:
        placeholders = PLACEHOLDER_RE.findall(entry)
        if not placeholders:
            if not (pack / entry).exists():
                findings.append(Finding(
                    "pack-required-file", f"{rel(pack)}/{entry}",
                    f"required by pack.schema.json required_files.always, but missing"))
            continue
        if placeholders == ["skill"] and entry == "skills/<skill>/SKILL.md":
            if not skill_dirs(pack):
                findings.append(Finding(
                    "pack-required-file", f"{rel(pack)}/skills",
                    "required_files.always names `skills/<skill>/SKILL.md` but the pack "
                    "ships no skills/<name>/SKILL.md — a pack with no skill is not a pack"))
            continue
        findings.append(Finding(
            "checklist-placeholder", rel(PACK_SCHEMA),
            f"required_files.always entry {entry!r} uses placeholder(s) "
            f"{sorted(set(placeholders))} that this gate does not know how to expand — "
            f"teach scripts/validate_pack.py the rule or the entry goes unchecked"))


def check_conditional(pack: Path, conditional, manifest, findings: list[Finding]) -> None:
    """required_files.conditional — entries whose requirement the manifest triggers.

    Today that is exactly one rule: `profiles/<name>.md`, "one per entry in
    profiles:". The manifest's own `profiles:` mapping is the source of truth for
    the path (the schema types its values as the file), so a manifest that names
    `profiles/x.md` is checked at that path rather than at a path this gate
    guesses.
    """
    for entry, note in (conditional or {}).items():
        if entry == "profiles/<name>.md":
            profiles = manifest.get("profiles")
            if not isinstance(profiles, dict):
                continue      # no profiles declared -> nothing conditional to require
            for name, path_value in profiles.items():
                target = str(path_value) if path_value else f"profiles/{name}.md"
                if not (pack / target).exists():
                    findings.append(Finding(
                        "pack-conditional-file", f"{rel(pack)}/{target}",
                        f"pack.yaml declares profile {name!r} but its file is missing "
                        f"(required_files.conditional: {note})"))
            continue
        findings.append(Finding(
            "checklist-placeholder", rel(PACK_SCHEMA),
            f"required_files.conditional entry {entry!r} ({note}) has no rule in "
            f"scripts/validate_pack.py — it goes unchecked until one is written"))


def required_sections(per_skill) -> list[str]:
    """The `## ` headings the per_skill checklist names, derived from the schema.

    Entries are written as `## Method — numbered steps, …`; the part before the
    em-dash is the heading. An entry that is not a heading (`intro — …`) is prose
    guidance for an author, not something a gate can assert, and is skipped.
    """
    out: list[str] = []
    for item in (per_skill or {}).get("sections", []) or []:
        text = str(item).strip()
        if not text.startswith("## "):
            continue
        out.append(text.split("—")[0].strip())
    return out


def check_per_skill(pack: Path, per_skill, findings: list[Finding]) -> None:
    """required_files.per_skill — front-matter shape and the named sections."""
    sections = required_sections(per_skill)
    for d in skill_dirs(pack):
        skill_md = d / SKILL_NAME
        where = rel(skill_md)
        fm = front_matter(skill_md)
        if fm is None:
            findings.append(Finding("pack-skill-shape", where,
                                    "no parseable YAML front-matter block "
                                    "(required_files.per_skill.frontmatter)"))
        else:
            name = str(fm.get("name") or "").strip()
            if not name:
                findings.append(Finding("pack-skill-shape", where, "front-matter missing `name:`"))
            elif name != d.name:
                findings.append(Finding(
                    "pack-skill-shape", where,
                    f"front-matter name {name!r} does not match its folder {d.name!r}"))
            elif not re.fullmatch(r"[a-z][a-z0-9-]*", name):
                findings.append(Finding(
                    "pack-skill-shape", where,
                    f"front-matter name {name!r} is not lowercase-kebab"))
            if not str(fm.get("description") or "").strip():
                findings.append(Finding("pack-skill-shape", where,
                                        "front-matter missing `description:` (what AND when)"))
        body = skill_md.read_text(encoding="utf-8")
        present = {ln.strip() for ln in body.splitlines() if ln.startswith("## ")}
        for heading in sections:
            if not any(p == heading or p.startswith(heading) for p in present):
                findings.append(Finding(
                    "pack-skill-shape", where,
                    f"missing required section {heading!r} "
                    f"(required_files.per_skill.sections)"))


# --- the estate-neutral scan -----------------------------------------------

def pack_text_files(pack: Path):
    """Every text file in the pack, skipping VCS/editor/tool state.

    A filesystem walk rather than `git ls-files`: a pack may be checked as a
    subdirectory, as a fresh checkout, or as a temporary tree in a test, and the
    rule is about what the pack CONTAINS either way.
    """
    for p in sorted(pack.rglob("*")):
        if any(part in SKIP_DIRS for part in p.relative_to(pack).parts):
            continue
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        yield p


def clean_holder(raw: str) -> str | None:
    """The holder name from a matched attribution line, or None if it names nobody."""
    holder = ALL_RIGHTS_RE.sub("", raw.strip()).strip(" \t.,;:")
    # `<name>` / `[name of copyright owner]`: an unfilled template names nobody, and
    # hunting a placeholder through the tree would match half of it.
    if not holder or any(ch in holder for ch in "<>[]"):
        return None
    if holder.lower() in HOLDER_BOILERPLATE or len(holder) < MIN_HOLDER_LEN:
        return None
    return holder


def license_holder(pack: Path) -> str | None:
    """The copyright holder named on the pack's LICENSE attribution line, or None.

    The FIRST line that carries the word *copyright* together with a (c)/© marker or
    a year wins; a pack with no LICENSE, or whose LICENSE names nobody, simply has no
    holder to hunt (the missing LICENSE is already a `pack-required-file` finding).
    """
    lic = pack / "LICENSE"
    if not lic.is_file():
        return None
    try:
        text = lic.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
    for line in text.splitlines():
        m = COPYRIGHT_RE.search(line)
        if not m or not (m.group("marker") or m.group("years")):
            continue
        holder = clean_holder(m.group("holder"))
        if holder:
            return holder
    return None


def holder_pattern(holder: str):
    """The holder hunted case-insensitively, at token boundaries."""
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(holder) + r"(?![A-Za-z0-9])",
                      re.IGNORECASE)


def check_estate_neutral(pack: Path, findings: list[Finding]) -> None:
    """5. No instance identifier in the pack. Never baselined, never a warning.

    The LICENSE exemption (see ESTATE-NEUTRAL at the top of this file) applies to the
    holder class only, and only inside the files named in `HOLDER_EXEMPT_FILES`.
    """
    holder = license_holder(pack)
    holder_re = holder_pattern(holder) if holder else None
    for f in pack_text_files(pack):
        in_pack = f.relative_to(pack).as_posix()
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        holder_exempt = in_pack in HOLDER_EXEMPT_FILES
        for n, line in enumerate(lines, 1):
            where = f"{rel(f)}:{n}"
            for token in TRACKER_KEY_RE.findall(line):
                if token in PUBLIC_SAFETY_ALLOWED_TOKENS:
                    continue
                findings.append(Finding(
                    "estate-neutral", where,
                    f"looks like an instance tracker key: {token!r} — a pack is "
                    f"published on its own and must name no estate (if it is a "
                    f"standards identifier, add the exact token to "
                    f"PUBLIC_SAFETY_ALLOWED_TOKENS in validate_framework.py)"))
            if HOME_PATH_RE.search(line):
                findings.append(Finding(
                    "estate-neutral", where,
                    "absolute home path — a machine path is instance data"))
            # The holder itself is deliberately NOT echoed: the file and line are
            # enough to find it, and a gate that reprints the name it is objecting
            # to spreads it into every log that reads the run.
            if holder_re and not holder_exempt and holder_re.search(line):
                findings.append(Finding(
                    "estate-neutral", where,
                    "names the pack's LICENSE copyright holder outside "
                    f"{sorted(HOLDER_EXEMPT_FILES)} — a holder's name is exempt in "
                    "LICENSE (ratified) and is an instance identifier everywhere else"))


# --- per-pack driver -------------------------------------------------------

def check_pack(pack: Path, validator, schema, findings: list[Finding]) -> None:
    manifest_path = pack / MANIFEST_NAME
    if not manifest_path.is_file():
        findings.append(Finding("pack-manifest", rel(pack),
                                f"not a pack: no {MANIFEST_NAME}"))
        return
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        findings.append(Finding("pack-manifest", rel(manifest_path),
                                f"{MANIFEST_NAME} is not parseable YAML: "
                                f"{str(exc).splitlines()[0]}"))
        return
    if not isinstance(manifest, dict):
        findings.append(Finding("pack-manifest", rel(manifest_path),
                                f"{MANIFEST_NAME} is not a mapping"))
        return

    if validator is not None:
        for err in sorted(validator.iter_errors(manifest),
                          key=lambda e: (list(e.absolute_path), e.message)):
            findings.append(Finding("pack-schema", rel(manifest_path), describe(err)))

    required_files = (schema or {}).get("required_files") or {}
    if not required_files:
        findings.append(Finding(
            "checklist-placeholder", rel(PACK_SCHEMA),
            "no `required_files` block — the conformance checklist half of the contract "
            "is gone, so only the JSON Schema half was applied"))
        return
    check_always(pack, required_files.get("always"), manifest, findings)
    check_conditional(pack, required_files.get("conditional"), manifest, findings)
    check_per_skill(pack, required_files.get("per_skill"), findings)


def check_config_files(paths: list[Path], findings: list[Finding]) -> None:
    """meta-os.config.json against its schema, wherever one is present.

    Absence is not a finding: the config schema's own description says every key
    is optional and "omitting the file yields default behaviour".
    """
    present = [p for p in paths if p.is_file()]
    if not present:
        return
    validator, _ = load_schema(CONFIG_SCHEMA, findings, "config-schema")
    if validator is None:
        return
    for p in present:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            findings.append(Finding("config-schema", rel(p),
                                    f"not readable JSON: {exc}"))
            continue
        for err in sorted(validator.iter_errors(data),
                          key=lambda e: (list(e.absolute_path), e.message)):
            findings.append(Finding("config-schema", rel(p), describe(err)))


# --- baseline / reporting --------------------------------------------------

def read_baseline() -> set:
    if not BASELINE.is_file():
        return set()
    return {ln.rstrip("\n") for ln in BASELINE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")}


def write_baseline(findings: list[Finding]) -> int:
    keys = sorted({f.key for f in findings if BASELINEABLE.get(f.check, False)})
    header = (
        "# meta-os pack conformance — accepted debt (the ratchet).\n"
        "#\n"
        "# Each line is one KNOWN violation, recorded so it warns instead of failing\n"
        "# the gate. A violation NOT listed here is an error: debt can be paid down,\n"
        "# never grown. Removing a line is how debt gets retired — do that in the same\n"
        "# commit that fixes it. Regenerate with:\n"
        "#     python3 scripts/validate_pack.py --update-baseline\n"
        "# Format: <check>\\t<path>\\t<detail>\n"
        "# checklist-placeholder and pack-manifest are never recorded — see BASELINEABLE.\n"
    )
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(header + "\n".join(keys) + "\n", encoding="utf-8")
    return len(keys)


def main() -> None:
    ap = argparse.ArgumentParser(description="meta-os pack conformance gate")
    ap.add_argument("packs", nargs="*", type=Path,
                    help="pack directories to check (default: discover in-repo)")
    ap.add_argument("--strict", action="store_true",
                    help="promote every baselined warning to an error")
    ap.add_argument("--update-baseline", action="store_true",
                    help="re-record current violations as accepted debt")
    args = ap.parse_args()

    findings: list[Finding] = []
    validator, schema = load_schema(PACK_SCHEMA, findings, "pack-schema")

    # A run scoped to explicit pack arguments sees only part of the picture, so it
    # must not reason about the baseline as a whole: findings it did not look for
    # are not findings that were fixed.
    full_sweep = not args.packs
    if args.update_baseline and not full_sweep:
        sys.exit("--update-baseline re-records the WHOLE baseline and would drop every "
                 "accepted violation outside the packs named on the command line. "
                 "Run it with no pack arguments.")

    packs = [p.resolve() for p in args.packs] if args.packs else discover_packs()
    # Render out-of-repo findings against the pack's own parent — see DISPLAY_ROOTS.
    DISPLAY_ROOTS.extend(p.parent for p in packs)
    if not packs:
        print("no packs found — nothing to check "
              f"(looked for {MANIFEST_NAME} under {ROOT})")
        return
    for pack in packs:
        check_pack(pack, validator, schema, findings)
        # Estate-neutrality is a property of the tree, not of the manifest, so it is
        # checked even when the manifest itself failed to parse.
        check_estate_neutral(pack, findings)

    check_config_files([ROOT / CONFIG_NAME] + [p / CONFIG_NAME for p in packs], findings)

    if args.update_baseline:
        n = write_baseline(findings)
        print(f"✓ baseline updated — {n} accepted violation(s) recorded in "
              f"{BASELINE.relative_to(ROOT)}")
        return

    baseline = read_baseline()
    errors, warns = [], []
    for f in findings:
        silenced = (BASELINEABLE.get(f.check, False) and f.key in baseline and not args.strict)
        (warns if silenced else errors).append(f)

    for f in sorted(errors, key=lambda x: (x.check, x.path)):
        print(f"✗ {f}")
    for f in sorted(warns, key=lambda x: (x.check, x.path)):
        print(f"! {f}  (accepted debt)")

    per_class: dict = {}
    for bucket, idx in ((errors, 0), (warns, 1)):
        for f in bucket:
            per_class.setdefault(f.check, [0, 0])[idx] += 1
    if per_class:
        print("\n  check                  error   warn")
        for check in sorted(per_class):
            e, w = per_class[check]
            print(f"  {check:<22} {e:>5}  {w:>5}")

    stale = (baseline - {f.key for f in findings}) if full_sweep else set()
    if stale:
        print(f"\n  {len(stale)} baseline line(s) no longer match a violation — "
              f"fixed debt; drop them from {BASELINE.relative_to(ROOT)}:")
        for key in sorted(stale):
            check, path, detail = (key.split("\t") + ["", ""])[:3]
            print(f"    - [{check}] {path}: {detail}")

    checked = ", ".join(rel(p) for p in packs)
    if errors:
        sys.exit(f"\n✗ pack gate FAILED — {len(errors)} error(s), "
                 f"{len(warns)} accepted warning(s) across: {checked}")
    print(f"\n✓ packs conformant — 0 errors, {len(warns)} accepted warning(s) "
          f"across: {checked}")


if __name__ == "__main__":
    main()
