---
type: index
tags: [os, scripts, validation]
---
# scripts/ — the framework's own gate

Executable checks this repo runs against **itself**. The framework is the public
artifact of the estate: it states invariants about itself in [[CLAUDE|CLAUDE.md]],
[[PROVENANCE]], `README.md` and the `_index.md` files, and this is what keeps those
statements true.

| File | What |
|------|------|
| `validate_framework.py` | The self-check. Skill registration (provenance row + catalog entry), catalog entries that resolve on disk, `systems/*.md` front-matter against [[systems/ontology]], the `_index.md` convention, a public-safety scan for instance identifiers, and derivable count claims. |
| `framework-baseline.txt` | Accepted pre-existing debt — the ratchet. A violation listed here warns; anything else is an error. Debt can be paid down, never grown. |

## Running it

```bash
python3 scripts/validate_framework.py              # gate: new violations fail, known debt warns
python3 scripts/validate_framework.py --strict     # every warning becomes an error (cleanup pass)
python3 scripts/validate_framework.py --update-baseline   # re-record accepted debt
```

**Enable the pre-commit hook once per clone** — hooks are not carried by a clone:

```bash
git config core.hooksPath .githooks
```

The mirror of this gate for a vault's items is that repo's own `scripts/validate_items.py`;
the two are deliberately shaped alike.
