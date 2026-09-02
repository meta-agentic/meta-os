---
type: index
tags: [os, skills, layer1]
---
# Layer 1 — Skill Backbone

Codified, executable workflows. **This folder is the single authoritative home** for the
whole library — never create a second real copy; discovery is via symlinks.

> If you do it more than once, it should be a skill. Author new ones with
> [[skills/skill-builder/SKILL|skill-builder]].

## Core backbone — our standing operating skills

| Skill | Domain | Use for |
|-------|--------|---------|
| [[skills/agile-process/SKILL\|agile-process]] | Process | **→ moved to the [agile pack](https://github.com/meta-agentic/meta-discipline-agile)** — mount with `scripts/packs.sh add agile`; link resolves in instances with the pack mounted |
| [[skills/agile-swarm/SKILL\|agile-swarm]] | Process | **→ moved to the [agile pack](https://github.com/meta-agentic/meta-discipline-agile)** — same mount; deprecation rows kept for one minor version |
| [[skills/graphify/SKILL\|graphify]] | Memory | Turn any folder (code/docs/papers/media) into a navigable knowledge graph |
| [[skills/infoviz/SKILL\|infoviz]] | Interface | Choose the visual *form* for data before drawing it — encoding, complex-data method, trust gate |
| [[skills/skill-builder/SKILL\|skill-builder]] | Meta | Author one skill: the trigger contract, progressive disclosure, and the registration a skill is not finished without |
| [[skills/pack-builder/SKILL\|pack-builder]] | Meta | Author a new pack: apply the is-it-a-pack test, structure (pack.yaml/profiles), parameterise, provenance/registry, verify by mounting — see [[systems/pack-strategy]] |
| [[skills/bootstrap-instance/SKILL\|bootstrap-instance]] | Meta | One-time onboarding for a fresh instance repo: backlog/tracking model, first project, GitHub integration |
| `hooks-automation` | Automation | **→ removed, third-party.** It documented claude-flow's own hook CLI; install that upstream (`npx @claude-flow/cli@latest init`) if you want it. The framework's hook *policy* — staged per pack, never auto-wired — is in [[systems/packs]] |
| `swarm-orchestration` | Orchestration | **→ removed, third-party.** Coordination inside a session belongs to the host engine ([[systems/engine]]); the OS's own parallel model is [[systems/swarm-harness]], driven by the [agile pack](https://github.com/meta-agentic/meta-discipline-agile)'s `agile-swarm` |
| [[skills/multi-engine/SKILL\|multi-engine]] | Meta | Cross-provider headless fan-out via meta-cli (`claude`/`gemini`/`grok`/…); collect → `memory/raw/` — see [[systems/engine]] |

## What is deliberately not here

The core ships only what is part of the OS itself — bootstrapping, skill and pack authoring,
the graph, the engine surface. Two categories live elsewhere on purpose:

- **Domain and process skill sets are packs.** An agile method, a discipline, a third-party
  collection: mounted per instance from [[systems/packs.yaml|the registry]], pinned and
  updatable, never vendored here. See [[systems/packs]].
- **Third-party tooling is installed by its own installer.** The 30-skill claude-flow / Ruflo
  library this repo once vendored (`agentdb-*`, `v3-*`, `flow-nexus-*`, `github-*`, sparc,
  swarm and reasoningbank sets) was removed in 2026-08, and `hooks-automation`,
  `swarm-orchestration` and `ruflo-setup` followed. That upstream is a CLI ecosystem rather
  than a mountable collection — the evidence is recorded under "Not packs" in
  [[systems/packs]] — so the supported path is its own installer, opt-in, outside this repo.
  Full history in [[PROVENANCE]].

## Skill learnings — the improvement loop

Skills self-improve structurally, not by memory: each skill in active use gets **one
standing [[templates/skill-learnings|skill-learnings]] note** in the *instance*
(`memory/wiki/skills/<skill>-learnings.md`). Per-run [[templates/skill-note|skill-notes]]
feed it; when a learning generalizes beyond the instance, fold it into the skill's
`SKILL.md` here via [[skills/skill-builder/SKILL|skill-builder]] and remove it from the
note. Learnings never live in this folder — they are instance experience, and this repo
stays public-safe.

**For a skill that came from a mounted pack, the fold-back goes to the pack repo, not
here:** change it upstream, then adopt it with `scripts/packs.sh update <pack>` (a pin
bump, a reviewable commit). Editing `.packs/<name>/` in place is a detached submodule
change the next update discards. The full loop — including how to tell a *method* change
from one that is really a config knob, a profile, or a new skill — is in
[[systems/packs]], "Evolving a discipline".

## Adding a skill

1. Build/scaffold it with [[skills/skill-builder/SKILL|skill-builder]].
2. Put the authoritative version in `skills/<name>/SKILL.md`.
3. Add it to the core table above **and** a row in [[PROVENANCE]] with its origin and
   licence, in the same commit — no skill enters this folder without a recorded origin.
4. Discovery: skills must be reachable by Claude Code (user-level `~/.claude/skills`
   symlink or per-repo `.claude/skills` link — see [[systems/agentic-operating-model]]).
