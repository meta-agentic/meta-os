---
type: index
tags: [os, validation, tests, packs]
---
# tests/fixtures/ — the control packs

Two packs, deliberately: a gate that only ever sees passing input proves nothing about
what it rejects. Both are checked by pointing `scripts/validate_pack.py` at them
explicitly; the in-repo sweep refuses to descend into this folder
(`EXCLUDED_FROM_DISCOVERY`), because one of these packs is non-conformant by design.

| Pack | Role | Expected verdict |
|------|------|------------------|
| `conforming-pack/` | positive control — ships every required file, valid manifest, well-shaped skill, estate-neutral | **pass**, including under `--strict` |
| `violating-pack/` | negative control — four violation classes at once | **fail** |

## What `violating-pack/` is expected to raise

Each row is asserted in `tests/test_validate_pack.py`. Fixing one here without updating
that test is how the gate quietly stops proving anything.

| Check | The violation |
|-------|---------------|
| `pack-schema` | `description:` is shorter than the contract's minimum |
| `pack-required-file` | no `PROVENANCE.md` |
| `pack-skill-shape` | skill front-matter has no `description:`; body has no `## Anti-patterns` |
| `estate-neutral` | the LICENSE copyright holder is named in a skill file, where the ratified exemption does not reach |

## Editing these packs

`conforming-pack/` is a worked example of the contract in `systems/pack.schema.json`,
so hold it to the standard of a published pack. Keep both fixtures estate-neutral in the
literal sense — the holder names here are invented, and nothing that would be unsafe in
a public repository is ever committed; probes that need such a string build it at run
time. See [[tests/_index|tests/]].
