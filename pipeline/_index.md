---
type: index
tags: [os, pipeline, automation]
---
# pipeline/ — the autonomous swarm loop (deterministic half)

Design: [[systems/swarm-pipeline]] · sizing: [[systems/swarm-pipeline-queueing]] ·
autonomy (regulator, reflection, speculation): [[systems/autonomous-pipeline-spike]].

This folder is **mechanism, not policy** (ADR-MOS-10): it holds no repository names, no
budgets, no prompts. An instance supplies a config file and a state directory; a harness
in the instance executes what `tick.py plan` emits and feeds the outcome back through
`tick.py record`.

| File | What |
|---|---|
| `tick.py` | CLI: `plan` (ready set → regulator → assignment → speculation → reflection), `record` (harness results → ledger → item transitions → vault commit), `report` (the human's morning page) |
| `metaos_pipeline/readyset.py` | ready-set query over the vault; the one rule as a `(space, repo, primary tag)` heuristic; fairness cap |
| `metaos_pipeline/controller.py` | AIMD regulator on the WIP cap `N`, rate-limit guard, per-lane cap, window budget |
| `metaos_pipeline/speculate.py` | the speculation decision rule and the per-tick speculative plan |
| `metaos_pipeline/reflect.py` | predicted (queueing model) vs measured, attribution rules, escalations, the reflection record |
| `metaos_pipeline/ledger.py` | atomic state, materialised lanes, append-only events / runs / reflections, a directory lock |
| `tests/test_pipeline.py` | `python3 -m unittest discover -s pipeline/tests` |

## Contract with the harness

`plan` writes a JSON document: `spawn[]` (work lanes: item, repo, branch, prompt),
`spec_spawn[]` (speculative lanes: decision, branch key, outcome branch, prompt), `check[]`
(running sessions to poll), `interrupt[]` (lanes over their cap), `N`, `freeze`, gauges and
the reflection record. The harness starts one headless session per spawn entry, polls the
sessions in `check`, and returns `results.json`:

```json
{ "spawned":  [{"lane_id": "...", "ok": true, "session_id": "..."}],
  "checks":   [{"lane_id": "...", "status": "working|idle|failed|archived", "usage": {"cost_usd": 0, "tokens": 0},
                "rate_status": "allowed|allowed_warning|rejected", "pr": {"url": "...", "number": 0}, "branch_pushed": true}],
  "interrupted": ["..."] }
```

`record` is idempotent per lane state and is the **only writer of item status**: it
transitions to `IN PROGRESS` when a lane starts and to `IN REVIEW` when a lane ends with a
PR, through the instance's backlog CLI, then commits the vault with a message that names
every transition, lane, session and branch.

## Invariants

- No loop widens its own bounds: `N ∈ [N_min, N_max]`, one step per tick, halving on any
  rate-limit signal, freeze when the window budget is spent.
- The pipeline never merges and never transitions to `DONE`; speculative lanes never
  transition anything.
- Every decision is replayable from `runs.ndjson` + `reflections.ndjson` + `events.ndjson`.
