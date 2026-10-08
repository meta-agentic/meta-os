---
type: index
tags: [os, pipeline, tests]
---
# pipeline/tests/ — the pipeline's own test suite

Unit and end-to-end tests for [[pipeline/metaos_pipeline/_index|metaos_pipeline/]] and
`tick.py`, run against a throwaway fake vault built in a temporary directory.

| File | What |
|------|------|
| `test_pipeline.py` | Ready set and assignment (the one rule, fairness, public-repo branch names), the AIMD regulator, speculation, the ledger, the backlog-CLI contract, and a `plan → record → report` round trip. |

## Running it

```bash
python3 -m unittest discover -s pipeline/tests
```

CI runs it in the blocking job of the check workflow, through `scripts/run_tests.py`,
which finds every suite in the repository.

The fixtures use synthetic space keys that cannot be mistaken for a real tracker key, so
the framework's public-safety scan stays clean without an allow-list entry.
