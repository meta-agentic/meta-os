---
type: index
tags: [os, pipeline, automation]
---
# pipeline/metaos_pipeline/ — the deterministic package

The library behind `tick.py` ([[pipeline/_index|pipeline/]]): everything the pipeline
decides, and nothing it executes. No module here talks to a session API or holds instance
data; the instance's harness runs what the plan emits and feeds the results back.
The exception is the event producers (`events.py`, `step_wrap.py`, `remote_watch.py`): they
observe steps and remotes and only write events to the runner's inbox.

| File | What |
|------|------|
| `__init__.py` | Package docstring: the split between this package and the instance's harness. |
| `admission.py` | The admission gate: which ready items a lane may start, the first failing rule as each exclusion's reason, orphans, and the planner hook (orders, never widens). |
| `readyset.py` | Ready-set query over the vault; lane assignment under the WIP cap, the one rule and the fairness cap. |
| `controller.py` | AIMD regulator on the WIP cap `N`, rate-limit guard, per-lane cap, window budget. |
| `speculate.py` | The speculation decision rule and the per-tick speculative plan. |
| `reflect.py` | Predicted (queueing model) vs measured, attribution rules, escalations, the reflection record. |
| `events.py` | The runner's inbox: the event file format, its one atomic writer, `list_events`, the `emit` CLI, the one-shot window reset. |
| `step_wrap.py` | Runs one step; writes `rate_limit` and `step_exit` events from what it reports, never changing its exit code. |
| `remote_watch.py` | The one poll: conditional (ETag) GitHub requests; a changed answer writes one `remote_change` event. |
| `ledger.py` | The record: atomic state, materialised lanes, append-only events / runs / reflections, a directory lock, `schema` versions; over the record repository's clone, fetch-before-write, one commit per phase that changed something and a replay on a rejected push. |
