# meta-os — Agentic OS framework

The **generic framework** of an Agentic OS built on Claude Code + Obsidian: a skill
backbone, an operating model for agent coordination, memory conventions, and note
templates — with **no instance data**. Your private *instance* repo (project registry,
live memory, automations, vault federation) mounts these folders by symlink and is the
vault you actually open.

> Design principle: **skill backbone, not dashboard.** The value is in codified skills and
> organized memory. The dashboard is the last 10% — built only once the backbone is solid.
> (After [chaseAI's Agentic OS](https://www.chaseai.io/blog/agentic-os-skill-backbone-not-dashboard)
> and Karpathy's `raw → wiki → output` LLM-wiki pattern.)

## Layers

1. **Skills & automation** — [`skills/`](skills/): the executable workflow library.
   Automations (scheduled/triggered routines) are catalogued per instance.
2. **Memory** — `raw/` (captures) → `wiki/` (refined reference) → `output/`
   (deliverables). The skeleton + promotion discipline live here; the content lives in
   your instance.
3. **Interface** — the Obsidian graph, plus an optional dashboard: see
   [`systems/interface-layer.md`](systems/interface-layer.md) for the contract and
   [meta-os-dashboard](https://github.com/mova77/meta-os-dashboard) for a reference
   implementation (sprint lanes, a live knowledge graph, memory pipeline, ontology
   linting). [`systems/ontology.md`](systems/ontology.md) defines the shared vocabulary
   layers 2 and 3 read from.

Plus [`systems/`](systems/) (how the OS operates), [`agents/`](agents/) (roster +
coordination patterns), [`templates/`](templates/).

## Setting up an instance

Fastest path: use
**[meta-os-instance-template](https://github.com/mova77/meta-os-instance-template)** —
click "Use this template" to get a private instance repo with the folder skeleton,
`_index.md` tables of contents, and framework symlinks already wired. Its README covers
cloning it as a sibling of `meta-os` and the remaining setup steps.

To build one by hand instead:

1. Create a private repo with `CLAUDE.md`, `_index.md`, `projects/`, `memory/`,
   `automations/`, `vaults/`.
2. Mount the framework as sibling symlinks: `skills/ → ../meta-os/skills`, likewise
   `systems/`, `templates/`, `agents/`. Vault-root-relative wikilinks then resolve
   identically in both repos.
3. Open the instance as your Obsidian vault.
4. For machine-global skill discovery in Claude Code:
   `ln -s $(pwd)/meta-os/skills/<name> ~/.claude/skills/<name>` per skill.

## Conventions

- Every folder has an `_index.md` table of contents — update it when you add a file.
- Cross-link with `[[wikilinks]]`; front-matter (`type:`, `tags:`) on every note.
- `memory/raw/` is disposable scratch; promote to `memory/wiki/` to make knowledge durable.
- **No instance data in this repo** — it stays public-safe by construction.

## License & provenance

MIT ([LICENSE](LICENSE)). The skill library includes MIT-licensed content from
[claude-flow / Ruflo](https://github.com/ruvnet/claude-flow) (rUv) and
[Graphify Labs](https://github.com/safishamsi/graphify) — full per-skill origin table in
[PROVENANCE.md](PROVENANCE.md).

## Status

Framework v0 — skill library (37 skills), operating-model docs, memory conventions,
templates. Extracted from a working single-vault scaffold.
