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
| [[skills/skill-builder/SKILL\|skill-builder]] | Meta | Author new skills with correct frontmatter + progressive disclosure |
| [[skills/pack-builder/SKILL\|pack-builder]] | Meta | Author a new pack: apply the is-it-a-pack test, structure (pack.yaml/profiles), parameterise, provenance/registry, verify by mounting — see [[systems/pack-strategy]] |
| [[skills/bootstrap-instance/SKILL\|bootstrap-instance]] | Meta | One-time onboarding for a fresh instance repo: backlog/tracking model, first project, GitHub integration |
| [[skills/hooks-automation/SKILL\|hooks-automation]] | Automation | Pre/post-task hooks, session mgmt, git + memory coordination — vendored (claude-flow), held back pending a native replacement, see [[PROVENANCE]] |
| [[skills/swarm-orchestration/SKILL\|swarm-orchestration]] | Orchestration | Multi-agent parallel execution, dynamic topology — vendored (claude-flow), held back pending a native replacement, see [[PROVENANCE]] |
| [[skills/multi-engine/SKILL\|multi-engine]] | Meta | Cross-provider headless fan-out via meta-cli (`claude`/`gemini`/`grok`/…); collect → `memory/raw/` — see [[systems/engine]] |

## Library — full catalog

Empty as of 2026-08-02: the vendored claude-flow/Ruflo skill set (agentdb-*, v3-*,
flow-nexus-*, github-*, sparc-methodology, swarm-advanced, stream-chain,
pair-programming, verification-quality, reasoningbank-agentdb,
reasoningbank-intelligence, browser) was stripped from core — see [[PROVENANCE]]. This
repo doesn't repackage third-party skills with provenance tracking; if you want that
tooling, install claude-flow/Ruflo through its own canonical installer, opt-in, outside
this repo.

Promote a library skill into the core table when it becomes part of the standing operating
model; prune it when it proves dead weight.

## Skill learnings — the improvement loop

Skills self-improve structurally, not by memory: each skill in active use gets **one
standing [[templates/skill-learnings|skill-learnings]] note** in the *instance*
(`memory/wiki/skills/<skill>-learnings.md`). Per-run [[templates/skill-note|skill-notes]]
feed it; when a learning generalizes beyond the instance, fold it into the skill's
`SKILL.md` here via [[skills/skill-builder/SKILL|skill-builder]] and remove it from the
note. Learnings never live in this folder — they are instance experience, and this repo
stays public-safe.

## Adding a skill

1. Build/scaffold it with [[skills/skill-builder/SKILL|skill-builder]].
2. Put the authoritative version in `skills/<name>/SKILL.md`.
3. Add it to the core table (or the library catalog) above.
4. Discovery: skills must be reachable by Claude Code (user-level `~/.claude/skills`
   symlink or per-repo `.claude/skills` link — see [[systems/agentic-operating-model]]).
