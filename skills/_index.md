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
| [[skills/agile-process/SKILL\|agile-process]] | Process | Backlog↔Jira reconciliation, ceremonies, story transitions, sprint open/close (generalized: `project <space>`) |
| [[skills/agile-swarm/SKILL\|agile-swarm]] | Process | Running a sprint as parallel multi-lane worktree-isolated agent swarms |
| [[skills/graphify/SKILL\|graphify]] | Memory | Turn any folder (code/docs/papers/media) into a navigable knowledge graph |
| [[skills/skill-builder/SKILL\|skill-builder]] | Meta | Author new skills with correct frontmatter + progressive disclosure |
| [[skills/hooks-automation/SKILL\|hooks-automation]] | Automation | Pre/post-task hooks, session mgmt, git + memory coordination |
| [[skills/swarm-orchestration/SKILL\|swarm-orchestration]] | Orchestration | Multi-agent parallel execution, dynamic topology |
| [[skills/stream-chain/SKILL\|stream-chain]] | Orchestration | Stream-JSON multi-agent pipelines & sequential workflows |
| [[skills/pair-programming/SKILL\|pair-programming]] | Dev | Driver/navigator pairing with live verification |
| [[skills/verification-quality/SKILL\|verification-quality]] | Quality | Truth scoring, quality gates, automatic rollback |
| [[skills/reasoningbank-intelligence/SKILL\|reasoningbank-intelligence]] | Learning | Trajectory tracking, pattern distillation, adaptive learning |
| [[skills/dual-mode/README\|dual-mode]] | Meta | Claude Code + headless Codex hybrid orchestration — ⚠️ unverified provenance, see [PROVENANCE](../PROVENANCE.md) |

## Library — full catalog

| Family | Skills |
|--------|--------|
| **agentdb-*** | advanced · learning · memory-patterns · optimization · vector-search |
| **github-*** | code-review · multi-repo · project-management · release-management · workflow-automation |
| **v3-*** | cli-modernization · core-implementation · ddd-architecture · integration-deep · mcp-optimization · memory-unification · performance-optimization · security-overhaul · swarm-coordination |
| **flow-nexus-*** | neural · platform · swarm |
| **misc** | browser · reasoningbank-agentdb · sparc-methodology · swarm-advanced |

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
