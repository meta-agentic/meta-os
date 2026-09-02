---
type: system
tags: [os, system, interface]
---
# Interface Layer — Widget Extensions (roadmap)

Evaluation of the common "agentic OS dashboard" widget set — live activity feed,
token/cost analytics, task kanban, routine scheduler, skill panel, output inbox, context
chat, knowledge graph — against this OS's [[systems/interface-layer]] contract, and the
plan for adopting what fits. The contract's principles are the filter: observability
first, prompt-first (never fire-and-forget buttons), the vault is the database,
ontology-driven rendering, privacy boundary preserved.

## Verdicts

| Proposed widget | Verdict | Why / how |
|-----------------|---------|-----------|
| Live activity feed | **extend** | A vault-activity widget exists (instance git log). Unify it with `automations/runs.jsonl`, the backlog changelog, and swarm batch state into one event timeline; live agent telemetry comes later via hook-appended events (below). |
| Token / cost analytics | **adopt** | New read surface. The engine's local session logs already record per-message usage — aggregate tokens × model × project × day. No new store, nothing leaves the machine. |
| Task kanban (tracker-integrated) | **already covered** | The lanes widget renders the backlog mirror per [[systems/swarm-harness\|swarm lane]] with burn + forecasts. The tracker stays authoritative (instance authority order); the dashboard never writes it. Remaining gap: blocked items + age — already specified in the ontology's `flow.metrics.instant`. |
| Cron / routine scheduler (next 24–48h) | **extend** | The automations table already carries machine-readable `cadence` ([[systems/ontology.yaml\|ontology.yaml]] `automations:` contract). Compute next-run per scheduled row and render an upcoming-runs strip. No contract change. |
| Skill / action panel (one-click) | **adapt** | One-click triggers violate prompt-first. This becomes the prompt console (MVP step 5): skill autocomplete prefills an *editable* prompt, runs headless, streams back. |
| Curated output inbox | **adopt** | `memory/output/` is already the deliverables folder ([[systems/memory-layer]]). A widget listing recent outputs plus fresh wiki promotions, faceted by ontology type. The vault is the database — no separate inbox store. |
| Context chat widget | **merge** | Not a separate widget: the prompt console prefills the context of the view you're looking at. One trigger mechanism, not two. |
| Knowledge graph | **done** | Shipped — the graphify view. No action. |

## New read surfaces

Contract additions to [[systems/interface-layer]]'s read-surface table, amended as each
one ships:

| Feed | Source | Renders as | Notes |
|------|--------|-----------|-------|
| Engine usage | engine session logs (local JSONL) | tokens/cost: model × project × day | Read-only and local-only; the log path is set in the dashboard's gitignored instance config. Session logs contain instance content — they never enter any repo. |
| Event log | `automations/events.jsonl` (instance) | live activity feed | Appended by whatever hooks the instance has enabled — staged per pack and never auto-wired ([[systems/packs]]) — one JSON object per line: `{ts, actor, action, target, note?}` — same discipline as `runs.jsonl`. |
| Outputs | `memory/output/` + recent `memory/wiki/` promotions (front-matter + git history) | output inbox | No new store; the promotion discipline is unchanged — the inbox just makes deliverables visible. |

## Phasing

1. **Derive from what exists** (dashboard-only, no contract change): upcoming-runs strip
   on the automations widget; unified event timeline composed from vault git log +
   `runs.jsonl` + backlog changelog; blocked + age on lanes.
2. **New read surfaces:** output inbox, then engine usage/cost. Amend the read-surface
   table in [[systems/interface-layer]] as each lands.
3. **Live telemetry:** hook-appended `automations/events.jsonl` plus server-sent events,
   so the activity feed updates without polling. Add the `events.jsonl` entry shape to
   [[systems/ontology.yaml|ontology.yaml]] when this ships.
4. **Trigger surface (last, per MVP order):** the prompt console — skill palette,
   view-context prefill, headless streaming run. Absorbs both the "skill panel" and the
   "context chat" proposals.

Implementation detail (endpoints, files, config keys) lives in the dashboard repo's
`ROADMAP.md` — app-lifecycle concerns stay out of the framework.

## Rejected on principle

- **Fire-and-forget skill buttons** — the run surface is an editable prompt, always.
- **A second task board with its own state** — lanes are derived, never filed; the
  tracker/backlog mirror remains the authority.
- **A standalone chat pane** — one trigger mechanism (the console); context awareness is
  a prefill, not a parallel channel.
