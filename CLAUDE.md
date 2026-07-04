# meta-os — the Agentic OS

This vault **is** the operating system. It is the meta-layer that sits above every
project ([[isohub]], [[vectis]], [[tessera]], [[io.space.infra]], [[isohub-assets]],
[[herakles]], [[scrum]]) and holds the parts that outlive any single repo: the **skill
backbone**, the **memory**, the **agent roster**, and the **project registry**.

This file is appended to every prompt Claude Code runs inside this directory.
It is the always-on contract. The *how* lives in [[systems/_index|systems/]]; load the specific
system doc or skill you need instead of re-deriving it.

## The model — skill backbone, not dashboard

Three layers, built bottom-up. Value lives in the lower two; the dashboard is last and
optional.

| Layer | Folder | What it is |
|-------|--------|-----------|
| **1 · Skills & automation** | [[skills/_index\|skills/]] · [[automations/_index\|automations/]] | Codified, executable workflows. If you do it more than once, it becomes a skill. |
| **2 · Memory** | [[memory/_index\|memory/]] | Knowledge base. Karpathy flow: `raw → wiki → output`. |
| **3 · Interface** | (not built yet) | Obsidian graph + optional dashboard. Build only after 1 & 2 are stable. |

Supporting registries: [[projects/_index|projects/]] (one node per repo) ·
[[agents/_index|agents/]] (the roster) · [[systems/_index|systems/]] (how the OS runs).

## Folder conventions

```
meta-os/
├── CLAUDE.md            ← this contract (appended to every prompt here)
├── _index.md            ← OS home / map of content — start here
├── skills/              ← Layer 1: canonical skill backbone (authoritative copies)
├── automations/         ← Layer 1: scheduled / on-demand routine catalog
├── memory/              ← Layer 2: raw → wiki → output
│   ├── raw/             ← captures, Claude outputs, scratch. Cheap, disposable.
│   ├── wiki/            ← refined, indexed, durable reference. The knowledge.
│   └── output/          ← finished deliverables (docs, decks, reports)
├── projects/            ← one node per repo — the meta-OS registry
├── vaults/              ← symlinks to federated project vaults (isohub, herakles)
├── agents/              ← agent roster + coordination patterns
├── systems/             ← how the OS itself operates (process, swarm, memory)
└── templates/           ← note templates
```

**Every folder has an `_index.md`** — its table of contents. When you add a file, add a
line to the folder's `_index.md`. When you enter a folder, read its `_index.md` first —
this keeps navigation token-efficient as the vault grows past 100+ files.

## Rules of the OS

- **Skills live here and only here.** `skills/` is the single copy. Discovery everywhere
  is via symlinks: `~/.claude/skills/<name> → meta-os/skills/<name>` (machine-global,
  every repo sees them). `scrum/.claude/skills` is retired. Never create a second real copy.
- **Project vaults are symlinked, not absorbed.** `vaults/isohub → isohub/isohub` and
  `vaults/herakles → Herakles/herakles-vault` join the Obsidian graph while their files stay
  owned by (and colocated with) their repos. Edit their notes in their own conventions.
- **Memory promotion is deliberate.** New knowledge lands in `memory/raw/`. It only
  becomes durable reference when a human/agent *promotes* it to `memory/wiki/` (cleaned,
  linked, indexed). Don't cite `raw/` as ground truth.
- **Projects are nodes, not clones.** A `projects/<name>.md` node points *at* the repo
  (path, purpose, stack, entry points, live links) — it does not duplicate the code.
- **Link liberally.** Use `[[wikilinks]]` for every cross-reference so the graph stays
  connected. A link to a note that doesn't exist yet is a valid TODO marker, not an error.
- **Front-matter on every note.** At minimum `type:` and `tags:`. Use `templates/`.
- **Authority order for process/backlog work:** Jira → `scrum/**/backlog.json` →
  the [[skills/agile-process/SKILL|agile-process]] skill → these invariants. On conflict, the higher source wins.
- Keep notes focused; split when a note outgrows one idea. Never commit secrets.

## Naming

- Notes: `kebab-or-Title Case.md`, descriptive. Numbered prefixes (`012-`) optional for
  ordered sequences (mirrors [[herakles]]-vault convention).
- Tags: lowercase, `#type/subtype` (e.g. `#source/paper`, `#system/process`).
- Wikilinks by shortest path; Obsidian resolves them.

## Entry points

- **Human:** start at [[_index]] (the map of content) or `README.md`.
- **Agent:** read this file, then the `_index.md` of the folder you're working in, then
  the specific skill/system doc. Don't load the whole vault.
