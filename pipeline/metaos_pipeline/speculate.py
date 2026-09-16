"""Speculative execution of pending human decisions.

A declared decision has two branches. The pipeline runs both as speculative lanes when the
expected cost of the discarded branch is below the value of the latency saved:

    (1 - pi) * c_A + pi * c_B  <  L * v

Speculative lanes never merge, never transition, never write to the tracker; they draw from
the same token pool, capped at a share of N, and are skipped when the human's probability
for one branch is extreme (assume the likely branch instead).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SpecPlan:
    decision_id: str
    branches: list[dict]
    reason: str
    go: bool


def should_speculate(pi: float, c_a: float, c_b: float, latency_days: float, value_per_day: float,
                     pi_extreme: float = 0.9) -> tuple[bool, str]:
    if not (0.0 <= pi <= 1.0):
        return False, "pi out of range"
    if pi >= pi_extreme or pi <= 1.0 - pi_extreme:
        return False, f"pi={pi:.2f} is extreme: assume the likely branch and let the human veto"
    wasted = (1.0 - pi) * c_a + pi * c_b
    gain = latency_days * value_per_day
    if wasted < gain:
        return True, f"expected discarded cost {wasted:.2f} < latency value {gain:.2f}"
    return False, f"expected discarded cost {wasted:.2f} >= latency value {gain:.2f}"


def plan_speculation(decisions: list[dict], lanes: list[dict], N: int, free_tokens: int,
                     share: float = 0.34, latency_days: float = 0.5) -> list[SpecPlan]:
    """Choose which declared decisions to speculate on this tick.

    A decision is eligible if not already running or done, if both branches fit in the
    speculative share of N, and if the rule says go.
    """
    running_spec = [l for l in lanes if l.get("kind") == "spec" and l.get("status") in ("running", "spawning")]
    done_ids = {l.get("decision") for l in lanes if l.get("kind") == "spec" and l.get("status") in ("done", "reaped")}
    max_spec = max(0, int(N * share + 1e-9))
    room = min(free_tokens, max_spec - len(running_spec))
    plans: list[SpecPlan] = []
    for d in decisions:
        did = d["id"]
        if did in done_ids or any(l.get("decision") == did for l in running_spec):
            continue
        branches = d.get("branches") or []
        if len(branches) != 2:
            plans.append(SpecPlan(did, branches, "only two-branch decisions are speculated", False))
            continue
        c_a = float(branches[0].get("cost", 1.0)); c_b = float(branches[1].get("cost", 1.0))
        go, why = should_speculate(float(d.get("pi", 0.5)), c_a, c_b, float(d.get("latency_days", latency_days)),
                                   float(d.get("value_per_day", 1.0)))
        if go and room < 2:
            plans.append(SpecPlan(did, branches, f"rule says go ({why}) but only {room} speculative token(s) free", False))
            continue
        plans.append(SpecPlan(did, branches, why, go))
        if go:
            room -= 2
    return plans
