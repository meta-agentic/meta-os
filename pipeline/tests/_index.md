---
type: index
tags: [os, pipeline, tests]
---
# pipeline/tests/ — the pipeline's own test suite

Unit and end-to-end tests for [[pipeline/metaos_pipeline/_index|metaos_pipeline/]] and
`tick.py`, run against a throwaway fake vault built in a temporary directory.

| File | What |
|------|------|
| `test_admission.py` | Must-fail tests, one per admission rule (blockers `TO DO`, `IN REVIEW`, `NO GO` and on an epic, a paused lane, a parked epic two levels up, a stale index, a non-executable space), the planner hook, the unchanged default order, a fixture of the prototype window's ready set, and the reasons in `plan.json`, the run line and the report. |
| `test_record.py` | The record repository over local bare repositories: one commit per phase, the no-op, a push race replayed, stale-clone refusals, unknown schemas, the read contract round trip, the nested-clone refusal, and the unset-key fallback. |
| `test_pipeline.py` | Ready set and assignment (the one rule, fairness, public-repo branch names), the AIMD regulator, speculation, the ledger, the backlog-CLI contract, and a `plan → record → report` round trip. |
| `test_sentinel_preflight.py` | The sentinel's two modes with sub-second stalls (a stall notifies once, a consumed event or a changing tree never, `.tmp` files are not events) and the pre-flight's allow, ask, deny, unmatched, compound and bypass cases. |
| `test_events.py` | The event producers: one well-formed event each, atomic writes and ignored `.tmp` files, window-reset idempotence, the step's exit code kept when the inbox is unwritable, the hooks, and a recorded `304` that writes nothing. |

## Running it

```bash
python3 -m unittest discover -s pipeline/tests
```

CI runs it in the blocking job of the check workflow, through `scripts/run_tests.py`,
which finds every suite in the repository.

The fixtures use synthetic space keys that cannot be mistaken for a real tracker key, so
the framework's public-safety scan stays clean without an allow-list entry.
