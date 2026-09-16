---
type: index
tags: [os, home, framework]
---
# ⚙️ meta-os — Agentic OS framework

Map of content for the **framework**. If you're operating the OS, open the *instance*
vault instead — this repo is the generic layer it mounts.

## What's here

| Folder | What |
|--------|------|
| [[skills/_index\|skills/]] | The skill library — Layer 1 backbone |
| [[systems/_index\|systems/]] | How the OS operates — operating model, memory, process & swarm harnesses |
| [[hooks/_index\|hooks/]] | Harness-executed event scripts — shipped, never auto-wired |
| [[pipeline/_index\|pipeline/]] | The autonomous swarm loop, deterministic half — ready set, regulator, reflection, speculation, ledger; an instance supplies config and a harness |
| [[agents/_index\|agents/]] | Agent roster + coordination patterns |
| [[templates/_index\|templates/]] | Note templates |
| memory/ | Empty `raw → wiki → output` skeleton with conventions — instances own the live one |
| [[scripts/_index\|scripts/]] | The framework's own self-check gate (wired as `.githooks/pre-commit`) |

## What's deliberately NOT here

Project registries, live memory, automation rows, vault federations — all instance data.
The framework stays **public-safe by construction**; see [[CLAUDE|CLAUDE.md]].

## Using the framework

1. Create a private instance repo (`CLAUDE.md`, `_index.md`, `projects/`, `memory/`,
   `automations/`, `vaults/`).
2. Mount this repo's folders as sibling symlinks: `skills/ → ../meta-os/skills`, same for
   `systems/`, `templates/`, `agents/`.
3. Open the instance as your Obsidian vault; point `~/.claude/skills/<name>` symlinks at
   `meta-os/skills/<name>` for machine-global skill discovery.
