---
type: index
tags: [os, home, moc]
---
# 🧠 {{instance-name}} — Agentic OS Home

<!-- TODO: rename this file's H1 to your instance name if bootstrap's guess was wrong;
     delete this comment. -->

The map of content for this OS instance. This vault is the meta-layer above every
project — the instance contract is `.claude/CLAUDE.md`, the framework contract is
[[CLAUDE|CLAUDE.md]]. Skills, systems, templates and agents are the framework's folders
at the root of this same repository, kept current by `scripts/upgrade.sh`.

## The three layers

> **Skill backbone, not dashboard.** Value is bottom-up: skills → memory → interface.

- **Layer 1 — Skills & automation** → [[skills/_index|skills/]] · [[automations/_index|automations/]]
- **Layer 2 — Memory** → [[memory/_index|memory/]] (`raw → wiki → output`)
- **Layer 3 — Interface** → the Obsidian graph (open the graph view); optionally, the
  [meta-os-dashboard](https://github.com/meta-agentic/meta-os-dashboard) observability app
  (`scripts/bootstrap.sh --dashboard` installs and points it at this instance)

## Registries

| Registry | What |
|----------|------|
| [[projects/_index\|projects/]] | Every repo we run, as a node — purpose, stack, entry points |
| [[vaults/_index\|vaults/]] | Federated project vaults, symlinked into this graph |
| [[agents/_index\|agents/]] | The agent roster + coordination patterns |
| [[systems/_index\|systems/]] | How the OS itself operates — process, swarm, memory |

## Quick start

- **Turn a folder into a knowledge graph** → [[skills/graphify/SKILL|graphify]] skill
- **Author a new skill** → [[skills/skill-builder/SKILL|skill-builder]] skill
- **Mount a discipline** → `scripts/packs.sh add <name>` from [[systems/packs.yaml|the registry]]
- **Capture something new** → drop it in [[memory/raw/_index|memory/raw/]], promote later
- **Add your first project** → copy [[templates/project|the project template]] into
  [[projects/_index|projects/]]
- **Take a framework update** → `scripts/upgrade.sh`

## Where things go

- A repeated workflow → a **skill** ([[skills/_index]])
- A scheduled/triggered routine → an **automation** ([[automations/_index]])
- A capture, note, or Claude output → **memory/raw**, promote to **memory/wiki**
- A finished artifact → **memory/output**
- A new repo → a node in **projects/**
