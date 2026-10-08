---
type: system
tags: [os, system, swarm, pipeline, autonomy, specification]
---
# Autonomous pipeline — specification

**What this is.** The *what* of the autonomous multi-lane pipeline (ASML): a loop that runs
unattended, keeps a fixed set of lanes busy with work that is ready, and stays inside the
account's usage windows, while the product owner (PO) starts, pauses and stops it, and watches
it from the dashboard. [[systems/swarm-pipeline]] is the model it runs,
[[systems/swarm-pipeline-queueing]] sizes it, and [[systems/autonomous-pipeline-spike]] is the
prototype it grows from. The *how* (runtime, record schema, control contract, sensor source,
planner port) is the architecture decision that follows this specification; nothing here
prescribes a module.

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
| One item, one branch, one session; a server of the queueing model | [[systems/swarm-pipeline]], [[systems/swarm-pipeline-queueing]] | **run** (the model's `m` is the number of lanes, unchanged) |
| A row of the prototype's `lanes.json`, minted per item and forgotten | `pipeline/` | **run** record; `lanes.json` holds lanes |
| `cli` / `acp` / `auto` execution path of an engine | [[systems/engine]] | **engine route** |
| A sprint's stories grouped by project (dashboard *Lanes* widget); one git worktree (dashboard *Flow* tab) | dashboard | **project swimlane**; **worktree** |

The renames are applied by the work that touches each place, not in one sweep.

## 2 · What the PO asks of it — user stories

Each story is written as the PO would say it, followed by what makes it true.

- **S1 · Run unattended.** "When I am away, ready work keeps moving." The loop ticks without a
  human, at the interval in §5, survives its own process or container being reclaimed (its
  state is entirely in the record repository), and resumes from the last committed tick.
- **S2 · Only ready work.** "Never start something that cannot finish." An item is started
  only when it is admissible (§4): every blocker `DONE`, nothing holding it, its project
  free on some lane. Every item not started carries a reason.
- **S3 · Stay inside my limits.** "Do not burn the week on Monday." The number of working
  lanes is capped so that, at the measured mileage, neither window's reserve is touched before
  its reset (§6). Hitting a reserve or a provider warning freezes new starts.
- **S4 · Lanes per project.** "One lane, one project at a time, and agents never cross
  projects." A lane bound to a project takes that project's items first, rebinds only when
  drained, and no session is ever used for a second project.
- **S5 · Start, pause, stop.** "I can pause or stop one lane or the whole pipe, and start it
  again." Controls per lane and for the pipe, through the CLI and, on a local dashboard, the
  Pipeline tab; each is acknowledged by the loop within the bound in §5.
- **S6 · See it.** "I see each lane's state and numbers, and the whole pipe's." The Pipeline
  tab and `status` show per-lane and aggregate state (§7).
- **S7 · No silent stall.** "If a lane is stuck or the pipe is deadlocked, it is unstuck or I
  am told." A periodic watchdog reaps stale lanes, freezes on deadlock, and reports a stall
  (§8).
- **S8 · Plan ahead, cheaply.** "Use the planner when it is there, reason when it is not, and
  re-plan every few minutes without starting from zero." The planning policy in §4.3.
- **S9 · A record I can audit.** "I can see what it did and why." Every tick, control, start,
  end, reap and freeze is an event in the record repository with its reason (§9).
- **S10 · Morning page.** "I read one page in the morning." The window report lists what
  shipped, what waits for me, what was reaped or held and why, the windows, and the controls
  applied. It reads in under 15 minutes: the decisions waiting for the PO come oldest first,
  capped at what one session can take (8), and escalations at 5.

## 3 · Non-goals and the envelope

The pipeline **never** merges a PR, never moves an item to `DONE` or `NO GO`, never creates or
edits items, sprints or decision records, never edits the framework or pushes to a default
branch, never force-pushes, never changes its own bounds (`m_max`, `N`, reserves, caps,
executable projects), never spends past a window's reserve, and never clears a freeze. Its
writes to the backlog are three arcs only: start (`REFINED → IN PROGRESS`), hand-off
(`IN PROGRESS → IN REVIEW`, with a PR), and give-back (`IN PROGRESS → REFINED`, on reap,
failure or a human stop). The dashboard never writes the
record repository: it asks the CLI. Only a human clears a freeze. The pipeline is not enabled
by default; an instance switches it on, like every automation in this framework.

## 4 · Admission and planning

### 4.1 Admissible

An item is **admissible** when all hold:

1. its space is declared executable by the instance, and its project resolves;
2. its status is a ready status (default `REFINED`), and it is not an epic;
3. every blocker the dependency index lists for it is `DONE` now;
4. no blocking label, exclusion rule or hold applies (a hold is set by the watchdog, §8);
5. no run of the same concurrency key is in flight (today the key is space, repository and
   primary tag);
6. its retry count is below the cap (default 2);
7. its space is not paused by the review discipline: a space whose review queue is over its
   cap, or whose oldest item in review is older than the review-age limit, takes no new work
   until the queue drains.

Anything not admissible is reported with its first failing rule as the reason: *waiting on
X (status)*, *label L*, *excluded*, *held after N reaps*, *project busy*, *not executable*,
*review queue full*.

### 4.2 Assignment

Each tick, after reconciling controls (§5) and reaping (§8), free lanes take admissible items
in planner order, under four rules: a run starts only against a free **token** (the fixed
work-in-progress cap `N` counts items from start until `DONE` or `NO GO`, so items waiting in
review hold their token); a lane bound to project P takes P's items first; an idle, drained
lane may rebind to another project only when no lane already bound to that project is idle,
and only within the fairness share (no space holds more than half the tokens); and the number
of working lanes never exceeds `m_cap` (§6). `N` is set by a human from the sizing in
[[systems/swarm-pipeline-queueing]] and never by the loop.

### 4.3 Planning policy

The planner of record is the instance's configured solver when it answers, and agent
reasoning over the same inputs otherwise. The fallback is automatic, logged with its cause,
and never blocks a tick. The planner orders; admission decides (§4.1): a schedule never starts
a story the vault does not admit.

| Event | Response | Number |
|---|---|---|
| A small change: the diff since the last plan touches at most K items or one lane | incremental repair of the last plan, minimal disruption | K = 5 *(proposal)* |
| A repair whose edit distance exceeds the churn cap | discard, solve cold | cap = 10 *(proposal)* |
| Window start, or the full-replan interval elapsed | cold solve | every 6 h *(proposal)* |
| A sudden budget drop (`m_cap` falls by more than one) | drop the lowest-priority runs from the plan; no running item is stopped | — |
| The loop reorders the planner's admissible order | allowed, one recorded reason per change, counted as a gauge | — |

## 5 · Lanes, the pipe, and controls

### 5.1 States

Each lane has a **desired** state (`running`, `paused`, `stopped`, written only by a control)
and an **actual** state:

| Actual | Meaning |
|---|---|
| `idle` | bound or unbound, no item |
| `working` | one run in flight |
| `draining` | no new item; the run in flight ends (PR or reap), its sessions are archived, the worktree released; then `idle` |
| `paused` | desired `paused`, run (if any) finished, takes nothing |
| `stopped` | desired `stopped`; sessions interrupted, item given back |
| `stale` | flagged by the watchdog until reaped (§8) |

The pipe has a desired state `running | paused | stopped` and, set only by the loop, `frozen`
with a reason. The pipe wins: a lane cannot run while the pipe is paused, stopped or frozen.

### 5.2 Controls

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

### 5.3 Cadence

| Quantity | Value |
|---|---|
| Tick interval | 10 min *(proposal)*, and an early tick when a run ends or a control is made |
| Heartbeat poll of running sessions | every tick, and by a lighter heartbeat between ticks if the tick interval is raised |
| Lanes in the proof-of-concept (`m_max`) | 3 *(proposal)* |

### 5.4 Runtime

One loop at a time, holding nothing it cannot rebuild from the record repository. It must run
where the planner of record is reachable: while the solver is local-only, that is the machine
that hosts it; once the solver is a reachable service, any host that reaches it. A routine
wakes at most hourly, so the inner cadence of §5.3 comes from the loop itself.

*Proposal:* a self-paced loop inside one persistent session on the solver's host, sleeping
the tick interval between ticks and woken early by run-ending events; a local scheduler
restarts it if it dies, and the restarted loop resumes from the last committed tick. A loop
started where the solver is unreachable runs on reasoning and says so on every tick.

## 6 · Budget: the two windows and the lane cap

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
[[systems/autonomous-pipeline-spike]] still sets the working-lane count `m` tick by tick; `m_cap`
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

## 7 · Screens and commands, in words

### 7.1 Commands

| Command | What it does |
|---|---|
| `status` | Prints the pipe's desired and actual state, the freeze reason if any, both windows (remaining, reset, `ĝ_w`), `m_cap`, and one line per lane: state, project, item, elapsed, heartbeat age, retries. Read-only. |
| `control pipe start\|pause\|stop --reason R` | Writes the pipe's desired state to the record repository as an event. Refuses on a record clone that is behind its remote. |
| `control lane <id> start\|pause\|stop --reason R` | The same for one lane; refuses an unknown lane. |
| `control lane <id> bind <project> --reason R` | Requests a rebind; drains first if the lane is working. Refuses a project the instance does not declare executable. |
| `control pipe unfreeze --reason R` | Clears a freeze. Human only. |
| `report` | Writes the window report (S10). |

### 7.2 The Pipeline tab

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

## 8 · Watchdog: stale, deadlock, stall

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

## 9 · The record repository

A private repository named in the instance config, never the framework repository, never a
place for secrets. It holds the loop's state (pipe, lanes, controls), each tick's plan and
results, an append-only event log, the run log, the reflections, and the window reports.
Tracker ids may appear in it. The loop fetches before every write and commits once per tick
phase; a push that is not a fast-forward means another loop wrote, and this one stops. The
window report is also filed in the instance's memory. Retention: everything is kept, since it
is text and the history is the audit trail *(proposal)*.

## 10 · Acceptance examples

Each is a test the implementation must pass, on fixtures; the instance repeats them on its real
backlog and records the outcome next to its decisions.

1. **Held on review.** Item B is `REFINED` and depends on A, which is `IN REVIEW`. B is not
   started; it is listed with the reason *waiting on A (IN REVIEW)*. When A becomes `DONE`, B is
   admissible at the next tick.
2. **Drain on rebind.** Lane 2 is working an item of project P when a `bind lane-2 Q` control
   arrives. Lane 2 shows *draining*, takes nothing new, and binds to Q only after the run ends
   in a PR or a reap; no session of P is used for Q.
3. **The week caps the lanes.** With the windows of the worked example in §6 and `m_max = 3`,
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

## 11 · Decisions this specification leaves to the PO

Nine, each with the proposal above as its default: the lane model (§5.3, `m_max`, drain); control
semantics (§5.2, acknowledgement bound); budget policy (§6, reserves, `K`, shape, last hour);
what the record repository logs and keeps (§9); the dashboard's write exception (§7.2); the
loop runtime (how it is woken, where it runs so that the solver is reachable, and how it
survives a reclaimed container); stale and deadlock thresholds (§8); proof-of-concept scope
(executable spaces and `m_max`); and the planning policy (§4.3). The instance records each
answer in its own tracker; this page then drops the *(proposal)* mark from the number.
