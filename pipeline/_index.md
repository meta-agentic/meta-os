---
type: index
tags: [os, pipeline, automation]
---
# pipeline/ — the autonomous swarm loop (deterministic half)

Design and specification: [[systems/pipeline]] · evidence: sizing [[systems/pipeline/queueing]],
autonomy (regulator, reflection, speculation) [[systems/pipeline/control-spike]].

This folder is **mechanism, not policy** — instances mount it rather than copy it, so it
must run unchanged in every one of them: it holds no repository names, no budgets, no
prompts. An instance supplies a config file and a record: the private repository `swarm.record_repository` names, or a plain state directory when that key is unset ([[pipeline/record]]; with `visibility_probe: true`
there, each run's repository is probed through [[scripts/_index|scripts/public_repo_gate.py]]
and a repository not proven private gets a branch name without the item id or any key its title cites, the public-repository note, and an empty `{pr_title_prefix}` where a private one gets `<id>: `); a harness in the
instance executes what `tick.py plan` emits and feeds the outcome back through
`tick.py record`.

**Pipeline changes are made here, in meta-os, and reach an instance only by `scripts/upgrade.sh`.** `pipeline/` is a framework path: an instance never edits it (the upgrade refuses a merge while one is modified), so a change made in an instance's copy has to be published upstream by hand before the next upgrade can merge.

| File | What |
|---|---|
| `tick.py` | CLI: `plan` (ready set → regulator → assignment → speculation → reflection), `record` (harness results → ledger → item transitions → vault commit), `report` (the human's morning page) |
| `metaos_pipeline/admission.py` | the admission gate: executable space, status, blockers from the vault's dependency index (refuses a stale one), lane holds and retries, holding labels and parked epics; a reason for every exclusion, orphans for the watchdog, the planner's order among the admitted |
| `metaos_pipeline/slots.py` | the lane slots: `swarm.lanes` durable slots, one project and one run each, a rebind only when idle and drained, finished runs filed in `runs/`, the per-pass session invariant |
| `metaos_pipeline/readyset.py` | ready-set query over the vault; the one rule as a `(space, repo, primary tag)` heuristic; fairness cap |
| `metaos_pipeline/controller.py` | AIMD regulator on the WIP cap `N`, rate-limit guard, per-lane cap, window budget |
| `metaos_pipeline/speculate.py` | the speculation decision rule and the per-tick speculative plan |
| `metaos_pipeline/reflect.py` | predicted (queueing model) vs measured, attribution rules, escalations, the reflection record |
| `metaos_pipeline/review.py` | the review station: the queue oldest first (age from the vault commit that set `IN REVIEW`), `review_age_max_days` and the `review_sla_days` pause, the auto-merge tier behind `decide` (off by default; every doubt refuses), `q` per week |
| `metaos_pipeline/ledger.py` | atomic state, materialised lanes, append-only events / runs / reflections, a directory lock |
| `metaos_pipeline/runner.py` | the event-driven runner behind `tick.py run`: the lease, a blocking wait on the inbox (the kernel's file events: kqueue on macOS and the BSDs, inotify on Linux; a declared poll only where neither exists), one pass per batch of events, steps started under `step_wrap`, quiet timers that kill and reap a silent step, the rate-limit hold, adoption of a lost pass's runs, the supervisor step as a pluggable command |
| `metaos_pipeline/vaultlock.py` | the vault write lock: `flock` on `vault-write.lock` in the vault's common git directory (a worktree shares it), the one lock every writer in the vault takes so they never meet at `.git/index.lock`; `tick.py`'s vault commit takes it for its fetch-commit-push (never around the backlog tool, which takes it itself) and defers, naming the holder, when it stays held |
| `metaos_pipeline/start.py` | the proven start behind `tick.py start`: pre-flight first (a refusal stops it with its reason), then the launch command, then *started* only when the runner holding the lease, the sentinel's job, the first lane step and the first progress have each been seen after the start began and cited; otherwise *not started*, naming each missing proof. The launch command's own exit decides nothing; the wait is bounded (`--deadline`, a look every `--every` seconds) |
| `metaos_pipeline/fake_engine.py` | the dry-run harness: a fake step engine with scripted exits, progress and rate-limit lines, and a scripted step command |
| `runner.plist.template` | the runner as a launchd agent (macOS; KeepAlive on a crash), placeholders only; the instance installs it |
| `systemd/` | the runner and the sentinel as systemd user units (Linux; `Restart=on-failure`, a `.path` unit for the sentinel), the same placeholders — [[pipeline/systemd/_index\|systemd/]] |
| `sentinel.py` | the watcher outside every session (started by the instance's service manager when the inbox changes, never on an interval: launchd `WatchPaths`, a systemd `.path` unit): `inbox` mode notifies once per event the runner left unconsumed for `--stall-minutes`; `progress` mode, armed by a marker file, notifies once per silence of the watched paths (a stat walk bounded by `--max-depth`, never entering dot-dirs or build trees). The notifier is the instance's argv (`--notify-cmd`) |
| `preflight.py` | refuses an unattended start when any step's command template could ask for approval under the session's permission settings (deny, ask, no allow rule, compound or `cd`); passes under `bypassPermissions` with a caveat |
| `metaos_pipeline/events.py` | the runner's inbox: the event file format, its one atomic writer, `list_events`, the `emit` CLI, the one-shot window reset |
| `metaos_pipeline/step_wrap.py` | runs one step; writes `rate_limit` and `step_exit` events from what it reports |
| `metaos_pipeline/remote_watch.py` | the one poll: conditional (ETag) GitHub requests; a change writes one `remote_change` event |
| `hooks/post-commit`, `hooks/post-merge` | in the record clone: one `vault_commit` event per new HEAD when `METAOS_PIPELINE_INBOX` is set |
| `tests/test_pipeline.py` | `python3 -m unittest discover -s pipeline/tests` |
| `metaos_pipeline/ledger.py` | atomic state, materialised lanes, append-only events / runs / reflections, a directory lock; over the record repository's clone, fetch before every phase and one commit per phase that changed something, pushed at once |
| `record.md` | the record's read contract: every file, its shape, its writer, its `schema` version |
| `tests/test_pipeline.py`, `tests/test_record.py` | `python3 -m unittest discover -s pipeline/tests` |
| `metaos_pipeline/`, `tests/` | each has its own index — [[pipeline/metaos_pipeline/_index\|metaos_pipeline/]] · [[pipeline/tests/_index\|tests/]] |

## Contract with the harness

`plan` writes a JSON document: `lanes[]` (every slot's `lane_id`, `project`, `actual`), `spawn[]` (work runs: slot `lane_id`, `run_id`, item, repo, branch, prompt), `admitted[]`, `excluded{id: reason}`, `orphans[]` and
`planner_ignored{id: reason}` from the admission gate (a stale dependency index makes `plan`
exit 2 with `refused` and nothing else),
`spec_spawn[]` (speculative lanes: decision, branch key, outcome branch, prompt), `check[]`
(running sessions to poll), `interrupt[]` (lanes over their cap), `N`, `freeze`, gauges and
the reflection record. The lane prompt may use `{lane_id}`, `{project}`, `{vault_sha}` and
`{item_sha256}` beside the item's fields. The harness starts one headless session per spawn entry, polls the
sessions in `check`, and returns `results.json`:

```json
{ "spawned":  [{"lane_id": "...", "ok": true, "session_id": "..."}],
  "checks":   [{"lane_id": "...", "run_id": "...", "activity_ts": 0, "status": "working|idle|failed|archived", "usage": {"cost_usd": 0, "tokens": 0},
                "rate_status": "allowed|allowed_warning|rejected", "pr": {"url": "...", "number": 0}, "branch_pushed": true}],
  "interrupted": ["..."] }
```

A result naming a `run_id` the slot no longer holds is ignored. `activity_ts` is the session's
last activity of any kind; `record` stamps it as the run's `heartbeat` (the time of reading when
absent), and nothing polls for it.

`record` is idempotent per lane state and is the **only writer of item status**: it
transitions to `IN PROGRESS` when a lane starts and to `IN REVIEW` when a lane ends with a
PR, through the instance's backlog CLI (which receives the vault path in `METAOS_VAULT`),
then commits the vault with a message that names every transition, lane, session and
branch.

## Events (the runner's inbox)

The runner has no cadence: it blocks on an inbox directory and runs one pass per event.
Producers only write there; none reads the record, takes the lease or starts work.

- **File:** `<UTC yyyymmddTHHMMSS.ffffffZ>-<kind>-<8 hex>.json`, so names sort by time. Written
  to `.tmp-<name>` and renamed; a name starting with `.` is never an event.
- **Body:** `{schema: 1, id, kind, at, source, payload}`.
- **Kinds:** `step_exit`, `rate_limit`, `window_reset`, `vault_commit`, `remote_change`;
  `control` and `stall` are the runner's own.

```bash
python3 -m metaos_pipeline.events emit <kind> --inbox DIR --source S [--payload JSON]
python3 -m metaos_pipeline.step_wrap --inbox DIR --run-id R [--log FILE] -- <cmd...>
python3 -m metaos_pipeline.remote_watch --inbox DIR --targets FILE [--poll-seconds 60] [--state FILE] [--once]
```

Run them from `pipeline/` or with it on `PYTHONPATH`. The targets file is the instance's (a
JSON list of `owner/repo@branch` and `owner/repo#n`). A reported reset time schedules one
detached one-shot that writes `window_reset` at that time, once per (window, reset time).

Installing the hooks in the record clone: [[pipeline/hooks/_index|hooks/]].

## Invariants

- No loop widens its own bounds: `N ∈ [N_min, N_max]`, one step per tick, halving on any
  rate-limit signal, freeze when the window budget is spent.
- The pipeline merges and transitions to `DONE` only through the auto-merge tier
  (`metaos_pipeline/review.py`), which is off while `swarm.automerge_classes` is empty; speculative lanes never
  transition anything.
- Every decision is replayable from `runs.ndjson` + `reflections.ndjson` + `events.ndjson`.
