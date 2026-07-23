---
type: system
tags: [os, system, interface]
---
# Interface Layer (layer 3)

The dashboard contract. The app itself lives in a **separate sibling repo**
(`meta-os-dashboard`) — app code (deps, builds, CI) has a different lifecycle from a
markdown vault, and this repo stays a pure framework. This note defines what the
interface reads, how it triggers work, and the principles it renders by.

## Principles

- **Observability first.** The primary user is the operator, not a non-technical
  delegate. Buttons are a bonus; *seeing the OS run* is the value: automations and their
  forecast, memory promotion state, vault changes, sprint/swarm lanes, graph health.
- **Prompt-first, not button-first.** The run surface is a command palette / prompt
  console with skill autocomplete — skills prefill an *editable* prompt, never a
  fire-and-forget button. Same mental model as the terminal, lower friction.
- **The vault is the database.** No proprietary store. The dashboard reads git-tracked
  markdown front-matter and JSON artifacts from disk; anything it writes goes through the
  normal engine so results land in the vault like any other run.
- **Ontology-driven rendering.** Views derive from [[systems/ontology.yaml|ontology.yaml]]
  (a view per note type, facets per tag namespace) — see [[systems/ontology]]. The
  dashboard also lints front-matter against the schema and surfaces violations.
- **Privacy boundary preserved.** Dashboard code is generic and public-safe; it is
  pointed at an *instance root* via config at runtime. Instance data never enters either
  framework repo.

## Read surfaces (all from the instance root)

| Feed | Source | Renders as |
|------|--------|-----------|
| Skill catalog | `skills/_index.md` | Palette entries, grouped by domain |
| Project registry | `projects/*.md` front-matter | Estate table (ontology `project` type) |
| Automations | `automations/_index.md` + `automations/runs.jsonl` | Routine rows, cadence/cron, last run + outcome |
| Memory pipeline | `memory/{raw,wiki,output}/` + `vaults/` | Promotion kanban; stale-raw and orphan warnings; federated note counts (navigation, not canon) |
| Knowledge graph | `graphify-out/graph.json` (per repo) | Graph view: communities, god nodes, confidence filter |
| Process state | tracker / backlog mirror | Sprint board, lane status |
| Flow state | tracker changelog + swarm batch state + vault git log | Lane queues + flow metrics (below) |
| Vault activity | instance git log | Recent-changes widget |
| Outputs | `memory/output/` + recent `memory/wiki/` promotions (front-matter + git history) | Output inbox — deliverables, faceted by type/project |
| Engine usage | engine session logs (local JSONL; path in dashboard config) | Tokens × model × project × day. Local-only — session logs are instance content and never enter a repo |

Graph queries can go through graphify's MCP server (`query_graph`, `god_nodes`,
`shortest_path`, …) instead of re-implementing traversal.

## Lanes and flow metrics

Lanes are **derived, never filed** — the ontology's `flow:` section defines the
vocabulary (pipelines, stages, item states); the dashboard reconstructs lane state from
the authoritative feeds and renders each pipeline as a queue view: one swim-lane per
[[systems/swarm-harness|swarm lane]] with its per-stage queue, and the same view over
[[systems/memory-layer|raw → wiki → output]].

- **Instant:** WIP per lane, queue depth per stage, blocked items + age, item age in
  stage, flow efficiency.
- **Forecast:** trailing throughput, cycle-time distribution, Little's-Law ETA per lane
  (queue depth ÷ throughput), capture-vs-promotion rate for memory.

All of it depends on one input: **stage-transition timestamps** (tracker changelog, PR
events, vault git log). If a feed can't produce timestamps, its lane renders as a plain
queue with no forecast — degrade visibly, don't fake precision.

## Trigger surface

One mechanism: run the engine **headless** from the prompt console, streaming output to
the UI (SSE). Skill invocations are prompt prefills over the same mechanism. Outputs land
in `memory/raw/` or `output/` per normal discipline — the dashboard displays results, it
never owns them.

**Default adapter** remains Claude (`claude -p "<prompt>"`). Prefer the pluggable form
via [meta-cli](https://github.com/meta-agentic/meta-cli) when multi-provider or configured
routing is needed:

```text
meta run --engine <auto|cli|acp> -p <claude|gemini|grok|…> -- "<prompt>"
```

The trigger surface is still **one mechanism**, but the run can pick a **lane**: a
one-shot **CLI** subprocess, or a warm **ACP** session that persists across runs. The
dashboard leaves `--engine auto` unless the operator selects a lane; a persistent ACP run
resumes from state the framework keeps as **OS memory** — its session summary and
`session_id` land in `memory/raw/` on collect, not in an opaque adapter store. So a warm
run is still just "a run whose result is in the vault," and the dashboard displays it like
any other. Engine contract, the two lanes, and quota-probe surface: [[systems/engine]].
Multi-provider collect skill: [[skills/multi-engine/SKILL|multi-engine]].

One control-plane consequence: adapters only **probe** quota (`getQuotaWindows`);
**enforcement** — budget hard-stops, auto-pause — is the interface layer's job, reading
that probe. The engine layer deliberately holds no budget logic.

## MVP order

1. Read-only observability: automations, promotion pipeline, registry, recent changes,
   lane queues (instant metrics only).
2. Flow forecasts (throughput, cycle time, ETA) once transition timestamps are wired.
3. Graph view over `graphify-out/graph.json` + ontology-driven type/tag facets.
4. Front-matter linting against [[systems/ontology.yaml|ontology.yaml]].
5. Prompt console with headless runs + streaming (last — the terminal already does this).

Beyond the MVP: [[systems/interface-extensions]] evaluates the wider agentic-dashboard
widget set against this contract and phases in the adopted ones (unified event feed,
scheduler forecast, output inbox, engine usage).
