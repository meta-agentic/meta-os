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

## Prerequisites

- **[Claude Code](https://claude.com/claude-code)** — required; runs the skills and reads `CLAUDE.md`.
- **[Obsidian](https://obsidian.md)** — optional; lets you browse the vault as a graph.
  Everything works from Claude Code alone without it.
- **Python 3** — optional; only used by the [`graphify`](skills/graphify/) skill, which
  self-installs its one dependency (`pip install graphifyy`) the first time it runs.
  Nothing to install up front.
- **git** (+ [`gh`](https://cli.github.com/), optional) — to clone the two repos below.

## Setting up the two repos

`meta-os` (this repo) and your private instance must sit **as siblings** in the same
parent folder — the instance's `skills/`, `systems/`, `templates/`, `agents/` are
relative symlinks (`../meta-os/...`).

```bash
mkdir agentic-os && cd agentic-os

# 1. the public framework
git clone git@github.com:mova77/meta-os.git

# 2. your private instance — from the template (fastest)
gh repo create <you>/<instance>-os --template mova77/meta-os-instance-template --private --clone
cd <instance>-os
```

No `gh` / prefer to build it by hand? Create a private repo with `CLAUDE.md`,
`_index.md`, `projects/`, `memory/{raw,wiki,output}/`, `automations/`, `vaults/`, then
symlink `skills/ systems/ templates/ agents/` to `../meta-os/<same name>`.

Then:

1. Open `<instance>-os/` (**not** `meta-os/`) as your Obsidian vault — wikilinks resolve
   across both repos since they're vault-root-relative.
2. Fill in the new repo's `CLAUDE.md` / `_index.md` with your instance facts.
3. *(optional)* machine-global skill discovery in Claude Code:
   ```bash
   for s in ../meta-os/skills/*/; do ln -s "$(pwd)/$s" ~/.claude/skills/"$(basename "$s")"; done
   ```
4. In Claude Code, run the [`bootstrap-instance`](skills/bootstrap-instance/SKILL.md)
   skill — a one-time onboarding conversation that decides your backlog/tracking model
   (none / local JSON / Jira-integrated), registers your first project, and optionally
   wires up its GitHub repo.

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
