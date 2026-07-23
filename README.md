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

## Not just for software

The OS is **domain-agnostic**: the three layers — codified skills, `raw → wiki →
output` memory, a graph/dashboard over both — fit any sustained knowledge work. A
software estate is just the best-documented instance so far. Equally natural instances:

- **Deep scientific research** — papers captured to `raw/`, promoted to a linked
  `wiki/`, syntheses and reports delivered to `output/`; graphify over the literature.
- **Systems design & engineering** — requirements, trade studies, and design decisions
  as the pipeline; the registry tracks subsystems instead of repos.
- **Working an existing Obsidian vault** — mount the OS around what you already have
  (vault federation) and get promotion discipline, automations, and observability over it.
- Content production, legal casework, ops runbooks — anywhere "capture → refine →
  deliver" repeats.

Domain-specific *process* lives in mountable [packs](systems/packs.md), not in the
core — the agile/Scrum set is simply the first such opinion, and choosing zero packs is
a fully supported install.

## Layers

1. **Skills & automation** — [`skills/`](skills/): the executable workflow library.
   Automations (scheduled/triggered routines) are catalogued per instance.
2. **Memory** — `raw/` (captures) → `wiki/` (refined reference) → `output/`
   (deliverables). The skeleton + promotion discipline live here; the content lives in
   your instance.
3. **Interface** — the Obsidian graph, plus an optional dashboard: see
   [`systems/interface-layer.md`](systems/interface-layer.md) for the contract and
   [meta-os-dashboard](https://github.com/meta-agentic/meta-os-dashboard) for a reference
   implementation (sprint lanes, a live knowledge graph, memory pipeline, ontology
   linting). [`systems/ontology.md`](systems/ontology.md) defines the shared vocabulary
   layers 2 and 3 read from.

Plus [`systems/`](systems/) (how the OS operates), [`agents/`](agents/) (roster +
coordination patterns), [`templates/`](templates/).

## Prerequisites

- **[Claude Code](https://claude.com/claude-code)** — required (default engine); runs the skills and reads `CLAUDE.md`.
- **[Obsidian](https://obsidian.md)** — optional; lets you browse the vault as a graph.
  Everything works from Claude Code alone without it.
- **[meta-cli](https://github.com/meta-agentic/meta-cli)** — optional; multi-engine headless fan-out
  (`claude` / `gemini` / `grok` / …). Contract: [`systems/engine.md`](systems/engine.md);
  skill: [`skills/multi-engine/`](skills/multi-engine/).
- **Python 3** — optional; only used by the [`graphify`](skills/graphify/) skill, which
  self-installs its one dependency (`pip install graphifyy`) the first time it runs.
  Nothing to install up front.
- **git** (+ [`gh`](https://cli.github.com/), optional) — to clone your instance below.

## Setting up an instance

You don't clone this repo directly — you create a **private instance** from
[meta-os-instance-template](https://github.com/meta-agentic/meta-os-instance-template) and the
framework comes with it as the `.meta-os` git submodule. **One clone and you're
running:**

```bash
# 1. create your private instance from the template
gh repo create <you>/<instance-name> --template meta-agentic/meta-os-instance-template --private

# 2. clone it — the framework lands in .meta-os/ at a pinned version, mounts pre-wired
git clone --recursive git@github.com:<you>/<instance-name>.git
cd <instance-name>
```

That's the default (**single-clone**) mode. Framework developers can instead point the
mounts at a sibling `../meta-os` checkout — see [`systems/distribution.md`](systems/distribution.md)
for all consumption modes (single-clone, sibling, and the planned container image), and
why the framework and instance stay separate repos.

Then:

1. Open `<instance-name>/` as your Obsidian vault — wikilinks resolve across the
   framework mount since they're vault-root-relative (`.meta-os/` stays out of the graph).
2. Rename `{{instance-name}}` and fill in `CLAUDE.md` / `_index.md` with your instance facts.
3. In Claude Code, run the [`bootstrap-instance`](skills/bootstrap-instance/SKILL.md)
   skill — a one-time onboarding conversation that decides your backlog/tracking model
   (none / local JSON / Jira-integrated), offers **skill packs** to mount
   ([`systems/packs.md`](systems/packs.md)), registers your first project, and optionally
   wires up its GitHub repo.

## Memory topologies

`raw → wiki → output` is the invariant. **Where those folders live — and how they nest —
is your choice**, because adopters arrive from very different places:

- a **clean slate**, wanting one self-contained repo;
- an **existing estate** whose repos already carry their own docs, where nothing should move;
- a preference to **centralize** every project's memory in one place.

All three are first-class. The layout is declared as data, and the tooling (dashboard,
graph, sync scripts) reads that declaration instead of assuming a shape. **Write nothing
and you get the simplest option** — see [Defaults](#defaults-and-changing-your-mind).

### Choice 1 — where the bytes live

Each storage location is a **root**:

| Root style | Bytes live in | Best when |
|---|---|---|
| **In-instance** | the instance repo itself | Clean slate. One clone is complete — fully portable, works on mobile Obsidian, trivial to back up. |
| **Shared vault repo** | one separate repo, all projects | You want the instance small, and one history covering all knowledge. |
| **In the project repos** | each project's own repo | Brownfield. Docs are authored and reviewed alongside their code and must not move. |

You can mix them — most mature estates do.

### Choice 2 — how each root nests

Each root declares its own `layout`:

```
"flat"                    "tier/project"            "project/tier"

memory/                   memory/                   memory/
├── raw/                  ├── raw/                  ├── alpha/
│   └── note.md           │   ├── alpha/            │   ├── raw/
├── wiki/                 │   └── beta/             │   ├── wiki/
│   └── topic.md          ├── wiki/                 │   └── output/
└── output/               │   ├── alpha/            └── beta/
    └── report.md         │   └── beta/                 ├── raw/
                          └── output/                   ├── wiki/
                              ├── alpha/                └── output/
                              └── beta/
```

| Layout | Pick it when your common question is… |
|---|---|
| `flat` | *"what's in my vault?"* — one project, or no need for per-project separation. Simplest. |
| `tier/project` | *"what's in flight across **everything**?"* — one glob per stage. Suits daily cross-project standups. |
| `project/tier` | *"everything about **project X**"* — and it keeps a project's memory trivially extractable if it's ever spun out. |

Nothing stops you changing later; it's a directory move plus a one-line config edit.

### Canon vs. navigation

Two kinds of mount, and the difference is load-bearing:

- **`roots` are canon** — counted as your promotion pipeline. Progress is measured here.
- **`federated` are navigation** — mounted so they appear in the graph and are reported as
  *context*, but never counted as pipeline progress.

This is the framework's promotion rule expressed as configuration: federation gives you
**one graph without moving a single file**; promotion is what makes knowledge **canon**.
A brownfield estate can therefore adopt the OS on day one — mount everything, move
nothing — and promote deliberately over time. See
[`systems/memory-layer.md`](systems/memory-layer.md).

### Worked examples

**A · Clean slate** — everything in the instance, no per-project split. This is the
default; the block is shown only to make it explicit.

```jsonc
"memory": {
  "roots": [
    { "label": "instance", "path": "${instance}/memory", "layout": "flat" }
  ]
}
```

**B · Brownfield** — a small in-instance pipeline for your own notes, with existing
project repos mounted read-only for navigation. Nothing moves out of those repos.

```jsonc
"memory": {
  "roots": [
    { "label": "instance", "path": "${instance}/memory", "layout": "flat" }
  ],
  "federated": [
    { "label": "platform-docs", "path": "${code}/platform/docs" },
    { "label": "research-vault", "path": "${code}/research/vault" }
  ]
}
```

**C · Centralized** — one shared vault repo holds every project's memory, nested
stage-first because the daily question is cross-project.

```jsonc
"memory": {
  "roots": [
    { "label": "estate", "path": "${code}/vault", "layout": "tier/project" }
  ]
}
```

**D · Hybrid** — what estates tend to converge on: a central vault for canon, plus
federated project docs for navigation.

```jsonc
"memory": {
  "roots": [
    { "label": "estate",   "path": "${code}/vault",       "layout": "tier/project" },
    { "label": "instance", "path": "${instance}/memory",  "layout": "flat" }
  ],
  "federated": [
    { "label": "platform-docs", "path": "${code}/platform/docs" }
  ]
}
```

`${...}` entries are reusable path variables, so relocating a checkout is a one-line change.

### Defaults and changing your mind

- **No `memory` block at all** → flat, in-instance (`<instance>/memory/{raw,wiki,output}`)
  plus anything symlinked under `vaults/` treated as federated. Example A, without writing it.
- **Adding a block never breaks an existing instance** — absent keys fall back to that default.
- **Switching layout later** is `git mv` plus a config edit. Because promotion moves a file
  between stage folders, `git log --follow` on any note replays its whole
  `raw → wiki → output` history — a property worth preserving whichever layout you pick.

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
