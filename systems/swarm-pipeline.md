---
type: system
tags: [os, system, swarm, pipeline, automation]
---
# Swarm Pipeline — m lanes over n projects, as a closed loop

[[systems/swarm-harness]] describes **one batch**: a sprint is cut into lanes, the lanes run,
the batch ships when every row reads *merged*. Nothing in that model says what happens next.
In practice nothing does: lanes are in-process agents that end with the turn that spawned
them, the batch file is ticked by hand, and the next batch waits for a human to open a
session and say "swarm". Between those moments the estate has zero lanes running, however
much refined work is waiting.

This document turns the batch into a **pipeline**: a loop that keeps a bounded number of
lanes populated across every project with ready work, releases capacity as items close, and
never asks the human for anything except the decisions that are genuinely theirs. It is
sized by [[systems/swarm-pipeline-queueing]], which models the loop as a Markovian queueing
network and says how many lanes, how much work in flight, and where the bottleneck sits.

## The pipeline in one picture

```
                 ┌──────────────── tokens released on DONE / NO GO ────────────────┐
                 ▼                                                                  │
 ready set ──▶ [D] dispatcher ──▶ [L] lanes (m) ──▶ [V] review ──▶ [C] cadence ──▶ [P] PO ──▶ close
 (vault query)    tick, N tokens      worktree,          bot +         wait for      human      auto-
                                      branch, PR         security      next session  merge/     transition
                                        ▲                   │ rework                 decide
                                        └───────────────────┘
                                                            └──── q · auto-merge tier ────────▶ close
```

Five stations, one control variable. **N**, the number of tokens, caps the items in flight
end to end (CONWIP). A lane may start an item only while a token is free; a token is freed
only when its item reaches `DONE` or `NO GO`. Everything else follows from that rule.

## Stations

### D · Dispatcher — the loop that was missing

An **automation**, not a skill: it runs on a schedule (a cloud routine or cron, hourly is
enough) and on the events that free capacity (a merge, a close). Each tick:

1. **Fetch, then read.** Every repository's default branch and the vault are fetched first;
   a plan computed on a stale checkout is the failure this estate has already paid for once
   (the framework's pre-commit fetch hook exists for the same reason).
2. **Build the ready set** from the vault, across every space with an active sprint:
   items whose status is `REFINED` (or `PLANNED` where the space allows it), whose
   dependencies are all `DONE`, whose definition of ready holds, and that carry no
   `blocked` marker. Epics are containers and never enter the set.
3. **Reap finished lanes.** For each lane recorded in the ledger: if its session has ended
   and its PR is merged, the auto-transition will have closed the item and freed the token;
   if the session ended without a PR, the item returns to the ready set with a `retry`
   count; if the session is stuck past its budget, it is interrupted and treated the same.
4. **Assign.** With `free = N − in_flight` tokens, pick items by priority and age, subject to
   the one rule of [[systems/swarm-harness]]: two items that touch the same module are the
   same lane, sequential. Pool lanes across projects (the queueing model shows why) but
   respect a per-space fairness cap so one project cannot starve the others.
5. **Spawn** one lane session per assignment and write the lane row to the ledger.
6. **Emit** the tick's gauges (see *Observability*).

The dispatcher holds no state of its own beyond the ledger; the vault is the source of
truth for item status, the ledger only for lane ↔ session ↔ branch bindings.

### L · Lane — one item, one branch, one session

A lane is a headless session ([[systems/engine]]) started with a contract, not a
conversation: the item id, the repository, the branch name, the definition of done, and the
write rules of the tracker. Inside the lane the [agile pack's `agile-swarm`
skill](https://github.com/meta-agentic/meta-discipline-agile) governs the work: fresh
worktree off the default branch, implement, clean-verify in the foreground, **in-lane
review before the PR** (this is what keeps the rework fraction low; the model shows every
0.2 of rework costs a quarter of lane capacity), open the PR, transition the item to
`IN REVIEW`, end. A lane never merges and never closes an item.

### V · Review — independent, automated, bounded

Every PR gets an independent reviewer pass and a security pass from agents that did not
write it. Findings that are defects go back to the lane (rework loop); findings that are
questions go to the PR thread. Review capacity is cheap relative to lanes and should never
be the queue that grows; give it more servers before giving the lanes more.

### C and P · Cadence and PO — the human station

The PO is a **single server with limited attendance**: decisions happen in sessions, not
continuously. Two consequences the model makes precise:

- The PO's *capacity* is decisions per session × sessions per day. Beyond the lane count
  that saturates it, more lanes add review queue, not throughput.
- The PO's *cadence* puts a floor under cycle time: an item that becomes ready waits on
  average half a cadence interval for the next session, whatever else is idle.

Three disciplines at this station:

1. **Oldest first, always.** The queue is served by age, not by recency. An estate that
   serves the freshest items first grows a tail of items nobody ever reaches; that tail is
   the signature of a LIFO station, and it is visible in the data that motivated this
   document.
2. **An auto-merge tier.** Classes of change that pass every automated gate and carry no
   human-judgement flag (documentation, test-only changes, dependency bumps within policy,
   bot-approved fixes below a size threshold) merge without the PO. The fraction that
   qualifies, `q`, is the single cheapest lever on throughput: at the estate's calibration
   it moves the ceiling from about 8 to about 10 items a day and halves the PO's load.
3. **A review SLA gauge.** Age of the oldest waiting item is a first-class metric; when it
   crosses the SLA the dispatcher stops spawning lanes for that space until it recovers.
   Starving the input is the only way to stop a queue from growing at a station you cannot
   speed up.

### Close — automatic

Merge triggers the auto-transition to `DONE` (the estate already has this for its main
code repository; extend it to every repository a lane can touch, or the pipeline will
report items as in flight that shipped days ago). `DONE` frees the token. The dispatcher's
next tick fills it.

## Multi-project: pooling with fairness

With `n` projects, the choice is between `n` dedicated pools of `m/n` lanes and one pool of
`m` lanes that any project can draw on. Pooling wins by a wide margin at the same lane count:
queueing delay drops by an order of magnitude and the probability that ready work waits for
a lane falls by two thirds ([[systems/swarm-pipeline-queueing]], *Pooling*). The one rule
still applies at assignment time, per repository, so pooling never puts two lanes in the
same module. The fairness cap (no space may hold more than a configured share of the
tokens) keeps a single project's deep backlog from monopolising the pool.

## Sizing rules

From the queueing spike, with `μL` items per lane-day, `p` rework fraction, `q` auto-merge
fraction, and `P` the PO's effective decisions per day:

| Quantity | Rule | Why |
|---|---|---|
| Lanes `m` | `m ≈ P / (μL · (1 − p) · (1 − q))` | lanes and PO saturate together; beyond this, lanes idle |
| Tokens `N` | `N ≈ 2m` to `3m` | throughput is within a few percent of its ceiling by `N = 2m`; every token past `3m` only lengthens cycle time (Little's law, `W = N / X`) |
| Reviewers | enough that review utilisation stays below 0.5 | review must never be the growing queue |
| Cadence | shorter sessions more often beat one long session | expected wait is half the interval, independent of session length |

At the calibration used in the spike (2 items per lane-day, 20 % rework, PO at 8 decisions
a day) these give `m = 5` and `N = 10–15` with no auto-merge tier, and `m = 10`,
`N = 20–30` with half the items auto-merging.

## Observability

Each tick appends one line to the instance's `automations/runs.jsonl` and, where the
framework's error-handler sink is enabled ([[hooks/_index]]), emits gauges:
`lanes_active`, `tokens_free`, `ready_set`, `review_queue`, `review_age_max_days`,
`throughput_24h`, `rework_24h`. The first four say whether the loop is populated; the last
three say which station is the bottleneck this week. A dashboard reads them; a human reads
them in the morning brief.

## Configuration

Instance-level, in the estate config ([[systems/config]]), namespace `meta-os.swarm`:

| Key | Meaning | Default |
|---|---|---|
| `lanes` | `m`, the lane pool size | 5 |
| `tokens` | `N`, the CONWIP cap | `2 × lanes` |
| `fairness_share` | max fraction of tokens one space may hold | 0.5 |
| `automerge_classes` | change classes that skip the PO | `[]` |
| `review_sla_days` | oldest-waiting threshold that pauses spawning for a space | 5 |
| `lane_budget` | wall-clock and token budget per lane before it is reaped | instance choice |
| `tick` | schedule expression | hourly |

## Failure modes this design closes

| Failure | Where it bit | What closes it |
|---|---|---|
| Lanes end with the turn; nothing re-populates | every batch so far | the dispatcher tick |
| Work planned on a stale checkout | sprint closes computed wrong | fetch-then-read, the pre-commit fetch hook |
| Review queue grows without bound | oldest items a month old | PO capacity in the sizing rule, oldest-first, the SLA gauge |
| More lanes, same throughput | intuition says "add lanes" | the model says where the ceiling is |
| Item closed in a repository the auto-transition does not watch | shipped work reported as in flight for a week | auto-transition on every lane-touchable repository |
| Two sessions mint the same id | concurrent lanes filing follow-ups | reserved id counters per space |

## What this is not

Not a second orchestration stack: coordination *inside* a lane stays with the host engine
([[systems/engine]]) and the agile pack's skill. Not a scheduler for humans: the PO station
is modelled so that its limits are visible, not so that it can be automated away. And not
enabled by default: like every hook and automation in this framework it ships as a
contract and is switched on per instance ([[hooks/_index]], [[systems/packs]]).
