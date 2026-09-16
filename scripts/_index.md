---
type: index
tags: [os, scripts, validation]
---
# scripts/ — the framework's own gate

Executable checks this repo runs against **itself**, and the one checker every **pack**
in the estate is held to. The framework is the public artifact of the estate: it states
invariants about itself in [[CLAUDE|CLAUDE.md]], [[PROVENANCE]], `README.md` and the
`_index.md` files, and this is what keeps those statements true.

| File | What |
|------|------|
| `validate_framework.py` | The self-check. Skill registration (provenance row + catalog entry), catalog entries that resolve on disk, `systems/*.md` front-matter against [[systems/ontology]], the `_index.md` convention, a public-safety scan for instance identifiers, and derivable count claims. |
| `framework-baseline.txt` | Accepted pre-existing debt — the ratchet. A violation listed here warns; anything else is an error. Debt can be paid down, never grown. |
| `validate_pack.py` | The pack conformance gate — the **single home** of the checker. `pack.yaml` against [[systems/pack.schema.json\|pack.schema.json]], the `required_files` checklist, the per-skill shape, `meta-os.config.json`, and the estate-neutral scan (instance identifiers, with the ratified LICENSE-holder exemption). Takes a pack directory, so it works against a checkout of any pack repository. |
| `pack-baseline.txt` | The same ratchet for packs. `estate-neutral` and `checklist-placeholder` can never enter it. |

## Running it

```bash
python3 scripts/validate_framework.py              # gate: new violations fail, known debt warns
python3 scripts/validate_framework.py --strict     # every warning becomes an error (cleanup pass)
python3 scripts/validate_framework.py --update-baseline   # re-record accepted debt

python3 scripts/validate_pack.py                   # every pack that lives inside this repo
python3 scripts/validate_pack.py ../some-pack      # one pack, from anywhere on disk
python3 -m unittest discover -s tests              # the gates' own tests — see [[tests/_index|tests/]]
```

Both gates run in CI (`.github/workflows/check.yml`), where they cannot be skipped. A
pack in **its own repository** runs the same `validate_pack.py` by calling
`.github/workflows/pack-conformance.yml` from a one-file caller workflow — see
[[systems/packs]]. No pack's conformance depends on a local copy of anything.

**Enable the pre-commit hook once per clone** — hooks are not carried by a clone:

```bash
git config core.hooksPath .githooks
```

The mirror of this gate for a vault's items is that repo's own `scripts/validate_items.py`;
the two are deliberately shaped alike.
