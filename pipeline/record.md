---
type: reference
tags: [os, pipeline, contract]
---
# The pipeline's record — read contract

What the pipeline writes, for every reader that is not the pipeline: the dashboard's Pipeline tab, the watchdog, a human with `git log`. Design: [[systems/pipeline]] §10.

## Where it lives

- **Record repository** (`swarm.record_repository.url` in the estate config, its local clone at `swarm.record_repository.path`; [[systems/config]]). A private git repository of its own, never the framework and never the instance's own tree. `tick.py` fetches and fast-forwards before every phase, refuses to write on a clone it cannot prove current (fetch failed, local commits the remote lacks, uncommitted files), and ends each phase that changed something in one commit, pushed at once: `pass <n> <phase>: lanes changed: <ids>`. A phase that changed nothing writes nothing. A push rejected as non-fast-forward drops the phase's local commit, re-fetches and replays the phase from the new state; nothing is ever force-pushed. A reader takes the clone, or the repository through the dashboard's GitHub source, and never writes.
- **Plain directory** (the key unset): `tick.py --state DIR`, the same files without git, as the prototype ran. The run line on stderr names the mode: `tick plan: record in the plain directory … (swarm.record_repository unset)` or `tick plan: record in the record repository's git clone …`.
- **Nested clones are refused.** A clone inside the instance's own git tree would mix the record's commits with the instance's history; `tick.py` stops unless the pipeline configuration sets `record_repository.allow_nested: true`.

## Versions

Every file carries `schema`: the top-level object of a JSON file, every element of `lanes.json`, every line of an NDJSON log. The current version is **2**. A file without `schema` is the prototype's layout, version 1, read and never written. Any other version stops the run with the file and the version it found.

## Files

| File | Shape | Writer |
|---|---|---|
| `state.json` | object: `schema`, `N`, `tick` (the pass), `paused`, `spent`, `calibration`, `retries`, `window_start`, `last_plan_ts`, `last_tick_ts`, `account_rate_status` | `tick.py plan`, `tick.py record` |
| `lanes.json` | array of lane objects: `schema`, `lane_id`, `kind` (`work` or `spec`), `status`, `item` and `item_ref` or `decision` and `branch_key`, `space`, `repo`, `branch`, `session_id`, `usage[]`, `pr`, `planned_tick`, `started`, `ended` | `tick.py plan`, `tick.py record` |
| `events.ndjson` | one object per line: `schema`, `ts`, `kind`, then the event's fields (`lane_id`, `item`, `to`, `status`, …) | `tick.py plan`, `tick.py record` |
| `runs.ndjson` | one object per line and phase: `schema`, `ts`, `phase` (`plan` or `record`), `tick`, the plan's gauges or the record's `transitions` | `tick.py plan`, `tick.py record` |
| `reflections.ndjson` | one object per line and pass: `schema`, `ts`, `tick`, `predicted`, `measured`, `attribution`, `escalations` | `tick.py plan` |
| `passes/<date>/plan-<n>.json` | the plan `tick.py plan` emitted for pass `n`, with every `prompt` removed | `tick.py plan`, record repository only |
| `passes/<date>/results-<n>.json` | the harness's results document for pass `n`, as `tick.py record` received it | `tick.py record`, record repository only |

`<date>` is the pass's UTC date, `YYYY-MM-DD`. The NDJSON logs are append-only; `state.json` and `lanes.json` are rewritten whole, atomically.

## What the record never holds

No token, credential or session prompt. A lane names its item by `item_ref`: `{path, vault_sha, sha256}`, the item file's path in the vault, the vault commit it was read at, and the hash of its bytes, never the body itself.

## Names

The file names are constants in `metaos_pipeline/ledger.py` (`RECORD_FILES`), the one place to rename one. `runs.ndjson` keeps its name for now, holding one record per phase; whether it becomes the log of finished runs, with the per-pass record moving to `passes.ndjson`, is still open.
