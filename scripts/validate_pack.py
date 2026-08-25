#!/usr/bin/env python3
"""Pack conformance gate for meta-os — the check `systems/pack.schema.json` asks for.

`systems/pack.schema.json` is the machine-readable contract for a pack's
`pack.yaml`, and until now nothing invoked it. Worse, its `required_files` block
is explicitly NOT JSON Schema — its own `$comment` calls it "the conformance
checklist a reviewer *or script* applies", and no such script existed. So the
half of the contract that says which files a pack must ship was enforced by
nobody. This is that script.

Self-contained on purpose, and deliberately shaped like `validate_framework.py`
next to it (and the vault's `validate_items.py` / `validate_sprints.py`) — same
`Finding`, same baseline ratchet, same exit convention — so one gate reads like
the other across the estate.

What it checks
--------------
1. `pack.yaml` validates against `systems/pack.schema.json`.
2. Every path the schema's `required_files` block names exists in the pack —
   `always:` unconditionally, `conditional:` where the manifest triggers it.
3. Each skill matches the `per_skill` shape the same block spells out
   (front-matter `name`/`description`, and the named `##` sections).
4. `meta-os.config.json` validates against `systems/meta-os.config.schema.json`
   wherever one is present.

Usage
-----
    python3 scripts/validate_pack.py                       # discover packs in-repo
    python3 scripts/validate_pack.py path/to/pack          # one pack directory
    python3 scripts/validate_pack.py --strict              # every warning is an error
    python3 scripts/validate_pack.py --update-baseline     # re-record accepted debt

Severity model
--------------
Identical to `validate_framework.py`:

  * a finding recorded in `scripts/pack-baseline.txt` is a **WARN** — known debt;
  * anything else is an **ERROR** — a change introduced it;
  * `--strict` promotes every WARN to an ERROR;
  * `--update-baseline` re-records the current debt.

Two classes opt out of the ratchet (see `BASELINEABLE`), for the same reason
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

ROOT = Path(__file__).resolve().parent.parent
PACK_SCHEMA = ROOT / "systems" / "pack.schema.json"
CONFIG_SCHEMA = ROOT / "systems" / "meta-os.config.schema.json"
BASELINE = ROOT / "scripts" / "pack-baseline.txt"

MANIFEST_NAME = "pack.yaml"
CONFIG_NAME = "meta-os.config.json"
SKILL_NAME = "SKILL.md"

# Directories never walked when discovering packs in-repo: VCS/editor/tool state.
SKIP_DIRS = {".git", ".idea", ".obsidian", ".claude", ".claude-flow", "node_modules"}

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

# Which classes may be silenced by the baseline.
#
# `checklist-placeholder` may not: it fires when this gate cannot interpret the
# schema's own checklist, and a silenced finding there means the checklist is
# being skipped rather than applied. `pack-manifest` may not either: when the
# manifest does not parse, nothing below it can run, and a YAML parse message is
# not a stable baseline key anyway.
BASELINEABLE = {
    "pack-manifest": False,
    "pack-schema": True,
    "pack-required-file": True,
    "pack-conditional-file": True,
    "pack-skill-shape": True,
    "config-schema": True,
    "checklist-placeholder": False,
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


def rel(p: Path) -> str:
    """Repo-relative path where possible — baseline keys must not carry a machine path."""
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


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
    """
    packs: list[Path] = []
    for p in ROOT.rglob(MANIFEST_NAME):
        parts = p.relative_to(ROOT).parts
        if any(part in SKIP_DIRS for part in parts):
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
    if not packs:
        print("no packs found — nothing to check "
              f"(looked for {MANIFEST_NAME} under {ROOT})")
        return
    for pack in packs:
        check_pack(pack, validator, schema, findings)

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
