---
type: system
tags: [os, system, swarm]
---
# Swarm Harness

> **The batch model the pipeline replaced.** Kept for the one rule and the in-run discipline it
> defines, which the pipeline still applies; for how work flows now, read [[systems/pipeline]].

Parallel multi-lane execution. Procedure lives in the [[skills/agile-swarm/SKILL|agile-swarm]] skill; this anchors
the model and its one hard rule.

## The model

A sprint becomes **N independent lanes**, each a lead agent in its own **git worktree**,
coordinated as one team via `SendMessage`. Like the parallel pipelines of a superscalar
CPU: each lane flows branch → implement → clean-verify → review → PR → merge, and N lanes
run at once.

## The one rule

**Parallelism is safe only when lanes don't touch the same files.** Group by *distinct
codebase/service* — one backend service · another service · the frontend · infra — never by
dependent chains inside one module. If two candidate items share a module, they're the
**same** lane (one lead, sequential), not two. Cross-cutting work is the hazard you
serialize.

## Guardrails (non-negotiable)

- Pull fresh `main`; branch every lane off latest.
- Reconcile tracker ↔ backlog before spawning (see [[systems/scrum-harness]]).
- One story ↔ one branch; foreground clean-verify before PR.
- Independent reviewer + security pass on each PR before merge.
- PO owns merges and sprint-close.

## Relation to the pipeline

This is the model of **one batch**. What keeps batches flowing — the dispatcher that
re-populates lanes as items close, the WIP cap, the PO station's limits and the sizing
rules — is [[systems/pipeline]], sized by [[systems/pipeline/queueing]].

## Relation to the operating model

This is the swarm specialization of [[systems/agentic-operating-model]] — same
SendMessage-first coordination, applied at sprint scale with worktree isolation.
