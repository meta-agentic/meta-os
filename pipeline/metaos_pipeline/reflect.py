"""Reflection: predicted vs measured, attribution, bounded action, escalation.

The predictor is the queueing model in systems/swarm-pipeline-model.py, loaded by path so
the pipeline never duplicates it. Reflection may act only at the parametric level and only
within the regulator's bounds; everything else is recorded and escalated.
"""
from __future__ import annotations

import importlib.util
import math
import os
import subprocess
import time
from typing import Any


def load_model(path: str):
    spec = importlib.util.spec_from_file_location("swarm_pipeline_model", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load model at {path}")
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def predict(model, m: int, N: int, cal: dict) -> dict:
    P = model.Params(m=max(1, m), muL=cal.get("muL", 2.0), p_rework=cal.get("p", 0.2),
                     q_automerge=cal.get("q", 0.0), muP=cal.get("muP", 16.0),
                     po_attend=cal.get("po_attend", 0.5), po_vac=cal.get("po_vac", 1.0))
    rows = model.closed_conwip(P, max(1, N))
    r = rows[-1]
    return {"X": round(r["X"], 2), "W": round(r["W"], 2), "util_lanes": round(r["util_lanes"], 2),
            "util_po": round(r["util_po"], 2)}


def closes_last_24h(vault: str) -> int:
    """Items that entered output/ in the last 24 h, from the vault's git history."""
    try:
        out = subprocess.run(["git", "-C", vault, "log", "--since=24 hours ago", "--diff-filter=A",
                              "--name-only", "--format=", "--", "*/output/*.md"],
                             capture_output=True, text=True, timeout=60).stdout
    except (subprocess.SubprocessError, OSError):
        return -1
    return len({l for l in out.split("\n") if l.strip() and not l.endswith("_index.md")})


def measure(vault: str, lanes: list[dict], runs: list[dict], burn: float, spent: float) -> dict:
    running = [l for l in lanes if l.get("status") in ("running", "spawning")]
    reviewed = [l for l in lanes if l.get("status") == "in_review"]
    done = [l for l in lanes if l.get("status") == "done"]
    reworked = [l for l in lanes if l.get("rework")]
    durations = [float(l["ended"]) - float(l["started"]) for l in lanes
                 if l.get("ended") and l.get("started")]
    return {
        "lanes_active": len(running),
        "in_review_by_pipeline": len(reviewed),
        "done_by_pipeline": len(done),
        "closes_24h_vault": closes_last_24h(vault),
        "lane_hours_median": round(sorted(durations)[len(durations) // 2] / 3600, 2) if durations else None,
        "rework_share": round(len(reworked) / max(1, len(done) + len(reviewed) + len(reworked)), 2),
        "burn_per_hour": round(burn, 3),
        "spent": round(spent, 3),
        "yield_items_per_unit": round((len(done) + len(reviewed)) / spent, 3) if spent > 0 else None,
    }


def attribute(predicted: dict, measured: dict, decision_reason: str, N: int, m: int) -> tuple[str, list[str]]:
    """One-paragraph attribution plus escalations. Deterministic rules; the human reads them."""
    notes: list[str] = []
    esc: list[str] = []
    active = measured["lanes_active"]
    if active == 0 and N > 0:
        notes.append("no lane is active although tokens exist: either the ready set is empty, "
                     "every candidate is blocked by the one rule or a paused space, or the harness has not executed the plan")
    if measured["in_review_by_pipeline"] >= max(2, N):
        notes.append("the pipeline's own output is queued at the human station: throughput is now bounded by the review cadence, not by lanes")
        esc.append("review queue holds pipeline output; decide the auto-merge classes or hold a review session")
    if measured["rework_share"] > 0.4:
        notes.append("rework above 0.4 multiplies lane load by more than 1.6: in-lane review is not catching defects")
        esc.append("rework share high; inspect the last reworked lanes' review findings")
    if measured["lane_hours_median"] and measured["lane_hours_median"] > 6:
        notes.append("median lane exceeds six hours: service time is far above the calibration's half day; recalibrate muL before trusting the predicted X")
    if measured["closes_24h_vault"] == 0 and measured["done_by_pipeline"] == 0 and active:
        notes.append("nothing closed in 24 h while lanes ran: expected in a first window (cadence floor) unless it persists past one human round")
    if not notes:
        notes.append("measured within the model's envelope for this window; no residual to attribute yet")
    para = " ".join(n[0].upper() + n[1:] + "." for n in notes) + f" Regulator: {decision_reason}."
    return para, esc


def record(tick: int, window: str, predicted: dict, measured: dict, decision, calibration: dict,
           paused: list[str], escalations: list[str], attribution: str) -> dict:
    return {
        "tick": tick, "window": window,
        "predicted": predicted, "measured": measured,
        "residuals": {"X_24h_minus_pred": (measured["closes_24h_vault"] - predicted["X"])
                      if measured["closes_24h_vault"] >= 0 else None},
        "attribution": attribution,
        "action": {"N": [decision.N_old, decision.N_new], "freeze": decision.freeze,
                   "paused_spaces": paused, "reason": decision.reason},
        "escalations": escalations,
        "calibration": calibration,
    }
