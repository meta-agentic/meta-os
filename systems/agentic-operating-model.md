---
type: system
tags: [os, system, operating-model]
---
# Agentic Operating Model

How work actually flows through the OS.

## The loop

```
intent → skill → agent(s) → memory
   ▲                            │
   └──────── promotion ─────────┘
```

1. **Intent** arrives (a request, a ceremony, a schedule firing).
2. A **skill** ([[skills/_index]]) says *what* to do — the codified workflow.
3. **Agent(s)** ([[agents/_index]]) do it — solo for simple work, a coordinated team for
   anything spanning 3+ files / multiple concerns.
4. Results land in **memory** ([[memory/_index]]) as `raw/`, and durable findings get
   **promoted** to `wiki/`, feeding the next intent.

## Solo vs. swarm

| Do NOT swarm | DO swarm |
|--------------|----------|
| single-file edits, 1–2 line fixes | 3+ files, new features |
| docs/config tweaks, questions | cross-module refactors, API changes |
| | security, performance, whole sprints |

## Coordination — SendMessage-first

Named agents message each other directly; no polling, no shared-state races. Spawn the
whole team in **one** message, each told who to message next, then stop and let them run.

```
Lead ←→ architect ←→ coder ←→ tester ←→ reviewer
```

- Pipeline (A→B→C→D) for sequential dependencies.
- Fan-out (Lead→A,B,C→Lead) for independent parallel work.
- Supervisor (Lead↔workers) for ongoing coordination.

For a full parallel sprint, lanes run in **isolated git worktrees** so they can't collide —
see [[systems/swarm-harness]] and the [[skills/agile-swarm/SKILL|agile-swarm]] skill.

## Model routing

Simple mechanical transforms → do them directly (Edit). Simple tasks → Haiku. Architecture,
security, complex reasoning → Sonnet/Opus. Don't burn a large model on a rename.

## Engine routing (which CLI)

Claude Code is the **default engine**. For cross-provider diversity or alternate CLIs
(Gemini, Grok, …), use [[systems/engine]] + [[skills/multi-engine/SKILL|multi-engine]]
(`meta run` / `meta fan`) — not a second swarm stack. Fan-out is opt-in; in-session
coordination stays SendMessage / Ruflo.

## Quality gate

Non-trivial work passes through a reviewer before it's considered done. Tests run after
code changes; build must be green before a PR.
