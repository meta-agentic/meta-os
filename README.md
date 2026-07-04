# meta-os — our Agentic OS

An **Agentic OS**: the meta-layer that sits above all our repos and holds what outlives
any single one — a **skill backbone**, a **memory** (Obsidian knowledge base), an **agent
roster**, and a **project registry**. Built on Claude Code + Obsidian.

> Design principle: **skill backbone, not dashboard.** The value is in codified skills and
> organized memory. The dashboard is the last 10% — built only once the backbone is solid.
> (After [chaseAI's Agentic OS](https://www.chaseai.io/blog/agentic-os-skill-backbone-not-dashboard)
> and Karpathy's `raw → wiki → output` LLM-wiki pattern.)

## Layers

1. **Skills & automation** — [`skills/`](skills/) (canonical, executable workflows) and
   [`automations/`](automations/) (scheduled/triggered routines).
2. **Memory** — [`memory/`](memory/): `raw/` (captures) → `wiki/` (refined reference) →
   `output/` (deliverables).
3. **Interface** — the Obsidian graph; a dashboard is future work.

Plus registries: [`projects/`](projects/) (a node per repo), [`agents/`](agents/) (the
roster), [`systems/`](systems/) (how the OS runs).

## Using it

- **As a human:** open this folder as an Obsidian vault. Start at [`_index.md`](_index.md).
- **As an agent:** [`CLAUDE.md`](CLAUDE.md) is appended to every prompt run inside this
  directory — it's the contract. Read it, then the `_index.md` of the folder you're in.

## Conventions

- Every folder has an `_index.md` table of contents — update it when you add a file.
- Cross-link everything with Obsidian `[[wikilinks]]`.
- Front-matter (`type:`, `tags:`) on every note; templates live in [`templates/`](templates/).
- `memory/raw/` is disposable scratch; promote to `memory/wiki/` to make knowledge durable.

## Status

Scaffold v0 — structure, root contract, canonical skill backbone, and project registry are
in place. Populate `memory/wiki/` and grow the skill set from here.
