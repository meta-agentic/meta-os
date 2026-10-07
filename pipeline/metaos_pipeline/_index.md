---
type: index
tags: [os, pipeline, automation]
---
# pipeline/metaos_pipeline/ — the deterministic package

The library behind `tick.py` ([[pipeline/_index|pipeline/]]): everything the pipeline
decides, and nothing it executes. No module here talks to a session API or holds instance
data; the instance's harness runs what the plan emits and feeds the results back.

| File | What |
|------|------|
| `__init__.py` | Package docstring: the split between this package and the instance's harness. |
| `readyset.py` | Ready-set query over the vault; lane assignment under the WIP cap, the one rule and the fairness cap. |
| `controller.py` | AIMD regulator on the WIP cap `N`, rate-limit guard, per-lane cap, window budget. |
| `speculate.py` | The speculation decision rule and the per-tick speculative plan. |
| `reflect.py` | Predicted (queueing model) vs measured, attribution rules, escalations, the reflection record. |
| `ledger.py` | Atomic state, materialised lanes, append-only events / runs / reflections, a directory lock. |
