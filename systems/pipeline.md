---
type: system
tags: [os, system, swarm, pipeline, autonomy, specification]
---
# Pipeline — the swarm as an autonomous closed loop

The living page of the pipeline (the autonomous multi-lane pipeline, ASML): a loop that keeps
a bounded set of lanes busy with work that is ready, across every project, runs unattended
between the product owner's (PO's) sessions, stays inside the account's usage windows, and
asks the PO for nothing but the decisions that are theirs. It replaces the one-batch model of
[[systems/swarm-harness]], whose lanes end with the turn that spawned them and wait for a human
to say "swarm" again.

This page is the model and the specification in one: what the pipeline is (§2), what the PO
asks of it (§3), and what each requirement means in numbers and tests (§4 to §14). The *how*
(runtime, record schema, control contract, sensor source, planner port) belongs to the
architecture decision that follows; nothing here prescribes a module.

**Evidence**, dated and frozen, linked rather than restated: [[systems/pipeline/queueing]]
sizes the pipeline as a queueing network, and
[[systems/pipeline/queueing-model.py|queueing-model.py]] reproduces every table;
[[systems/pipeline/control-spike]] works out how the loop regulates itself unattended and
records the prototype it grew from. Where an evidence page and this page differ, this page
wins. Folder index: [[systems/pipeline/_index|pipeline/]].

**How to read it.** Every requirement is testable, and every one that needs a number states
it. A number marked *(proposal)* is the default until the instance's PO decides; the instance
records the answer in its own tracker, never here, and this page is updated to match.
Examples are generic; the instance keeps its worked examples on real items next to its
decision record.

## 1 · Vocabulary — one word, one meaning

The word *lane* has five meanings in this framework today. From here on it has one.

| Term | Meaning |
|---|---|
| **Lane** | A durable slot, `lane-1 … lane-m_max`, that exists from the first tick and persists in the record. At any moment a lane is **bound** to at most one project and holds at most one item. |
| **Project** | One repository of the instance's registry. A lane's binding names exactly one. |
| **Run** | One item worked by one lane, from start to a pull request (PR) or a reap. A run may use several sessions, all of the lane's project. |
| **Session** | One headless agent session. It belongs to exactly one project for its whole life and is never reused for another. |
| **Pipe** | The pipeline as a whole, as an object of control: its desired state wins over any lane's. |
| **Loop** | The single process that runs ticks. There is never more than one. |
| **Tick** | One cycle: sense, admit, plan, assign, record. |
| **Window** | One of the account's usage limits: the **5-hour** window and the **weekly** window. Each has an **allowance** (100 % of that window), a **remaining** fraction `R_w`, and a reset time. |
| **Mileage** | `ĝ_w`, the share of window `w`'s allowance one lane consumes per hour of work, estimated from what the windows actually report. |
| **Record repository** | The private repository the loop writes its state, plans, results and events to. It is the loop's memory and the dashboard's source. |
| **Control** | A change of *desired* state (start, pause, stop, bind) made by a human through the CLI. The loop changes *actual* state to match. |

What the other four meanings become, so that no document or screen uses *lane* for them:

| Old use of "lane" | Where | Becomes |
|---|---|---|
| A lead agent in its own worktree working a group of related items | [[systems/swarm-harness]], the agile pack | **work stream** |
| One item, one branch, one session; a server of the queueing model | the earlier model page (now §2), [[systems/pipeline/queueing]] | **run** (the model's `m` is the number of lanes, unchanged) |
| A row of the prototype's `lanes.json`, minted per item and forgotten | `pipeline/` | **run** record; `lanes.json` holds lanes |
| `cli` / `acp` / `auto` execution path of an engine | [[systems/engine]] | **engine route** |
| A sprint's stories grouped by project (dashboard *Lanes* widget); one git worktree (dashboard *Flow* tab) | dashboard | **project swimlane**; **worktree** |

The renames are applied by the work that touches each place, not in one sweep.

## 2 · The model — five stations, one cap

```
                 ┌──────────────── tokens released on DONE / NO GO ────────────────┐
                 ▼                                                                  │
 ready set ──▶ [D] dispatcher ──▶ [L] lanes (m) ──▶ [V] review ──▶ [C] cadence ──▶ [P] PO ──▶ close
 (backlog)        tick, N tokens      worktree,          bot +         wait for      human      auto-
                                      branch, PR         security      next session  merge/     transition
                                        ▲                   │ rework                 decide
                                        └───────────────────┘
                                                            └──── q · auto-merge tier ────────▶ close
```

Five stations, one cap. **N**, the number of tokens, caps the items in flight end to end
(CONWIP): a run starts only while a token is free, and a token is freed only when its item
reaches `DONE` or `NO GO`. Everything else follows from that rule.

- **D · Dispatcher**, the loop's tick (§6.4). Fetch every repository's default branch and the
  backlog first: a plan computed on a stale checkout is the failure this design exists to
  prevent. Then build the admissible set (§5.1), reap finished and stale runs (§9), assign
  free lanes under the token and the binding rules (§5.2), start one session per assignment,
  and record the tick and its gauges (§8.3). It holds no state beyond the record repository
  (§10); the backlog is the authority on item status.
- **L · Lanes and runs.** A lane carries one run at a time: a headless session
  ([[systems/engine]]) started with a contract, not a conversation (the item, the repository,
  the branch, the definition of done, the tracker's write rules). Inside the run the agile
  pack's swarm skill governs the work: a fresh worktree off the default branch, implement,
  clean-verify in the foreground, **review inside the run before the PR** (every 0.2 of rework
  costs a quarter of lane capacity), open the PR, hand the item to `IN REVIEW`, end. A run
  never merges and never closes an item.
- **V · Review.** Every PR gets an independent reviewer pass and a security pass from agents
  that did not write it. Defects go back to the lane (the rework loop); questions go to the PR
  thread. Review is cheap next to lanes and must never be the queue that grows: give it more
  servers before giving the lanes more.
- **C and P · Cadence and PO.** The PO is a single server with limited attendance. Their
  capacity is decisions per session times sessions per day; past the lane count that
  saturates it, more lanes add review queue, not throughput. Their cadence puts a floor under
  cycle time: a ready item waits, on average, half a cadence interval. Three disciplines:
  **oldest first** (serving the freshest items first grows a tail nobody ever reaches); an
  **auto-merge tier** (classes of change that pass every automated gate and carry no
  human-judgement flag merge without the PO; the fraction `q` that qualifies is the cheapest
  lever on throughput); and a **review-age limit** (when the oldest waiting item crosses it,
  the space takes no new work, §5.1 rule 7: starving the input is the only way to stop a queue
  growing at a station that cannot be sped up).
- **Close.** A merge triggers the automatic transition to `DONE` in every repository a lane can
  touch, or the pipeline reports as in flight what shipped days ago. `DONE` frees the token; the
  next tick fills it.

**Pooling with fairness.** With `n` projects, one pool of `m` lanes that any project can draw
on beats `n` dedicated pools of `m/n`: queueing delay drops by an order of magnitude, and the
chance that ready work waits for a lane falls by two thirds ([[systems/pipeline/queueing]],
*Pooling*). The concurrency key still applies per repository, so pooling never puts two runs
in the same module, and the fairness share (no space holds more than a configured share of
the tokens) keeps one deep backlog from monopolising the pool.

**Sizing rules**, from [[systems/pipeline/queueing]], with `μL` items per lane-day, `p` the
rework fraction, `q` the auto-merge fraction and `P` the PO's effective decisions per day:

| Quantity | Rule | Why |
|---|---|---|
| Lanes `m` | `m ≈ P / (μL · (1 − p) · (1 − q))` | lanes and PO saturate together; beyond this, lanes idle |
| Tokens `N` | `N ≈ 2m` to `3m` | throughput is within a few percent of its ceiling by `N = 2m`; past `3m` only cycle time grows (Little's law, `W = N / X`) |
| Reviewers | review utilisation below 0.5 | review must never be the growing queue |
| Cadence | shorter sessions, more often | the expected wait is half the interval, whatever the session length |

At the queueing analysis's calibration (2 items per lane-day, 20 % rework, the PO at 8
decisions a day) these give `m = 5` and `N = 10–15` with no auto-merge tier, and `m = 10`,
`N = 20–30` with half the items auto-merging. The sizing says how many lanes the *flow* can
use; §7 says how many the *budget* can pay for. The smaller wins.

## 3 · What the PO asks of it — user stories

Each story is written as the PO would say it, followed by what makes it true.

- **S1 · Run unattended.** "When I am away, ready work keeps moving." The loop ticks without a
  human, at the interval in §6, survives its own process or container being reclaimed (its
  state is entirely in the record repository), and resumes from the last committed tick.
- **S2 · Only ready work.** "Never start something that cannot finish." An item is started
  only when it is admissible (§5): every blocker `DONE`, nothing holding it, its project
  free on some lane. Every item not started carries a reason.
- **S3 · Stay inside my limits.** "Do not burn the week on Monday." The number of working
  lanes is capped so that, at the measured mileage, neither window's reserve is touched before
  its reset (§7). Hitting a reserve or a provider warning freezes new starts.
- **S4 · Lanes per project.** "One lane, one project at a time, and agents never cross
  projects." A lane bound to a project takes that project's items first, rebinds only when
  drained, and no session is ever used for a second project.
- **S5 · Start, pause, stop.** "I can pause or stop one lane or the whole pipe, and start it
  again." Controls per lane and for the pipe, through the CLI and, on a local dashboard, the
  Pipeline tab; each is acknowledged by the loop within the bound in §6.
- **S6 · See it.** "I see each lane's state and numbers, and the whole pipe's." The Pipeline
  tab and `status` show per-lane and aggregate state (§8).
- **S7 · No silent stall.** "If a lane is stuck or the pipe is deadlocked, it is unstuck or I
  am told." A periodic watchdog reaps stale lanes, freezes on deadlock, and reports a stall
  (§9).
- **S8 · Plan ahead, cheaply.** "Use the planner when it is there, reason when it is not, and
  re-plan every few minutes without starting from zero." The planning policy in §5.3.
- **S9 · A record I can audit.** "I can see what it did and why." Every tick, control, start,
  end, reap and freeze is an event in the record repository with its reason (§10).
- **S10 · Morning page.** "I read one page in the morning." The window report lists what
  shipped, what waits for me, what was reaped or held and why, the windows, and the controls
  applied. It reads in under 15 minutes: the decisions waiting for the PO come oldest first,
  capped at what one session can take (8), and escalations at 5.

## 4 · Non-goals and the envelope

The pipeline **never** merges a PR, never moves an item to `DONE` or `NO GO`, never creates or
edits items, sprints or decision records, never edits the framework or pushes to a default
branch, never force-pushes, never changes its own bounds (`m_max`, `N`, reserves, caps,
executable projects), never spends past a window's reserve, and never clears a freeze. Its
writes to the backlog are three arcs only: start (`REFINED → IN PROGRESS`), hand-off
(`IN PROGRESS → IN REVIEW`, with a PR), and give-back (`IN PROGRESS → REFINED`, on reap,
failure or a human stop). The dashboard never writes the
record repository: it asks the CLI. Only a human clears a freeze. The pipeline is not enabled
by default; an instance switches it on, like every automation in this framework.

## 5 · Admission and planning

### 5.1 Admissible

An item is **admissible** when all hold:

1. its space is declared executable by the instance, and its project resolves;
2. its status is a ready status (default `REFINED`), and it is not an epic;
3. every blocker the dependency index lists for it is `DONE` now;
4. no blocking label, exclusion rule or hold applies (a hold is set by the watchdog, §9);
5. no run of the same concurrency key is in flight (today the key is space, repository and
   primary tag);
6. its retry count is below the cap (default 2);
7. its space is not paused by the review discipline: a space whose review queue is over its
   cap, or whose oldest item in review is older than the review-age limit, takes no new work
   until the queue drains.

Anything not admissible is reported with its first failing rule as the reason: *waiting on
X (status)*, *label L*, *excluded*, *held after N reaps*, *project busy*, *not executable*,
*review queue full*.

### 5.2 Assignment

Each tick, after reconciling controls (§6) and reaping (§9), free lanes take admissible items
in planner order, under four rules: a run starts only against a free **token** (the fixed
work-in-progress cap `N` counts items from start until `DONE` or `NO GO`, so items waiting in
review hold their token); a lane bound to project P takes P's items first; an idle, drained
lane may rebind to another project only when no lane already bound to that project is idle,
and only within the fairness share (no space holds more than half the tokens); and the number
of working lanes never exceeds `m_cap` (§7). `N` is set by a human from the sizing in
[[systems/pipeline/queueing]] and never by the loop.

### 5.3 Planning policy

The planner of record is the instance's configured solver when it answers, and agent
reasoning over the same inputs otherwise. The fallback is automatic, logged with its cause,
and never blocks a tick. The planner orders; admission decides (§5.1): a schedule never starts
a story the vault does not admit.

| Event | Response | Number |
|---|---|---|
| A small change: the diff since the last plan touches at most K items or one lane | incremental repair of the last plan, minimal disruption | K = 5 *(proposal)* |
| A repair whose edit distance exceeds the churn cap | discard, solve cold | cap = 10 *(proposal)* |
| Window start, or the full-replan interval elapsed | cold solve | every 6 h *(proposal)* |
| A sudden budget drop (`m_cap` falls by more than one) | drop the lowest-priority runs from the plan; no running item is stopped | — |
| The loop reorders the planner's admissible order | allowed, one recorded reason per change, counted as a gauge | — |

## 6 · Lanes, the pipe, and controls

### 6.1 States

Each lane has a **desired** state (`running`, `paused`, `stopped`, written only by a control)
and an **actual** state:

| Actual | Meaning |
|---|---|
| `idle` | bound or unbound, no item |
| `working` | one run in flight |
| `draining` | no new item; the run in flight ends (PR or reap), its sessions are archived, the worktree released; then `idle` |
| `paused` | desired `paused`, run (if any) finished, takes nothing |
| `stopped` | desired `stopped`; sessions interrupted, item given back |
| `stale` | flagged by the watchdog until reaped (§9) |

The pipe has a desired state `running | paused | stopped` and, set only by the loop, `frozen`
with a reason. The pipe wins: a lane cannot run while the pipe is paused, stopped or frozen.

### 6.2 Controls

| Control | Effect at the next tick |
|---|---|
| **pause** (lane or pipe) | no new item is taken; the running item finishes |
| **stop** (lane or pipe) | sessions interrupted now; the item goes back to `REFINED` with a *stopped by human* note and **no** retry increment; worktree released |
| **start** (lane or pipe) | resume from `paused` or `stopped`; refused while the pipe is frozen, with the reason recorded |
| **bind** (lane, project) | if the lane is working, it drains first; then it binds |
| **unfreeze** (pipe) | human only; the loop never clears a freeze |

Every control is an event with actor, reason and time; its application is a second event with
the latency from request to effect. **Acknowledgement bound:** at most one tick interval
*(proposal: tick interval 10 min, so ≤ 10 min)*; the dashboard shows the control as *pending*
until the application event exists.

### 6.3 Cadence

| Quantity | Value |
|---|---|
| Tick interval | 10 min *(proposal)*, and an early tick when a run ends or a control is made |
| Heartbeat poll of running sessions | every tick, and by a lighter heartbeat between ticks if the tick interval is raised |
| Lanes in the proof-of-concept (`m_max`) | 3 *(proposal)* |

### 6.4 Runtime

One loop at a time, holding nothing it cannot rebuild from the record repository. It must run
where the planner of record is reachable: while the solver is local-only, that is the machine
that hosts it; once the solver is a reachable service, any host that reaches it. A routine
wakes at most hourly, so the inner cadence of §6.3 comes from the loop itself.

*Proposal:* a self-paced loop inside one persistent session on the solver's host, sleeping
the tick interval between ticks and woken early by run-ending events; a local scheduler
restarts it if it dies, and the restarted loop resumes from the last committed tick. A loop
started where the solver is unreachable runs on reasoning and says so on every tick.

## 7 · Budget: the two windows and the lane cap

Units are each window's own allowance, never currency. For each window `w ∈ {5h, week}`, with
`R_w` the remaining fraction of the allowance, `H_w` the hours to its reset, `ρ_w` its reserve
(a fraction of the whole allowance, never spent) and `ĝ_w` the mileage in that window's units:

```
ĝ_w     = EWMA over K ticks of ( drop in R_w during the tick / active lane-hours in the tick )
m_w     = ⌊ max(0, R_w − ρ_w) / (H_w · ĝ_w) ⌋      lanes affordable, run continuously, until w resets
m_cap   = min( m_max, m_5h, m_week )                feed-forward ceiling; moves at most one step per tick
freeze  when R_w < ρ_w for any w, or the provider reports a warning or rejection
```

Inside `[m_min, m_cap]` the additive-increase, multiplicative-decrease law of
[[systems/pipeline/control-spike]] still sets the working-lane count `m` tick by tick; `m_cap`
only bounds it from above. Speculative runs (declared decisions only, at most a third of `m`)
count against `m_cap` like any other run.

The reserve is subtracted, not scaled: `(1 − ρ_w) · R_w` would shrink the reserve as the window
drains and plan spending below the freeze threshold `R_w < ρ_w`. Mileage is estimated **per
window** because the two windows have different allowances: one lane-hour is a larger share of
the 5-hour window than of the week. Until `K` ticks have been
observed, `ĝ_w` is seeded from the instance's declared calibration and flagged as seeded.

| Parameter | Value |
|---|---|
| `ρ_5h` | 0.15 *(proposal)* |
| `ρ_week` | 0.10 *(proposal)* |
| `K` (EWMA span) | 6 ticks *(proposal)* |
| Spending the week faster than pro rata | not allowed *(proposal)* |
| Last hour before a reset | no start whose expected cost (`ĉ_w = ĝ_w ×` expected run hours) exceeds what is left above the reserve |
| No sensor answers | fall back to the declared budget per hour, loudly (an event and a gauge), never silently |
| Per-run cap | expected cost × 3; over it, the run is interrupted and given back |

**Worked example.** Weekly window at `R_week = 0.20`, reset in `H_week = 96 h`, `ρ_week =
0.10`, measured `ĝ_week = 0.0008` (0.08 % of the week per lane-hour). Then
`m_week = ⌊(0.20 − 0.10) / (96 × 0.0008)⌋ = ⌊0.10 / 0.0768⌋ = ⌊1.30⌋ = 1`. With the 5-hour window
at `R_5h = 0.60`, `H_5h = 3 h`, `ρ_5h = 0.15`, `ĝ_5h = 0.12`: `m_5h = ⌊0.45 / 0.36⌋ = ⌊1.25⌋ = 1`.
So `m_cap = 1`: one lane works, whatever `m_max` is. At the same mileage with `R_week = 0.15`,
`m_week = ⌊0.05 / 0.0768⌋ = 0`: nothing starts, the running item finishes, and the pipe idles
until the reset rather than touch the reserve.

## 8 · Screens, commands and gauges, in words

### 8.1 Commands

| Command | What it does |
|---|---|
| `status` | Prints the pipe's desired and actual state, the freeze reason if any, both windows (remaining, reset, `ĝ_w`), `m_cap`, and one line per lane: state, project, item, elapsed, heartbeat age, retries. Read-only. |
| `control pipe start\|pause\|stop --reason R` | Writes the pipe's desired state to the record repository as an event. Refuses on a record clone that is behind its remote. |
| `control lane <id> start\|pause\|stop --reason R` | The same for one lane; refuses an unknown lane. |
| `control lane <id> bind <project> --reason R` | Requests a rebind; drains first if the lane is working. Refuses a project the instance does not declare executable. |
| `control pipe unfreeze --reason R` | Clears a freeze. Human only. |
| `report` | Writes the window report (S10). |

### 8.2 The Pipeline tab

A dashboard tab, read from the record repository.

- **Aggregate strip.** Pipe state (and freeze reason); lanes working / idle / paused / stale;
  both windows as remaining-and-reset gauges with `ĝ_w`; `m_cap` against `m_max`; items started,
  handed off and given back in the last 24 h; median run time; items waiting in review; the
  planner in use (solver or reasoning) and its last fallback cause.
- **Lane cards**, one per lane. Lane id, bound project, desired and actual state (a *pending*
  badge while they differ), the current item with its title and elapsed time, heartbeat age,
  sessions used by this run, the run's usage against its cap, retries, and the last five runs
  with their outcome.
- **Controls**, on a lane card and on the strip: start, pause, stop, bind. Rendered **only**
  when the dashboard reads a local record clone and the instance enables them; never on a
  hosted or GitHub-sourced dashboard. A control calls the CLI; the dashboard writes nothing
  itself.

### 8.3 Gauges

Every tick records its gauges in the record repository and, where the framework's
error-handler sink is enabled ([[hooks/_index]]), emits them. **Flow**: `lanes_active`,
`tokens_free`, `ready_set`, `review_queue`, `review_age_max_days`, `throughput_24h`,
`rework_24h`; the first four say whether the loop is populated, the last three which station
is the bottleneck this week. **Budget**: `window_5h_remaining`, `window_week_remaining`,
`mileage_5h`, `mileage_week`, `m_cap`. **Safety**: `lanes_stale`, `orphans`, `freeze` (with its
reason), `loop_tick_age`, `planner_fallbacks`. The Pipeline tab and the morning report read
them; nobody has to.

## 9 · Watchdog: stale, deadlock, stall

Runs at every tick before admission, and as a lighter heartbeat between ticks that only reads
sessions.

| Condition | Test | Action |
|---|---|---|
| **Stale lane** | no session event and no new commit on the run's branch for `stale_after`; or the session ended or failed without a PR; or the run is over its cap; or the session cannot be found | interrupt, reap, give the item back with retry + 1 and the reason |
| **Held** | the same item reaped `max_stale_reaps` times | hold it (a *needs PO* label and a raised blocker); it is no longer admissible |
| **Deadlock or accounting anomaly** | a running item's blocker is not `DONE`; an `IN PROGRESS` item with no lane (orphan); one item on two lanes; a session recorded under two projects; tokens in use not matching items in flight; the record and the vault disagree | freeze the pipe with the reason; no reap, no transition |
| **Unsafe ground** | a red default branch in a lane's project; the backlog's schema gate failing; a fetch of the backlog or the record failing | freeze the pipe with the reason |
| **Stall** | every lane idle while admissible items exist for 3 ticks *(proposal)*; nothing admissible while open work waits in review; the loop's own last tick older than two intervals | report in the window report and as a gauge; never freeze |

| Parameter | Value |
|---|---|
| `stale_after` | 2 ticks (20 min at the proposed interval) *(proposal)* |
| `max_stale_reaps` | 2 *(proposal)* |

The watchdog's only backlog arc is the give-back; it never merges, closes, creates or widens
anything.

## 10 · The record repository

A private repository named in the instance config, never the framework repository, never a
place for secrets. It holds the loop's state (pipe, lanes, controls), each tick's plan and
results, an append-only event log, the run log, the reflections, and the window reports.
Tracker ids may appear in it. The loop fetches before every write and commits once per tick
phase; a push that is not a fast-forward means another loop wrote, and this one stops. The
window report is also filed in the instance's memory. Retention: everything is kept, since it
is text and the history is the audit trail *(proposal)*.

## 11 · Configuration

Instance-level. The prototype loop (`pipeline/tick.py`) reads a YAML file named on its command
line today; the intended home is the estate-config namespace `meta-os.swarm`
([[systems/config]]), which is **not in the schema yet**. The architecture decision fixes the
final key set (it adds at least the reserves, the record repository and the executable
spaces); the model's keys and defaults are:

| Key | Meaning | Default |
|---|---|---|
| `lanes` | `m_max`, the lane slots | 5 from the sizing (§2); 3 *(proposal)* for a proof of concept |
| `tokens` | `N`, the CONWIP cap | `2 × lanes` |
| `fairness_share` | the largest share of the tokens one space may hold | 0.5 |
| `automerge_classes` | change classes that skip the PO | `[]` |
| `review_sla_days` | the review-age limit that stops new work for a space | 5 |
| `lane_budget` | a run's cap before it is reaped: its expected cost × 3 | 3 |
| `tick` | the tick interval | 10 min *(proposal)*; hourly is too slow to re-plan |

## 12 · Failure modes this design closes

| Failure | What closes it |
|---|---|
| Lanes end with the turn and nothing re-populates them | the dispatcher's tick |
| Work planned on a stale checkout | fetch before every read and every write |
| The review queue grows without bound | the PO's capacity in the sizing, oldest first, the review-age limit |
| More lanes, same throughput | the sizing says where the ceiling is; the budget says what is affordable |
| An item closed in a repository the auto-transition does not watch stays "in flight" | the automatic close in every repository a lane can touch |
| Two sessions mint the same id | reserved id counters per space |
| A run that never ends, a lane nobody notices is stuck | the watchdog (§9) |
| The week's allowance spent by Monday | the window-paced lane cap (§7) |

## 13 · Acceptance examples

Each is a test the implementation must pass, on fixtures; the instance repeats them on its real
backlog and records the outcome next to its decisions.

1. **Held on review.** Item B is `REFINED` and depends on A, which is `IN REVIEW`. B is not
   started; it is listed with the reason *waiting on A (IN REVIEW)*. When A becomes `DONE`, B is
   admissible at the next tick.
2. **Drain on rebind.** Lane 2 is working an item of project P when a `bind lane-2 Q` control
   arrives. Lane 2 shows *draining*, takes nothing new, and binds to Q only after the run ends
   in a PR or a reap; no session of P is used for Q.
3. **The week caps the lanes.** With the windows of the worked example in §7 and `m_max = 3`,
   `m_cap = 1`; a second admissible item waits with the reason *budget cap*.
4. **Stop gives back without a retry.** `stop lane-1` while it works item C: C returns to
   `REFINED` with the *stopped by human* note, its retry count unchanged, and the lane shows
   `stopped` within the acknowledgement bound.
5. **Pipe wins.** With the pipe paused, `start lane-3` changes nothing, and the event records
   why.
6. **Stale reap, then hold.** A session stops emitting events. After `stale_after` the lane is
   reaped, the item goes back with retry + 1; the second reap of the same item holds it.
7. **Deadlock freezes.** A running item's blocker is moved back from `DONE`. The next tick
   freezes the pipe with that reason, and nothing starts until a human unfreezes.
8. **Planner falls back.** The solver is unreachable. The tick plans by reasoning, records the
   cause, and admission still decides what starts.
9. **Repair, not replan.** One item changes status between ticks. The planner repairs the
   previous plan, with edit distance under the churn cap, instead of solving cold.
10. **Not executable.** An admissible-looking item in a space the instance does not declare
    executable is never assigned, and is reported as *not executable*.

## 14 · Decisions this specification leaves to the PO

Nine, each with the proposal above as its default: the lane model (§6.3, `m_max`, drain); control
semantics (§6.2, acknowledgement bound); budget policy (§7, reserves, `K`, shape, last hour);
what the record repository logs and keeps (§10); the dashboard's write exception (§8.2); the
loop runtime (how it is woken, where it runs so that the solver is reachable, and how it
survives a reclaimed container); stale and deadlock thresholds (§9); proof-of-concept scope
(executable spaces and `m_max`); and the planning policy (§5.3). The instance records each
answer in its own tracker; this page then drops the *(proposal)* mark from the number.

## What this is not

Not a second orchestration stack: coordination *inside* a run stays with the host engine
([[systems/engine]]) and the agile pack's skill. Not a scheduler for humans: the PO station is
modelled so that its limits are visible, not so that it can be automated away. And not enabled
by default: like every hook and automation in this framework, it ships as a contract and is
switched on per instance ([[hooks/_index]], [[systems/packs]]).
