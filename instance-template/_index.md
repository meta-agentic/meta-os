---
type: index
tags: [os, distribution, template]
---
# instance-template/ — what a fresh instance is instantiated from

The instance half of the one-repository layout ([[systems/distribution]]). Everything
under `root/` is copied, path for path, to the repository root by `scripts/bootstrap.sh`
on first run — and only on first run. After that the copies are the instance's own: the
framework never writes to those paths again, and this folder is never edited in an
instance.

| Path | What |
|------|------|
| `root/` | The payload. Each entry lands at the same path under the repository root. |
| `root/.claude/CLAUDE.md` | The **instance contract** — loaded by Claude Code alongside the root `CLAUDE.md` (the framework contract). Instance facts, authority order, instance rules. |
| `root/_index.md` | The vault home — the map of content a human opens first. |
| `root/projects/` · `root/memory/` · `root/automations/` · `root/vaults/` | The instance folders, each with its `_index.md`: registry, `raw → wiki → output`, routine rows, federated vaults. |
| `root/meta-os.config.json` | The estate config ([[systems/config]]) with the `instance` block bootstrap fills in. |
| `root/.packs.yaml` | The declared-packs manifest `scripts/packs.sh apply` reconciles to ([[systems/packs]]). |
| `root/.githooks.d/` · `root/.gitignore.instance` | The instance's **extension points** for git hooks and root-level ignore rules: the framework's `.githooks/` and `.gitignore` are framework files an upgrade replaces ([[systems/distribution]], "Extension points"). |
| `root/.obsidian/` | Obsidian vault settings: attachments under `memory/raw/attachments`, daily notes under `memory/raw/daily`, templates from `templates/`, graph colour groups per folder. |

## The two rules this folder encodes

1. **The framework never tracks an instance path.** For every entry `root/<x>`, the path
   `<x>` at the repository root is instance-owned. `scripts/validate_framework.py` fails
   if the framework ever commits one — that is what makes an upgrade unable to collide
   with an instance's files, by construction rather than by care.
2. **Bootstrap never overwrites.** `scripts/bootstrap.sh` copies an entry only when its
   root counterpart does not exist yet, so re-running it is safe and an instance that
   already carries a file keeps it.

## Placeholders

Bootstrap substitutes these in the copied files only — never here:

| Placeholder | Becomes |
|-------------|---------|
| `{{instance-name}}` | The instance name (`--name`, default: the checkout's directory name) |
| `{{bootstrapped}}` | The date of the first run, `YYYY-MM-DD` |
| `{{template-ref}}` | The framework commit whose `instance-template/` was instantiated — `scripts/upgrade.sh` reads it back from `meta-os.config.json` to report template drift |

## Evolving the template

Change `root/` here when every *future* instance should start differently. Existing
instances are not rewritten: `scripts/upgrade.sh` reports the diff of this folder since
each instance's `template` ref, and the operator applies what they want by hand. A change
that must reach *running* instances is framework mechanism and belongs in `skills/`,
`systems/`, `scripts/` or `hooks/` — not here.
