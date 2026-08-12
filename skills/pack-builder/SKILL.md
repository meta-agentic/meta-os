---
name: "Pack Builder"
description: "Author a new meta-os skill pack — a mountable, parameterised, curated collection of skills that codifies a discipline (a method + a rigor standard). Use when creating a pack from scratch, extracting skills from a core into a pack, or turning a domain's practice (research, systems engineering, a regulated field, an engineering branch) into a reusable pack. The mechanism is in systems/packs.md; the thesis (what makes a good pack, and where the opportunity is) in systems/pack-strategy.md."
---

# Pack Builder

The meta-discipline: how to turn a body of practice into a **pack** — a git repo of
skills that mounts into any instance, carries its method, and takes the estate's choices
as config. `skill-builder` authors one skill; this authors the *collection + contract*
around a discipline. Read [[systems/packs]] (mechanism) and [[systems/pack-strategy]]
(what to build and why) before starting.

## Step 0 — Is it a pack? (the three-part test)

Don't build until the candidate passes all three ([[systems/pack-strategy]]):

1. **Recognizable** — a practitioner would call it "how we actually work."
2. **Portable** — parameterizable to any estate, not welded to one shop.
3. **Checkable** — it produces outputs a reviewer can verify against the discipline's
   own standard.

A pack is a **codified discipline = method + rigor standard + portability**. If it's only
a process (steps, no standard of "done right"), it's under-specified — add the rigor. If
it's only one estate's config, it's not a pack — it's instance data.

## Step 1 — Scope & name

- Name the **discipline**, not a tool (`research`, `systems-engineering`, `quant-rigor` —
  not `zotero-helper`). One discipline per pack; one **provenance** per pack (don't mix
  first-party and vendored — see the curation bar).
- List the skills. Each is a distinct *method or judgment* within the discipline. Keep
  the pack lean; a skill that isn't recognizable/checkable is a candidate to cut.

## Step 2 — Structure

A pack is any repo with `SKILL.md` folders; the mount handles flat, category-nested, or
`.claude-plugin/plugin.json` layouts ([[systems/packs]]). **Start from the skeleton in
`resources/discipline-pack/`**, not from memory — it is the shape the shipped first-party
packs actually carry:

```
<pack>/
├── skills/_index.md             ← REQUIRED: the folder's contents —
│                                  Skill | Discipline | Checkable output, one row each
├── skills/<skill>/SKILL.md      ← the discipline's methods & judgments
├── pack.yaml                    ← manifest + config schema; validate against
│                                  [[systems/pack.schema.json|pack.schema.json]]
├── config.example.yaml          ← the block a user copies into .packs.yaml
├── profiles/<name>.md           ← named rigor bundles — ONLY if the discipline has
│                                  genuine variants; never invent a split to look complete
├── README.md                    ← skills table, the three-part test, configure, install
├── PROVENANCE.md                ← REQUIRED: per-skill origin table, the public-safe
│                                  statement, and why THIS coverage was chosen
├── .gitignore
└── LICENSE
```

Author each skill with [[skills/skill-builder/SKILL|skill-builder]]. It MAY also carry
`agents/` (engine agent defs) and `hooks/` (staged, never auto-wired).

**Every skill takes the same five-part shape** — see
`resources/discipline-pack/skills/SKILL.template.md`: intro (what a practitioner does,
and the boundary with sibling skills) → **Method** (numbered steps, config knobs
referenced inline) → **The rigor standard** (what to reject) → **Checkable output** →
**Anti-patterns**. Target 80–120 lines.

> **The ledger is the load-bearing part.** "Checkable output" means a **named ledger with
> a concrete, filled-in example** — an estimation ledger, a claims ledger, a
> generation-constraint ledger. It is what turns the rigor standard from an assertion into
> something a reviewer can audit, and it must be able to *fail*: name the reading that is a
> rejection, not only the one that passes. A skill with no ledger has not passed Step 0's
> checkable test.

## Step 3 — Parameterise (method vs. opinion)

The rule that keeps a pack from being one shop's dogma ([[systems/packs]],
"Parameterisation"):

- **Method** stays in the pack's skills — invariant.
- **Parameters** (names, trackers, cadences) resolve from the instance's `.packs.yaml`
  `config:` block. Declare them in `pack.yaml` with defaults + `one_of` enums (pipe-
  separated, comma-free). Skills read config-first; `scripts/packs.sh config <pack>`
  resolves and validates.
- **Conventions** (rules, checklists, formats) ship as data the skills read, with
  instance overrides winning.
- **Profiles** — if the discipline has genuinely different modes (e.g. the agile pack's
  `scrum` vs `kanban`), ship each as `profiles/<name>.md` selected by `config: profile:`.
  "Choose the methodology" becomes one line; "change it" is an edit to instance data,
  never a fork.

## Step 4 — Declare dependencies (don't duplicate a sibling pack)

When a skill you are about to write already exists in another pack, **depend on it instead
of re-deriving it** — a second copy of a discipline diverges, and the divergence is silent.
Declare it in `pack.yaml` and say why:

```yaml
depends:
  - name: <other-pack>
    for: [<skill-it-consumes>]     # the names this pack actually calls
    reason: "<what would otherwise be duplicated>"
```

Then cite that skill by wikilink from the skills that use it, and add the **Dependency**
section to `PROVENANCE.md` and `README.md`. Mirror `depends:` in the registry entry so a
dependency can be resolved *before* the pack is cloned.

Rules ([[systems/packs]], "Dependencies between packs"):

- **Names, not version ranges.** A mounted pack is a pinned submodule — the pin *is* the
  version. Ranges would fight the pin.
- **Anything in `for:` must be listed in the dependency's `provides:`** — that is the
  dependency's public surface, and a collision on a provided name is an error rather than a
  silently skipped skill.
- **Depend on packs, not on instances.** If the thing you need is an estate's convention
  rather than a discipline, it is config — go back to Step 3.

## Step 5 — Provenance & curation

- **First-party** — author it; MIT; a `PROVENANCE`-style note in the README. **Vendored /
  third-party** — record the real upstream and license; never a silent fork.
- The pack must be **public-safe**: no instance data, ever (same boundary as the
  framework — [[systems/distribution]]).
- To list it in the curated registry ([[systems/packs.yaml]]), meet the bar: provenance
  named, license known (or `verify-at-add`), public-safe. `status: planned` until the
  repo publishes, then `available`.

## Step 6 — Verify

Check the manifest against the contract, then mount it into a **clean instance clone** and
prove it works before publishing:

- **Conformance** — `pack.yaml` validates against [[systems/pack.schema.json|pack.schema.json]],
  and every file in that schema's `required_files` exists. Do this first: it is cheap, and
  it catches the drift that reading another pack by eye does not.
- `scripts/packs.sh add <pack> <url>` (then by registry name once listed) — skills land
  in the union `skills/` and `.claude/skills/`; nested/plugin layouts resolve; collisions
  shadow as expected; declared dependencies resolve and mount.
- `scripts/packs.sh config <pack>` — defaults resolve, enums validate, a non-default
  profile resolves.
- Exercise one skill end-to-end against a real input; confirm its output is *checkable*
  against the discipline's standard (Step 0.3). If it isn't, the rigor standard is
  missing — go back to Step 1.

## Principles

- **Discipline, not dump.** A pack makes an agent behave like a competent practitioner —
  method *and* rigor, not a prompt pile.
- **Method in the pack, choices in the instance.** If changing a convention means editing
  the pack, you've hardcoded an opinion — move it to config/profiles.
- **One discipline, one provenance, public-safe.** Clean packs compose; muddy ones rot.
- **Prove it by mounting it.** A pack that hasn't been mounted into a clean clone and
  driven once is unverified.
