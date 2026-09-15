#!/usr/bin/env python3
"""
Swarm pipeline as a Markovian queueing network — analytic + discrete-event check.
Companion to systems/swarm-pipeline-queueing.md (findings) and systems/swarm-pipeline.md
(the architecture the findings size). Standard library only; `python3 swarm-pipeline-model.py`
prints every table in the findings doc, `--json` emits them as data.

Stations (items flow left→right; a fraction p loops back from review to a lane):

    refined backlog ──▶ [L] lanes (M/M/m, μL each) ──▶ [V] reviewers (M/M/r, μV) ──▶ [C] cadence delay ──▶ [P] PO (M/M/1, μP·attend)
                          ▲                                   │ p (rework)                                  │ q (auto-merge bypasses C and P)
                          └───────────────────────────────────┘

Two regimes are computed:
  * OPEN  (Jackson): Poisson arrivals λ of refined items; steady state exists iff every station
    has ρ < 1. Gives cycle time, WIP, utilisation per station.
  * CLOSED (CONWIP, mean-value analysis): N items circulate; the backlog is assumed
    inexhaustible (it is, today). Gives throughput X(N) and cycle time W(N) as a function of
    the WIP cap — i.e. how many lanes/tokens the loop should keep populated.

All rates are items/day. Nothing here is instance-specific; parameters are arguments.
"""
from __future__ import annotations
import math, random, argparse, json
from dataclasses import dataclass, asdict

# ---------- analytic building blocks ----------

def erlang_c(m: int, a: float) -> float:
    """P(wait) for M/M/m with offered load a = λ/μ (erlangs). Requires a < m."""
    if a >= m:
        return 1.0
    s = sum(a**k / math.factorial(k) for k in range(m))
    last = a**m / math.factorial(m) * (m / (m - a))
    return last / (s + last)

def mmc(lam: float, mu: float, m: int):
    """M/M/m: returns (rho, P_wait, Lq, Wq, W, L)."""
    a = lam / mu
    rho = a / m
    if rho >= 1:
        return dict(rho=rho, p_wait=1.0, Lq=math.inf, Wq=math.inf, W=math.inf, L=math.inf, stable=False)
    pw = erlang_c(m, a)
    Lq = pw * rho / (1 - rho)
    Wq = Lq / lam
    W = Wq + 1 / mu
    return dict(rho=rho, p_wait=pw, Lq=Lq, Wq=Wq, W=W, L=lam * W, stable=True)

def mm1_vacation(lam: float, mu: float, vac_mean: float, vac_cv2: float = 0.0):
    """M/M/1 with multiple vacations (exhaustive service). The server (PO) leaves whenever
    the queue empties and returns after a vacation of mean V (cv² = variance/mean²);
    a cadence of 'once a day' is V = 1 day deterministic (cv² = 0).
    Stochastic decomposition (Fuhrmann–Cooper): W = W_{M/M/1} + E[V²]/(2 E[V])."""
    rho = lam / mu
    if rho >= 1:
        return dict(rho=rho, W=math.inf, L=math.inf, stable=False)
    w_mm1 = 1 / (mu - lam)
    ev2 = vac_mean**2 * (1 + vac_cv2)
    w = w_mm1 + (ev2 / (2 * vac_mean) if vac_mean > 0 else 0.0)
    return dict(rho=rho, W=w, L=lam * w, stable=True)

@dataclass
class Params:
    lam: float = 8.0        # refined items arriving per day (open regime)
    m: int = 4              # lanes
    muL: float = 2.0        # items per lane-day (0.5 d service)
    r: int = 2              # reviewer agents
    muV: float = 6.0        # items per reviewer-day
    muP: float = 16.0       # PO decisions per day while attending
    po_attend: float = 0.5  # fraction of the day the PO attends the queue (capacity = muP*po_attend)
    po_vac: float = 1.0     # mean PO vacation length in days (cadence); 0 = always on
    po_cv2: float = 0.0     # vacation variability (0 deterministic, 1 exponential)
    p_rework: float = 0.2   # fraction of reviews sent back to a lane
    q_automerge: float = 0.0  # fraction of items that skip the PO (bot-approved tier)

def open_network(P: Params):
    # Jackson: visit ratios. Each item visits L and V 1/(1-p) times, P (1-q) times.
    v = 1 / (1 - P.p_rework)
    lamL = P.lam * v
    lamV = P.lam * v
    lamP = P.lam * (1 - P.q_automerge)
    L = mmc(lamL, P.muL, P.m)
    V = mmc(lamV, P.muV, P.r)
    PO = mm1_vacation(lamP, P.muP * P.po_attend, P.po_vac, P.po_cv2)
    stable = L["stable"] and V["stable"] and PO["stable"]
    W = (v * L["W"] + v * V["W"] + (1 - P.q_automerge) * PO["W"]) if stable else math.inf
    return dict(stable=stable, rhoL=L["rho"], rhoV=V["rho"], rhoP=PO["rho"],
                p_wait_lane=L["p_wait"], cycle_days=W, wip=P.lam * W if stable else math.inf,
                wip_at_po=PO["L"], wip_at_lanes=L["L"], lane_days_per_item=P.m / P.lam)

def closed_conwip(P: Params, N: int):
    """Exact mean-value analysis (Reiser–Lavenberg) for a closed product-form network with
    N circulating items (CONWIP tokens) and an inexhaustible backlog:
      L  lanes      — multi-server, m servers at rate μL
      V  reviewers  — multi-server, r servers at rate μV
      P  PO         — single server whose capacity is time-limited: μP·po_attend
      C  cadence    — infinite-server delay station: an item that becomes ready for the PO
                      waits on average E[V²]/(2E[V]) for the next PO session (Fuhrmann–Cooper
                      residual), independent of the other items, so it never queues.
    Returns X(N), W(N) and per-station utilisation."""
    v = 1 / (1 - P.p_rework)
    cadence = (P.po_vac * (1 + P.po_cv2) / 2) if P.po_vac > 0 else 0.0
    stations = [  # (visit ratio, service rate per server, servers, kind)
        (v, P.muL, P.m, "Q"),
        (v, P.muV, P.r, "Q"),
        (1 - P.q_automerge, P.muP * P.po_attend, 1, "Q"),
        (1 - P.q_automerge, (1 / cadence) if cadence > 0 else math.inf, 1, "IS"),
    ]
    K = len(stations)
    p = [[1.0] + [0.0] * N for _ in range(K)]
    out = []
    for n in range(1, N + 1):
        R = []
        for k, (vk, mu, c, kind) in enumerate(stations):
            s = 0.0 if mu == math.inf else 1 / mu
            if kind == "IS":
                R.append(vk * s)
            elif c == 1:
                Lprev = sum(j * p[k][j] for j in range(n))
                R.append(vk * s * (1 + Lprev))
            else:
                Lprev = sum(j * p[k][j] for j in range(n))
                corr = sum((c - 1 - j) * p[k][j] for j in range(0, min(c - 1, n)))
                R.append(vk * s / c * (1 + Lprev + corr))
        X = n / sum(R)
        newp = []
        for k, (vk, mu, c, kind) in enumerate(stations):
            pk = [0.0] * (N + 1)
            if kind != "IS" and mu != math.inf:
                for j in range(1, n + 1):
                    pk[j] = (vk * X / (mu * min(j, c))) * p[k][j - 1]
            pk[0] = max(0.0, 1 - sum(pk[1:n + 1]))
            newp.append(pk)
        p = newp
        util = [min(1.0, stations[k][0] * X / (stations[k][1] * stations[k][2])) if stations[k][3] == "Q" else 0.0 for k in range(K)]
        out.append(dict(N=n, X=X, W=n / X, util_lanes=util[0], util_review=util[1], util_po=util[2],
                        items_per_lane_day=X / P.m))
    return out

# ---------- discrete-event simulation (validation) ----------

def simulate(P: Params, days: float = 2000.0, seed: int = 1, conwip: int | None = None):
    """Event-driven simulation with exponential services, Poisson arrivals (open) or a CONWIP
    token pool (closed, backlog inexhaustible), PO with deterministic vacations of length po_vac
    taken whenever its queue empties. Returns throughput, mean cycle time, mean WIP."""
    rng = random.Random(seed)
    t = 0.0
    lane_free = P.m; rev_free = P.r; po_busy = False; po_away_until = 0.0
    qL, qV, qP = [], [], []
    events = []  # (time, kind, payload)
    import heapq
    def push(dt, kind, payload=None): heapq.heappush(events, (t + dt, kind, payload))
    done = 0; cycle_sum = 0.0; wip = 0; wip_area = 0.0; last = 0.0
    tokens = conwip
    def new_item():
        nonlocal wip
        wip += 1
        return dict(t0=t)
    if conwip is None:
        push(rng.expovariate(P.lam), "arr")
    else:
        for _ in range(conwip): qL.append(new_item())
    def try_lane():
        nonlocal lane_free
        while lane_free and qL:
            it = qL.pop(0); lane_free -= 1
            push(rng.expovariate(P.muL), "lane_done", it)
    def try_rev():
        nonlocal rev_free
        while rev_free and qV:
            it = qV.pop(0); rev_free -= 1
            push(rng.expovariate(P.muV), "rev_done", it)
    def try_po():
        nonlocal po_busy
        if not po_busy and qP and t >= po_away_until:
            it = qP.pop(0); po_busy = True
            push(rng.expovariate(P.muP * P.po_attend), "po_done", it)
    def finish(it):
        nonlocal done, cycle_sum, wip
        done += 1; cycle_sum += t - it["t0"]; wip -= 1
        if conwip is not None:
            qL.append(new_item())
    try_lane()
    while t < days:
        t_new, kind, it = heapq.heappop(events)
        wip_area += wip * (t_new - last); last = t_new; t = t_new
        if kind == "arr":
            qL.append(new_item()); push(rng.expovariate(P.lam), "arr")
        elif kind == "lane_done":
            lane_free += 1; qV.append(it)
        elif kind == "rev_done":
            rev_free += 1
            if rng.random() < P.p_rework: qL.append(it)
            elif rng.random() < P.q_automerge: finish(it)
            else: qP.append(it)
        elif kind == "po_done":
            po_busy = False; finish(it)
            if not qP and P.po_vac > 0:
                po_away_until = t + P.po_vac
                push(P.po_vac, "po_back")
        elif kind == "po_back":
            pass
        try_lane(); try_rev(); try_po()
    return dict(X=done / days, cycle_days=cycle_sum / max(done, 1), wip=wip_area / days)

# ---------- experiment grid ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    base = Params()
    results = {}

    # 1. Open regime: lanes vs PO cadence, at the estate's measured demand.
    grid = []
    for m in (2, 4, 6, 8, 12):
        for vac in (0.0, 0.5, 1.0):
            for q in (0.0, 0.5):
                P = Params(m=m, po_vac=vac, q_automerge=q)
                o = open_network(P)
                grid.append(dict(m=m, po_vac=vac, q=q, **{k: (round(v, 3) if isinstance(v, float) and math.isfinite(v) else v) for k, v in o.items()}))
    results["open_grid"] = grid

    # 2. Closed regime: throughput vs CONWIP N for several lane counts (backlog inexhaustible).
    closed = {}
    for m in (2, 4, 5, 6, 8, 10, 12):
        for q in (0.0, 0.5):
            P = Params(m=m, q_automerge=q, po_vac=1.0)
            closed[f"m={m},q={q}"] = [dict(N=r["N"], X=round(r["X"], 2), W=round(r["W"], 2),
                                           uL=round(r["util_lanes"], 2), uP=round(r["util_po"], 2)) for r in closed_conwip(P, 32) if r["N"] in (2, 4, 6, 8, 10, 12, 16, 24, 32)]
    results["closed_conwip"] = closed

    # 3. Pooling gain: n projects with m/n dedicated lanes each vs one pool of m lanes (same total λ).
    pooling = []
    for n in (2, 3, 4):
        for m in (4, 8, 12):
            if m % n: continue
            lam_i = base.lam / n
            v = 1 / (1 - base.p_rework)
            part = mmc(lam_i * v, base.muL, m // n)
            pool = mmc(base.lam * v, base.muL, m)
            pooling.append(dict(n=n, m=m, partitioned_Wq=round(part["Wq"], 3) if part["stable"] else "unstable",
                                pooled_Wq=round(pool["Wq"], 3) if pool["stable"] else "unstable",
                                partitioned_p_wait=round(part["p_wait"], 3), pooled_p_wait=round(pool["p_wait"], 3)))
    results["pooling"] = pooling

    # 4. Rework sensitivity.
    rework = []
    for p in (0.0, 0.2, 0.4, 0.6):
        o = open_network(Params(p_rework=p))
        rework.append(dict(p_rework=p, rhoL=round(o["rhoL"], 3), rhoP=round(o["rhoP"], 3),
                           cycle_days=round(o["cycle_days"], 2) if math.isfinite(o["cycle_days"]) else "unstable"))
    results["rework"] = rework

    # 5. Simulation cross-check of two analytic points.
    sim = {}
    for label, P, N in (("open m=4 vac=1", Params(m=4, po_vac=1.0), None),
                        ("closed m=8 q=0.5 N=12", Params(m=8, q_automerge=0.5, po_vac=1.0), 12)):
        s = simulate(P, days=3000, conwip=N)
        an = open_network(P) if N is None else [r for r in closed_conwip(P, N) if r["N"] == N][0]
        sim[label] = dict(sim={k: round(v, 2) for k, v in s.items()},
                          analytic=dict(X=round(an.get("X", P.lam), 2), cycle_days=round(an.get("cycle_days", an.get("W", 0)), 2)))
    results["simulation_check"] = sim

    if a.json:
        print(json.dumps(results, indent=1))
        return
    # human-readable
    print("== OPEN regime (λ=8/day, μL=2, r=2 reviewers μV=6, μP=16, p_rework=0.2) ==")
    print(f"{'m':>3} {'vac':>4} {'q':>4} {'stable':>6} {'ρL':>5} {'ρP':>5} {'Pwait':>6} {'cycle d':>8} {'WIP':>6} {'WIP@PO':>7}")
    for g in grid:
        print(f"{g['m']:>3} {g['po_vac']:>4} {g['q']:>4} {str(g['stable']):>6} {g['rhoL']:>5} {g['rhoP']:>5} {g['p_wait_lane']:>6} {g['cycle_days']:>8} {g['wip']:>6} {g['wip_at_po']:>7}")
    print("\n== CLOSED regime (CONWIP N, backlog inexhaustible, PO once a day) ==")
    for k, rows in closed.items():
        print(k, " ".join(f"N={r['N']}:X={r['X']},W={r['W']},uL={r['uL']},uP={r['uP']}" for r in rows))
    print("\n== POOLING (Wq days) =="); [print(r) for r in pooling]
    print("\n== REWORK =="); [print(r) for r in rework]
    print("\n== SIM CHECK =="); [print(k, v) for k, v in sim.items()]

if __name__ == "__main__":
    main()
