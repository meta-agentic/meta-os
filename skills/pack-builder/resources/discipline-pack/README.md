# meta-discipline-<pack>

A first-party [meta-os](https://github.com/meta-agentic/meta-os) **skill pack** codifying
the **<discipline>** — not a pile of <domain> facts, but a *method + a standard of rigor*
per branch that turns an agent into a competent practitioner (per
`meta-os/systems/pack-strategy.md`, the *<wedge>* wedge).

> A pack = a codified discipline: a repeatable **method** + a **standard of rigor** +
> **portability** across estates.

## Skills

| Skill | Discipline it codifies | Checkable output |
|-------|------------------------|------------------|
| [`<skill-a>`](skills/<skill-a>/SKILL.md) | <what it codifies> | <the ledger it emits> |
| [`<skill-b>`](skills/<skill-b>/SKILL.md) | <…> | <…> |

## The three-part test (why this is a pack)

1. **Recognizable** — <a practitioner would call it "how we actually work", concretely>.
2. **Portable** — parameterized by `pack.yaml` config (<the knobs>); welded to no single
   estate.
3. **Checkable** — <how each skill's output is verified against the discipline's own
   standard>.

## Configure

Set the pack's knobs in the instance's `.packs.yaml` `config:` block (see
`config.example.yaml`). Skills read config-first and fall back to documented defaults.

```yaml
packs:
  <pack>:
    config:
      profile: <default>      # <a> | <b>
      <knob>: <value>
```

Profiles (`profiles/*.md`) are named rigor bundles: **<a>** (<what it emphasises>) vs
**<b>** (<…>). <Or, when the discipline has no variants: "No profiles: this discipline
has no alternative methodologies to bundle." Say it — do not invent a split.>

## Dependencies

<Omit unless pack.yaml declares `depends:`.> This pack assumes **`<other-pack>`** is
mounted and reuses its `<skill>` rather than duplicating it. Declare both in the
instance's `.packs.yaml`; `scripts/packs.sh add <pack>` resolves the dependency.

## Install

```bash
# in a meta-os instance
scripts/packs.sh add <pack> https://github.com/meta-agentic/meta-discipline-<pack>
scripts/packs.sh config <pack>      # resolve/validate config
```

## Provenance & license

First-party (<author>). MIT — see `LICENSE` and `PROVENANCE.md`. Public-safe by
construction: no instance data.

## Registry entry (add to `meta-os/systems/packs.yaml`)

```yaml
  <pack>:
    repo: https://github.com/meta-agentic/meta-discipline-<pack>
    ref: main
    description: "<the pack.yaml description, trimmed>"
    provenance: first-party
    license: MIT
    depends: [<other-pack>]   # omit when none
    status: planned           # → available once main carries the skills
```
