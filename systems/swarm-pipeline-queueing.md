---
type: system
tags: [os, system, swarm, pipeline, queueing, spike]
---
# Swarm Pipeline — queueing analysis (spike findings)

The spike behind [[systems/swarm-pipeline]]. Question: *for a swarm of `m` lanes serving
`n` projects, which configuration delivers the most closed items per day, at what cycle
time, and where is the bottleneck?* Method: model the pipeline as a Markovian queueing
network, solve it in closed form where the theory allows and by exact mean-value analysis
where it does not, and cross-check one point of each regime with a discrete-event
simulation. Everything here is reproducible from
[[systems/swarm-pipeline-model.py|swarm-pipeline-model.py]] (standard library only).

## The model

```
 refined ─▶ [L] lanes M/M/m ─▶ [V] review M/M/r ─▶ [C] cadence delay (∞-server) ─▶ [P] PO M/M/1 ─▶ closed
                ▲                    │ p rework                                            │
                └────────────────────┘                    q auto-merge ───────────────────┘ (skips C and P)
```

| Symbol | Meaning | Calibration used below |
|---|---|---|
| `λ` | refined items arriving per day (open regime only) | 8 |
| `m`, `μL` | lanes, items per lane-day | varied, 2 |
| `r`, `μV` | reviewer agents, items per reviewer-day | 2, 6 |
| `μP · a` | PO decisions per day while attending × attending fraction | 16 × 0.5 = 8 |
| `V` | PO cadence: interval between sessions, days | 1 (deterministic) |
| `p` | fraction of reviews sent back to a lane | 0.2 |
| `q` | fraction of items that merge without the PO | 0 or 0.5 |

The calibration is one estate's fortnight: two items per lane-day is what its swarm days
delivered per lane; eight decisions a day is its average close rate over a period in which
the PO was the only merger; twenty percent rework is the share of PRs that went back for a
second push. Replace them with your own before believing a number to the second digit. The
*shape* of every result below survives any calibration in the same order of magnitude.

Two regimes:

- **Open** (Jackson network): work arrives as a Poisson stream at rate `λ`. Steady state
  exists only if every station is under-utilised; otherwise some queue grows without
  bound. Answers "can this configuration keep up with this demand?"
- **Closed** (CONWIP): `N` tokens circulate and the backlog is inexhaustible, which is the
  honest description of an estate with more refined work than lanes. Solved by exact
  mean-value analysis with multi-server stations and an infinite-server delay station for
  the cadence. Answers "what throughput and cycle time does a lane count and a WIP cap
  buy?"

The cadence station is the one non-obvious modelling choice. A PO who works in sessions is
a server on *vacation* between them; an item that becomes ready while the PO is away waits
the residual of the interval, `E[V²]/2E[V]`, which for a deterministic daily session is
half a day (Fuhrmann–Cooper decomposition). That wait is independent across items, so it
is a delay, not a queue. Time-limited attendance is separate: it caps the PO's capacity at
`μP · a` decisions a day.

## Findings

### F1 · Without an auto-merge tier the PO is the ceiling, at any lane count

Open regime, `λ = 8`, `q = 0`: the PO station sits at utilisation 1.0 for every `m`. The
system is unstable no matter how many lanes run. With `q = 0.5` the PO drops to 0.5 and
the system is stable from `m = 6` upward.

| `m` | `q` | stable | ρ lanes | ρ PO | cycle days | WIP |
|---|---|---|---|---|---|---|
| 4 | 0 | no | 1.25 | 1.00 | ∞ | ∞ |
| 6 | 0 | no | 0.83 | 1.00 | ∞ | ∞ |
| 6 | 0.5 | yes | 0.83 | 0.50 | 2.05 | 16.4 |
| 8 | 0.5 | yes | 0.63 | 0.50 | 1.72 | 13.7 |
| 12 | 0.5 | yes | 0.42 | 0.50 | 1.68 | 13.5 |

### F2 · Throughput saturates; the knee is at `m ≈ 5` lanes (no auto-merge) or `m ≈ 8–10` (half auto-merge)

Closed regime, throughput `X` in items per day against tokens `N`, PO once a day:

| `m` | `q` | `N = 2m` | `N = 3m` | ceiling | bound by |
|---|---|---|---|---|---|
| 2 | 0 | 2.41 | 2.94 | 3.2 | lanes |
| 4 | 0 | 4.72 | 5.73 | 6.4 | lanes |
| 5 | 0 | 5.67 | 6.6 | 7.6 | lanes ≈ PO |
| 6 | 0 | 6.42 | 7.2 | 7.9 | PO |
| 8 | 0 | 7.35 | 7.9 | 8.0 | PO |
| 12 | 0 | 7.88 | 8.0 | 8.0 | PO |
| 4 | 0.5 | 5.65 | 6.25 | 6.4 | lanes |
| 6 | 0.5 | 7.93 | 8.6 | 9.2 | lanes |
| 8 | 0.5 | 9.18 | 9.6 | 9.6 | cadence |
| 12 | 0.5 | 9.59 | 9.6 | 9.6 | cadence |

Reading down the `q = 0` column: from 5 lanes to 12, the ceiling moves from 7.6 to 8.0.
Seven extra lanes buy five percent. Their utilisation falls from 0.95 to 0.42: they are
paid for and idle. With half the items auto-merging, the same seven lanes are worth
another 25 %, and the new ceiling is set by the cadence, not the PO.

### F3 · Tokens beyond `2m–3m` buy cycle time, not throughput

Little's law, `W = N / X`, with `X` flat past the knee: at `m = 8, q = 0.5`, going from
`N = 16` to `N = 32` moves throughput from 9.18 to 9.60 and cycle time from 1.7 to 3.3
days. The WIP cap is the pipeline's most important control: too low starves lanes, too
high doubles the age of everything in flight for nothing.

### F4 · Cadence sets the cycle-time floor

Even with idle lanes and an idle PO, an item cannot close faster than lane service + review
+ half a cadence interval + PO service, about 1.15 days at this calibration with a daily
session. Two sessions a day halve the cadence term; a session that is twice as long does
nothing for it. The wait is a property of the interval, not of the attention.

### F5 · Pooling lanes across projects is worth an order of magnitude in queueing delay

Same total demand, same total lanes, M/M/m at the lane station:

| projects `n` | lanes `m` | dedicated `m/n` each: wait (days) | one pool of `m`: wait (days) | P(ready work waits), dedicated → pooled |
|---|---|---|---|---|
| 2 | 8 | 0.107 | 0.028 | 0.32 → 0.17 |
| 4 | 8 | 0.321 | 0.028 | 0.48 → 0.17 |
| 3 | 12 | 0.022 | 0.000 | 0.10 → 0.01 |
| 4 | 4 | unstable | unstable | 1.0 → 1.0 |

One lane per project is unstable in both layouts at this demand: it is not a pooling
question, it is too few lanes. Above that, pooling is strictly better and the gap widens
with `n`. The one rule of [[systems/swarm-harness]] is a constraint on *assignment*, not on
*pooling*: a pooled lane still takes one module at a time.

### F6 · Rework multiplies lane load by `1 / (1 − p)`

| `p` | lane load multiplier | lanes needed for `λ = 8` at `μL = 2` |
|---|---|---|
| 0.0 | 1.00 | 4 |
| 0.2 | 1.25 | 5 |
| 0.4 | 1.67 | 7 |
| 0.6 | 2.50 | 10 |

An in-lane review before the PR is the cheapest lane you can add.

### F7 · The model holds where it should, and says where it does not

Simulation with exponential services, deterministic daily PO vacations, CONWIP tokens,
3 000 simulated days: at `m = 8, q = 0.5, N = 12` the simulation gives `X = 8.28`,
`W = 1.45` against the analytic `8.34` and `1.44`. The open-regime unstable point
(`m = 4, q = 0`) shows WIP in the thousands in simulation, as predicted.

What the model does **not** capture: heavy-tailed service (one item that takes a week),
priority starvation at the PO (a LIFO station leaves a tail of items that are never
served; the fix is a discipline, oldest-first, not a parameter), and correlated failures
(a broken main that stalls every lane at once). The first two are visible in the data
that motivated the spike; the design in [[systems/swarm-pipeline]] addresses them by
policy rather than by modelling.

## Sizing rules that fall out

- **Lanes:** `m ≈ P_eff / (μL · (1 − p) · (1 − q))`, where `P_eff = μP · a` is the PO's
  real decisions per day. Lanes and PO saturate together at this point; past it, lanes idle.
- **Tokens:** `N ≈ 2m` reaches ~90 % of the ceiling, `3m` ~97 %; beyond that only cycle time
  grows.
- **Cheapest levers, in order:** raise `q` (auto-merge tier), lower `p` (in-lane review),
  shorten the cadence interval, and only then add lanes.
- **Report both** utilisations every tick: lanes and PO. Whichever is near 1.0 is the
  bottleneck; the other's queue is where the waste is.

## Reproduce

```bash
python3 systems/swarm-pipeline-model.py          # the tables above
python3 systems/swarm-pipeline-model.py --json   # as data, for a dashboard or a notebook
```

Edit the `Params` defaults or construct `Params(...)` in a REPL to run your own calibration.
