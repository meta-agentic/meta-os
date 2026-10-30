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
| `test_slots.py` | Lane slots: `swarm.lanes` slots on the first pass, a bound lane taking its project's item, an idle rebind with its event, a drain before a mid-run rebind with the run filed in `runs/run-<n>.json`, lowering `swarm.lanes`, the last five runs, the heartbeat from reported activity, must-fail forged ledgers, a prototype `lanes.json`, the prompt fields and the report. |
| `test_sentinel_preflight.py` | The sentinel's two modes with sub-second stalls (a stall notifies once, a consumed event or a changing tree never, `.tmp` files are not events) and the pre-flight's allow, ask, deny, unmatched, compound and bypass cases. |
| `test_runner.py` | The runner on the dry-run harness, with an injected clock and waiter: one event starting two steps and an exit with a PR moving its item to review, no pass without an event, a silent step killed and given back with the reason, the rate-limit hold and its lost reset, the idempotent transition, a forged half pass adopted and failed after a restart, the lease on one host and across hosts, one commit per pass in a record repository, the kqueue and poll waiters, real steps under the wrapper, and the launchd template. |
| `test_review.py` | The review station: must-fail refusals of the auto-merge tier (off by default, a malformed list, outside the classes, agent instructions are not documentation, an unknown class, a red, pending, skipped or missing check, `human-judgement` on the PR or the item, a draft, closed or unmergeable PR), the merge pinned to the head it read and the transition to `DONE`, a failed transition retried without a second merge, the queue oldest first with its age from git, the SLA pause in `plan.json`, the run line and the report, and `q` per week. |
| `test_start.py` | The proven start on the dry-run harness: a start missing each of the runner, the sentinel, the first step and its first progress is refused naming it, proofs older than the start do not count, a launch that never returns still gets its verdict at the deadline, the pre-flight refusal stops the launch, the sentinel probe (launchd and systemd, its file and the inbox it must watch), and the CLI. |
| `test_vaultlock.py` | The vault write lock: the runner's vault commit takes it, a held lock defers the commit naming the holder, autocommit off takes none, a worktree shares the lock. |
| `test_events.py` | The event producers: one well-formed event each, atomic writes and ignored `.tmp` files, window-reset idempotence, the step's exit code kept when the inbox is unwritable, the hooks, and a recorded `304` that writes nothing. |

## Running it

```bash
python3 -m unittest discover -s pipeline/tests
```

CI runs it in the blocking job of the check workflow, through `scripts/run_tests.py`,
which finds every suite in the repository.

The fixtures use synthetic space keys that cannot be mistaken for a real tracker key, so
the framework's public-safety scan stays clean without an allow-list entry.
