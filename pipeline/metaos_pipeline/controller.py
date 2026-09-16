"""Token-bandwidth regulator: AIMD on the WIP cap N, with a rate-limit guard.

    if rate_limit in {warning, rejected}: N <- max(N_min, N // 2); freeze
    elif burn > setpoint * (1 + eps):     N <- max(N_min, N // 2)
    elif burn < setpoint * (1 - eps) and lanes saturated: N <- min(N_max, N + 1)
    else: hold

Burn and setpoint are in the same unit (currency per hour by default). The controller never
stops a running lane; it changes only how many may start. See
systems/autonomous-pipeline-spike.md §5 for the plant model and the stability argument.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Decision:
    N_old: int
    N_new: int
    freeze: bool
    reason: str


def setpoint(budget: float, window_hours: float, reserve_fraction: float = 0.15,
             shape: float = 1.0) -> float:
    """Currency per hour the regulator aims at. `reserve_fraction` is held back for the
    overshoot bound (one lane's burn for one tick) and for speculation. `shape` > 1 spends
    faster early in the window (work ready by morning is worth more)."""
    usable = budget * (1.0 - reserve_fraction)
    return max(0.0, usable / max(window_hours, 1e-9) * shape)


def regulate(N: int, burn: float, target: float, rate_status: str,
             lanes_saturated: bool, N_min: int, N_max: int, eps: float = 0.15,
             warn_cap: int | None = None, active_lanes: int | None = None) -> Decision:
    """`warn_cap`: on an account-level *warning* (quota not yet exhausted) N is capped at this
    value instead of halved, so a persistent warning does not drive the pipeline to N_min;
    a *rejection* always halves and freezes."""
    N = int(N)
    status = (rate_status or "allowed").lower()
    if status in ("rejected", "exceeded"):
        new = max(N_min, N // 2)
        return Decision(N, new, True, f"rate limit '{status}': halve to {new} and freeze spawning this tick")
    if status in ("warning", "allowed_warning"):
        cap = warn_cap if warn_cap is not None else max(N_min, N // 2)
        if N > cap:
            return Decision(N, max(N_min, cap), False, f"rate limit '{status}': cap N at {cap}")
        # fall through to the burn rule with the cap as the ceiling
        N_max = min(N_max, max(N_min, cap))
    if target <= 0:
        return Decision(N, N_min, True, "no budget: hold at minimum and freeze")
    if burn > target * (1.0 + eps):
        # Refractory decrease (ADR-MOS-12 correction): the regulator never stops a lane
        # mid-item, so a decrease only reaches the plant once running lanes drain below the
        # cap. Halving again before that collapses the cap while burn has not moved.
        if active_lanes is not None and active_lanes > N:
            return Decision(N, N, False, f"burn {burn:.2f}/h above setpoint {target:.2f}/h but {active_lanes} lanes still draining above cap {N}: refractory hold")
        new = max(N_min, N // 2)
        return Decision(N, new, False, f"burn {burn:.2f}/h above setpoint {target:.2f}/h: halve to {new}")
    if burn < target * (1.0 - eps):
        if lanes_saturated:
            new = min(N_max, N + 1)
            return Decision(N, new, False, f"burn {burn:.2f}/h below setpoint {target:.2f}/h and lanes saturated: +1 to {new}")
        return Decision(N, N, False, f"burn {burn:.2f}/h below setpoint {target:.2f}/h but lanes not saturated: hold")
    return Decision(N, N, False, f"burn {burn:.2f}/h within ±{eps:.0%} of setpoint {target:.2f}/h: hold")


def over_cap(lane_cost: float, cap: float) -> bool:
    return cap > 0 and lane_cost > cap


def budget_exhausted(spent: float, budget: float) -> bool:
    return budget > 0 and spent >= budget
