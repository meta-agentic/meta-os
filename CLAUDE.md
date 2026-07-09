# meta-os — Agentic OS framework

This repo is the **generic framework** of an Agentic OS: the skill backbone, the operating
model, and the vault conventions — with **no instance data**. A private *instance* repo
(project registry, memory, live automations) mounts these folders by symlink and is the
vault you actually open. This separation is the privacy boundary: everything here must stay
**public-safe by construction** — no repo names, trackers, paths, or promoted knowledge.

This file is appended to every prompt Claude Code runs inside this directory. The *how*
lives in [[systems/_index|systems/]]; load the specific system doc or skill you need
instead of re-deriving it.

## The model — skill backbone, not dashboard

Three layers, built bottom-up. Value lives in the lower two; the dashboard is last and
optional. (After chaseAI's Agentic OS; memory flow after Karpathy's LLM-wiki.)

| Layer | Folder | What it is |
|-------|--------|-----------|
| **1 · Skills & automation** | [[skills/_index\|skills/]] · automations (instance) | Codified, executable workflows. If you do it more than once, it becomes a skill. |
| **2 · Memory** | memory (instance; skeleton here) | Knowledge base. Karpathy flow: `raw → wiki → output`. |
| **3 · Interface** | (build last) | Obsidian graph + optional dashboard, only after 1 & 2 are stable. |

## Framework vs. instance

```
meta-os/  (this repo — PUBLIC-SAFE)      <instance>/  (private — the vault you open)
├── skills/      ← the skill library     ├── CLAUDE.md, _index.md  ← instance contract
├── systems/     ← how the OS operates   ├── projects/   ← estate registry
├── agents/      ← roster + patterns     ├── memory/     ← the live knowledge
├── templates/   ← note templates        ├── automations/← live routine rows
├── memory/      ← empty skeleton        ├── vaults/     ← federated project vaults
└── CLAUDE.md    ← this contract         └── skills,systems,templates,agents → (.)meta-os/*
```

Mounts are **symlinks per folder** — to the instance's `.meta-os/` submodule (default)
or a sibling checkout (developer mode; see [[systems/distribution]]) — so
vault-root-relative wikilinks (`[[skills/…]]`, `[[systems/…]]`) resolve identically in
both repos.

## Conventions (apply in framework and instance alike)

- **Every folder has an `_index.md`** — its table of contents. Add a line when you add a
  file; read it first when you enter a folder. Keeps navigation token-efficient at scale.
- **Skills live in `skills/` and only there.** Discovery is via symlinks
  (`~/.claude/skills/<name> → meta-os/skills/<name>`). Never create a second real copy.
- **Memory promotion is deliberate.** Capture lands in `memory/raw/`; only *promoted*
  notes (cleaned, front-mattered, linked) enter `memory/wiki/`. Don't cite `raw/`.
- **Link liberally** with `[[wikilinks]]`; a link to a not-yet-existing note is a TODO
  marker, not an error. Front-matter (`type:`, `tags:`) on every note.
- **Naming:** descriptive note names; tags lowercase `#type/subtype`; wikilinks by
  shortest path.
- Keep notes focused; split when a note outgrows one idea. Never commit secrets.
- **Instance data never enters this repo** — repo names, tracker ids, machine paths,
  business context, promoted knowledge all belong in the instance. **This applies to git
  metadata too, not just file content:** commit messages, PR titles/bodies, and issue
  references must never carry tracker IDs (e.g. Jira keys) or other instance
  identifiers — describe the change in plain language instead. This repo is public;
  commit history is permanent. Reference tracker IDs only in the private instance's own
  mirror/notes, never here.

## Entry points

- **Human:** open the *instance* as the Obsidian vault; start at its `_index.md`.
- **Agent:** read the instance `CLAUDE.md` (which defers here), then the `_index.md` of
  the folder you're working in, then the specific skill/system doc. Don't load everything.
