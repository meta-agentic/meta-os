---
type: system
tags: [os, system, swarm, pipeline, autonomy, control, spike]
---
# Autonomous multi-lane pipeline — spike

**Question.** [[systems/swarm-pipeline]] gives the swarm a loop and
[[systems/swarm-pipeline-queueing]] sizes it. Both assume a human sets `m` and `N` and reads
the gauges. This spike asks what it takes for the pipeline to run **unattended between human
rounds**: to regulate its own token bandwidth, to reason about its own performance while it
runs, and to use the human's absence rather than wait it out. It ends in questions for a
reviewer to settle in an ADR, and a prototype that runs one night.

**Scope.** Architecture, the mathematics of acceleration and its limits, the latency budget,
the bottleneck ranking, a control law for token consumption, a reflection contract, and a
decision rule for speculative execution. Not in scope: replacing the host engine's in-lane
coordination ([[systems/engine]]), or removing the human from the decisions that are theirs.

## 1 · Architecture — three loops around one pipeline

```
                    ┌───────────────── reflection (every tick) ─────────────────┐
                    │  predicted vs measured · attribution · bounded adjustment │
                    └──────────────┬───────────────────────────────▲────────────┘
                                   ▼                               │ gauges
   ready set ─▶ [D] dispatcher ─▶ [L] lanes (m) ─▶ [V] review ─▶ [C] cadence ─▶ [P] human ─▶ close
      ▲            │  N tokens        │ burn                            │           │ decisions
      │            │                  ▼                                 │           │
      │      ┌─────┴──────────── token regulator ───────────────────────┘           │
      │      │  sensor: Σ usage/lane · setpoint: budget/h · law: AIMD on N          │
      │      └──────────────────────────────────────────────────────────────────────┘
      └──────────── speculative lanes: both branches of a pending decision ─────────┘
```

| Loop | Period | Actuates | Bounded by |
|---|---|---|---|
| **Dispatch** (ADR-MOS-11) | tick, plus merge events | which items start, on which lane | `N` tokens, fairness cap, the one rule |
| **Token regulator** | tick | `N` (and through it, `m` in use) | `N ∈ [N_min, N_max]`, one step per tick, hard freeze on rate-limit signals |
| **Reflection** | tick | writes a record; may move `N` by one within the regulator's bounds; may pause a space; escalates everything else | never writes item status, never merges, never changes budgets |
| **Speculation** | when a decision is pending and idle capacity exists | starts one lane per branch of the decision, output to a scratch area | never merges, never transitions, capped share of `N` |

The dispatcher is the only writer of item status and lane bindings. The regulator writes
one number. Reflection writes prose and, within the regulator's bounds, the same number.
Speculation writes into a scratch area a human reads at the next round. No loop can widen
its own bounds; that is the property that makes unattended operation safe rather than merely
possible.

## 2 · Acceleration — how much, and why it stops

### 2.1 The law

Let one lane close items at rate `μL`. With `m` lanes, a serialised station of capacity `P`
(the human), a rework fraction `p`, and pairwise coherency cost between lanes (rebases,
conflicts, shared-module contention), throughput follows the Universal Scalability Law:

```
X(m) = μL · m / (1 + σ (m − 1) + κ m (m − 1))
```

`σ` is contention: the fraction of a lane's time spent waiting for something another lane
holds (review capacity, a shared module, the human's session). `κ` is coherency: the cost of
keeping `m` lanes consistent with one another, which grows with the number of *pairs*.
Amdahl is the `κ = 0` case. The queueing spike gives `σ` a concrete origin: the human station
saturates at `P_eff / (1 − q)` items a day, so `σ ≈ μL / P_eff` once that station is busy.

### 2.2 The three ceilings, in order

1. **Capacity ceiling.** `X ≤ P_eff / ((1 − q)(1 − p))`. Reached at `m* = P_eff / (μL (1 − p)(1 − q))`.
   Past `m*`, lanes idle. From the queueing spike at its calibration: `m* ≈ 5` with no
   auto-merge, `≈ 10` at `q = 0.5`.
2. **Coherency peak.** With `κ > 0` the curve has a maximum at `m_peak = √((1 − σ) / κ)` and
   *falls* beyond it: more lanes, fewer items. `κ` is what merge conflicts and a red default
   branch look like in aggregate. A pipeline that keeps `m` below `m_peak` never sees this;
   a pipeline that measures `κ` knows where `m_peak` is.
3. **Budget ceiling.** Lanes burn tokens whether or not they close items. With a budget `B`
   per day and a cost `c` per item-day of lane time, `m ≤ B / (c · 24 h)` regardless of
   the other two. This is the ceiling the regulator enforces (§ 5).

### 2.3 Worked numbers

At the queueing calibration (`μL = 2`, `p = 0.2`, `P_eff = 8`), single-lane throughput is
about 1.4 items a day once review and cadence are included. Speed-up over one lane:

| `q` | `m` | `X` | speed-up | lane utilisation | items per lane-day |
|---|---|---|---|---|---|
| 0 | 1 | 1.4 | 1.0 | 0.85 | 1.4 |
| 0 | 5 | 7.6 | 5.4 | 0.95 | 1.5 |
| 0 | 12 | 8.0 | 5.7 | 0.42 | 0.67 |
| 0.5 | 8 | 9.6 | 6.9 | 0.75 | 1.2 |
| 0.8 | 12 | ~11 | ~8 | 0.6 | 0.9 |

The right-hand columns are what the regulator trades against: each step right buys fewer
items per lane-day, and tokens are spent per lane-day.

### 2.4 Efficiency, not just speed

Define **yield** `Y = items closed / tokens spent`. `Y` is highest at `m ≈ m*` and falls on
both sides: below, cadence and review dominate cycle time and lanes wait; above, lanes wait
for the human. The regulator's objective is not maximum `X` but maximum `X` subject to `Y`
not falling below a floor; the reflection loop reports `Y` per tick so the floor is a
measured number, not a guess.

## 3 · Latency budget

| Stage | Typical | Floor | Lever |
|---|---|---|---|
| Dispatch wait (tick interval `T`) | `T / 2` | 0 with event-driven ticks | fire on merge and close events, not only on the clock |
| Lane start (container, clone, context) | 2–5 min | ~1 min | warm pool; shallow clones |
| Lane service `1/μL` | 0.5 day | item-dependent | in-lane review shortens rework, not service |
| Review | 0.5–2 h | minutes | more reviewer servers, they are cheap |
| Cadence residual `E[V²]/2E[V]` | 0.5 day at daily sessions | 0 with a continuous human, unreachable | shorter, more frequent sessions; the auto-merge tier removes the stage for `q` of items |
| Human decision | minutes | minutes | pre-read by reflection; both branches ready by speculation |
| Merge → close (CI, auto-transition) | 5–15 min | ~1 min | auto-transition on every repository |

Cycle-time floor at daily cadence is about **1.15 days**; with `q = 0.5` half the items skip
the cadence stage and the *mean* floor is about 0.9 days. Nothing the lanes do moves the
floor; only the human station's cadence and the auto-merge share do.

## 4 · Bottlenecks, ranked, with their signatures

| Rank | Bottleneck | Signature in the gauges | Remedy that is the pipeline's to apply | Remedy that is the human's |
|---|---|---|---|---|
| 1 | Human decision capacity | `util_po → 1`, review queue grows, lane utilisation falls | pause spawning for the space (SLA gauge); prepare decisions (speculation) | auto-merge classes; shorter cadence |
| 2 | Token budget / rate limits | burn > setpoint; rate-limit warnings | reduce `N` (regulator); reap over-budget lanes | raise the budget |
| 3 | Coherency (`κ`) | rework and conflict rate rise with `m`; `X` falls as `m` grows | lower `N`; serialise lanes sharing a module | split the module |
| 4 | Review capacity | review queue grows while `util_po < 1` | add reviewer servers | none needed |
| 5 | Hosted CI minutes | merge → close latency grows; kill switch trips | pause spawning | budget |
| 6 | Ready set exhausted | `ready_set = 0`, tokens free | speculation may use idle capacity | refine more items |

The ranking is by how often each was the binding constraint in the estate history the
queueing spike was calibrated on. The first is binding today.

## 5 · Token bandwidth — the regulator

### 5.1 Sensor

Every lane is a session with reported usage (input, cache, output tokens and cost). The
sensor sums, per tick, the *delta* of usage across all live and just-reaped lanes:

```
b(t) = Σ_lanes [usage(t) − usage(t − 1)] / T          # tokens (or currency) per hour
```

plus two discrete signals: the account's rate-limit status (allowed / warning / rejected)
and the per-lane cumulative spend against its cap. The sensor is one tick late by
construction: usage is reported after the work, and the tick is the sampling period.

### 5.2 Plant

Burn is proportional to work in flight: each in-flight item occupies a lane that burns at
roughly a constant rate `g` while active.

```
b(t + 1) ≈ g · N_active(t) + noise
```

`g` is the calibration constant the reflection loop estimates continuously as
`b / N_active` over a window. The plant is first-order with one tick of delay.

### 5.3 Setpoint

`b* = B / H` where `B` is the budget for the unattended window and `H` its length in hours,
optionally shaped: a higher setpoint early in the window (work ready for the morning is
worth more than work ready at noon) and a reserve held back for speculation and for
reaping.

### 5.4 Law — AIMD with a guard

```
if rate_limit ∈ {warning, rejected}:        N ← max(N_min, ⌊N / 2⌋); freeze spawning this tick
elif b > b* (1 + ε):                         N ← max(N_min, ⌊N / 2⌋)          # multiplicative decrease
elif b < b* (1 − ε) and lanes saturated:     N ← min(N_max, N + 1)              # additive increase
else:                                        hold
```

AIMD rather than a proportional law for three reasons. It is robust to an unknown and
drifting `g`: decrease is relative, so a mis-estimated plant gain cannot drive `N`
negative or into oscillation faster than one halving per tick. It converges, for a
first-order plant with delay, to a sawtooth around the setpoint whose amplitude is one step
(Chiu–Jain), which is the right shape when the cost of overshooting (spend) is asymmetric
with the cost of undershooting (idle tokens can be spent later). And its behaviour is
explainable in one sentence to the human who set the budget. The deadband `ε` (0.15 in the
prototype) keeps the loop from chattering on sampling noise.

Stability: with a one-tick delay and a step of one token, the largest overshoot is one lane's
burn for one tick, `g · T`. That is the reserve to hold back from `B`. With halving, recovery
from any overshoot takes `⌈log₂ N⌉` ticks at most.

### 5.5 What the regulator does not do

It does not stop a lane mid-item to save tokens; it stops *starting* lanes. A half-built item
is wasted spend; a token held back is not. The only mid-item stop is the per-lane cap, which
is a correctness guard (a lane looping on a failing test), not a bandwidth control.

## 6 · Reflection — reasoning about the pipeline while it runs

Each tick, after dispatch and regulation, the pipeline writes a **reflection record**:

```
{ tick, window,
  predicted: { X, W, util_lanes, util_po },      # from the queueing model at current N, m, q, p
  measured:  { X_24h, W_median, util_lanes, review_queue, review_age_max, burn, yield },
  residuals: { X, W, burn },                     # measured − predicted, with the sign explained
  attribution: "which station's residual is largest and what it implies",
  action: { N: old → new, paused_spaces: [...], reason },
  escalations: [ "what the human must decide at the next round, with the evidence" ],
  calibration: { muL, p, q, g }                  # the running estimates
}
```

The reflection loop reasons at three levels and is allowed to act on only the first:

1. **Parametric.** Re-estimate `μL`, `p`, `q`, `g` from the last window and re-run the sizing
   rule. Move `N` by at most one step within the regulator's bounds if the sizing rule and the
   regulator agree on the direction. Pause a space whose review age breaches the SLA.
2. **Structural.** Detect a bottleneck rank change (§ 4): the binding constraint moved from
   the human to coherency, or from tokens to CI. Recorded and escalated, never acted on.
3. **Semantic.** Notice that measured and predicted diverge in a way no parameter explains:
   items closing without merges, merges without closes, a space where every lane reworks.
   Recorded with the evidence, escalated, and if the anomaly is in the pipeline's own
   accounting, spawning is frozen until a human looks.

A reflection that cannot attribute a residual says so. The record's value is that a human
reading it at the next round sees the pipeline's reasoning, not only its numbers, and can
correct the reasoning rather than the number.

## 7 · Speculative execution — using the human's absence

A pending decision `D` with branches `A` and `B` blocks work behind it for at least one
cadence interval. If capacity is idle, the pipeline may run **both** branches as
speculative lanes, writing their outputs to a scratch area, so the human's round begins
with both answers in hand and the chosen one applies immediately.

### 7.1 The decision rule

Let `c_A`, `c_B` be the token costs of the branches, `π` the probability the human picks `A`,
`L` the latency saved (one cadence interval, at least), and `v` the value of a day of
latency on the work behind `D`. Sequential expected cost is `π c_A + (1 − π) c_B + L v`;
speculative cost is `c_A + c_B`. Speculate when

```
(1 − π) c_A + π c_B  <  L · v
```

that is, when the expected cost of the branch that will be thrown away is less than the value
of the latency saved. Two corollaries the prototype enforces: never speculate on a decision
with more than two live branches (the discarded cost grows linearly while `L` does not),
and never speculate when `π` is extreme (above 0.9 the cheaper move is to *assume* `A` and
let the human veto).

### 7.2 Isolation

A speculative lane never merges, never transitions an item, never writes to the tracker.
It produces artefacts (a branch, a draft, a diff, a note) in a scratch area named by the
decision and the branch, plus a one-paragraph summary the human reads first. When the
human picks, the dispatcher promotes the chosen artefact through the normal path and
discards the other. Speculative lanes draw from the same token pool and count against `N`,
capped at a configured share (one third in the prototype) so they can never starve
committed work.

### 7.3 Where the decisions come from

The reflection loop's escalations, the open-decision tables in ADRs and epics, and any item
whose acceptance criteria name a choice the human has not made. The prototype reads a
declared list; the ADR should decide whether the pipeline may *infer* decisions from prose.

## 8 · Trade-offs

| Choice | Buys | Costs | Position taken here |
|---|---|---|---|
| Event-driven ticks vs clock only | removes `T/2` dispatch latency | more wake-ups, more tokens on quiet nights | clock tick plus merge and close events; never a busy loop |
| AIMD vs PI control on `N` | robustness to unknown gain, explainability | slower convergence to the setpoint | AIMD; PI only if the gain is stable for a fortnight of records |
| Reflection may act vs may only report | closes the loop without a human | wrong reasoning acts | acts on level 1 only, within the regulator's bounds |
| Speculate both branches vs assume the likely one | zero latency on the decision | the discarded branch's tokens | the rule in § 7.1; assume when `π > 0.9` |
| Pool lanes across projects vs partition | order-of-magnitude lower queueing delay | fairness has to be enforced | pool with a share cap |
| Auto-merge tier | the cheapest throughput lever | a class misconfigured merges unreviewed | start with documentation and test-only classes |
| Per-lane token cap | bounds a runaway lane | may kill a legitimately long item | cap high (an item's estimate × 3), reap with a note, never silently |

## 9 · Prototype scope

One unattended window, hourly ticks, with the estate's real ready set. The prototype
implements: the ready-set query and assignment with the one rule and a fairness cap; the
token ledger, the regulator (§ 5) with `N ∈ [1, 4]`, a budget for the window and a
per-lane cap; the reflection record (§ 6) with the queueing model as the predictor; one
speculative decision with two branches under the rule in § 7. Lanes are headless sessions
started and reaped by the dispatcher. Every tick appends to the run log; the last tick of
the window writes a morning report.

What the window must measure before the ADR is accepted: `g` (burn per active lane per
hour), `μL` on real items, the regulator's response to the first over-budget tick, the
reflection records' attribution quality (did a human agree with the residual explanation),
and whether the speculative branches were both usable.

## 9a · Reviewer's corrections (recorded after review, kept for the record)

The reviewing ADR checked the algebra and changed four things this spike had wrong. The
sections above are left as written; read them with these corrections:

1. **The actuator is the lane cap `m`, not the token cap `N`.** Under release-at-DONE, half
   to two thirds of held tokens sit at review, cadence or the human station burning
   nothing, so the gain from `N` to burn switches between `g` and 0 on state the regulator
   cannot observe. Burn is `g · m_active`; regulate `m`, keep `N` as the fixed CONWIP cap.
2. **Decrease is refractory.** The regulator never stops a lane mid-item, so a decrease
   reaches the plant with time constant `1/μL`, not one tick. A second halving before
   `m_active ≤ m` collapses the cap while burn has not moved. The overshoot to reserve is
   one item's tokens per excess lane (`g/μL`), not one tick's (`g·T`).
3. **The capacity ceiling** is `min(m·μL(1−p), r·μV(1−p), P_eff/(1−q))`: rework revisits
   the lanes and the reviewers, not the human. At `q = 0.5` the model's 9.6/day ceiling is
   the *review* station at utilisation 1, not the cadence; four reviewers lift it to ~16.
   The `q = 0.8 → ~11` row in § 2.3 is therefore wrong.
4. **USL parameters must be fitted.** `σ ≈ μL / P_eff` does not reproduce the queueing
   model's curve; treat `σ` and `κ` as measured from the gauges, not derived.

Tokens release at DONE (one loop, as in the base pipeline); the prototype's
release-at-review with a separate review cap is a documented deviation for its first window.

## 10 · Questions for the reviewer's ADR

1. Is AIMD on `N` the right actuator, or should the regulator act on `m` (the number of
   lane sessions) directly, given that a token is only spent by a lane that exists?
2. Where does the reflection record live: the instance's automation run log, the vault's
   memory tier, or both? It carries instance data and must not enter the framework.
3. May reflection ever move `N` against the regulator's direction (for example, up when
   burn is high but the ready set is about to be exhausted)? The position here is no.
4. Should speculation be allowed to *infer* pending decisions from ADR and epic prose, or
   only from a declared list? The position here is declared only, until inference has a
   measured false-positive rate.
5. What is the correctness argument for the single-writer rule (only the dispatcher writes
   item status) under concurrent human edits to the same vault?
6. What must the morning report contain for the human round to take under fifteen minutes?
