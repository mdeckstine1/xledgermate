"""Condensed scenario playbook for SKYNET / Grok context (mirrors ALPHA_TRADERS_MANUAL scenarios)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# Friendly HUD names → operator override keys (Grok may use either).
KNOB_ALIASES: Dict[str, str] = {
    "risk_per_trade_pct": "alpha_risk_per_trade_pct",
    "min_edge_threshold_pct": "alpha_min_edge_threshold_pct",
    "buy_limit_offset_pct": "alpha_buy_limit_offset_pct",
    "sell_limit_offset_pct": "alpha_sell_limit_offset_pct",
    "weakness_deviation": "alpha_weakness_deviation",
    "strength_deviation": "alpha_strength_deviation",
    "max_pending_buys": "alpha_max_pending_buys",
    "max_pending_sells": "alpha_max_pending_sells",
    "stale_pending_buy_max_drift_pct": "alpha_stale_pending_buy_max_drift_pct",
    "stale_pending_buy_enabled": "alpha_stale_pending_buy_enabled",
    "stale_pending_buy_max_age_seconds": "alpha_stale_pending_buy_max_age_seconds",
    "cycle_interval_seconds": "alpha_cycle_interval_seconds",
    "target_xrp_pct": "inventory_target_xrp_ratio",
    "ta_weight": "alpha_ta_weight",
    "ta_min_buy_score": "alpha_ta_min_buy_score",
    "ta_min_sell_score": "alpha_ta_min_sell_score",
    "tp_cooldown_cycles": "alpha_reentry_tp_cooldown_cycles",
    "sl_cooldown_cycles": "alpha_reentry_sl_cooldown_cycles",
    "tp_dip_pct": "alpha_reentry_tp_dip_pct",
    "sl_stabilization_pct": "alpha_reentry_sl_stabilization_pct",
    "reentry_enabled": "alpha_reentry_enabled",
}


def build_scenario_playbook() -> str:
    """Compact operator playbook for Grok (keep under ~4k chars)."""
    return """=== Scenario playbook (A–R) ===
Map decision.reason + inventory to a scenario, then suggest knob bundles from presets below.

Coupling rules:
- buy_limit_offset_pct >= min_edge_threshold_pct always.
- STICKY bids: stale_max_drift > buy_offset + spread (~0.10%). Example offset 0.12 → drift 0.35.
- CHASE bids: stale_max_drift ≈ buy_offset (expect mid_passed_entry cancel/replace).
- Size ≈ portfolio_xrp_equiv × (risk_per_trade_pct/100); check market_conditions recommended_max_buy_xrp.
- Limit buys fill when best ask <= bid, NOT when mid crosses entry.

A — Bid left behind (uptrend): offset 0.12, min_edge 0.08, drift 0.35, max_pending 1.
B — Patient sniper: offset 0.25–0.35, drift ≈ offset, max_pending 1–2.
C — Ladder clutter: drift 0.15, max_pending 1–3, stale on.
D — edge_below_threshold: raise offset OR lower min_edge.
E — Downtrend knife-catching: weakness↑, ta_min_buy↑, sl_cooldown↑, risk↓, offset↑.
F — Chop / more fills: offset 0.08–0.12, min_edge 0.05–0.08, weakness 0.03–0.04.
G — Entry keeps moving: drift 0.35–0.50, max_pending 1, max_age 0; NOT drift≈offset.
H — Small size (~13 RLUSD @ ~584 XRP): raise risk_per_trade_pct (2→3→4%); not offset.
I — RLUSD-heavy sell_block: normal; buys when dev≤−weakness; no strength sells until less RLUSD-heavy.
J — ta_buy_blocked / bearish: lower ta_min_buy or ta_weight; or wait.
K — post_sl_* re-entry: sl_cooldown, sl_stabilization, sl_min_ta_score; patient reload.
L — post_tp_* re-entry: tp_cooldown, tp_dip_pct, tp_min_ta_score.
M — balanced dev=: lower weakness to buy or raise strength_deviation to sell.
N — Pending bid no fill: passive limit; lower offset or wait for ask to hit bid.
O — XRP-heavy strength sells: strength_deviation, sell_limit_offset, ta_min_sell.
P — kill_switch / pause_bids / preflight: fix risk first, do not crank aggression.
Q — ta_warming_up: wait or ta_weight=0 advisory.
R — insufficient_ask_depth: book health, not risk knob.

Preset — sticky + ~26 RLUSD @ ~580 XRP portfolio:
  alpha_risk_per_trade_pct=4.0, alpha_buy_limit_offset_pct=0.12, alpha_min_edge_threshold_pct=0.08,
  alpha_stale_pending_buy_max_drift_pct=0.35, alpha_max_pending_buys=1,
  alpha_stale_pending_buy_max_age_seconds=0, alpha_cycle_interval_seconds=20

Natural language → keys: "stickier"→drift↑; "bigger orders"/"26 RLUSD"→risk_per_trade_pct;
"one bid"→max_pending_buys=1; "faster cycles"→cycle_interval_seconds↓; "eager fills"→offset↓.
When operator states desired settings in their prompt, output suggested_changes implementing them.
"""


def infer_scenario_hints(
    *,
    decision_reason: str = "",
    inventory: Optional[Dict[str, Any]] = None,
    reentry: Optional[Dict[str, Any]] = None,
    stale_snapshot: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Heuristic scenario letters for Grok (non-exhaustive)."""
    reason = (decision_reason or "").lower()
    inv = inventory or {}
    hints: List[str] = []
    dev = inv.get("deviation")
    label = str(inv.get("label") or "")

    if "edge_below" in reason or "edge" in reason and "threshold" in reason:
        hints.append("D")
    if "post_sl" in reason or "reentry_sl" in reason:
        hints.append("K")
    if "post_tp" in reason or "reentry_tp" in reason:
        hints.append("L")
    if "ta_buy_blocked" in reason or "ta_warming" in reason:
        hints.append("J" if "ta_buy" in reason else "Q")
    if "ta_warming" in reason:
        hints.append("Q")
    if "balanced dev" in reason:
        hints.append("M")
    if "max_pending_buys" in reason:
        hints.append("C")
    if "insufficient_ask_depth" in reason:
        hints.append("R")
    if "kill_switch" in reason or "pause_bids" in reason or "preflight" in reason:
        hints.append("P")
    if "sell_blocked" in reason or label in ("heavy_rlusd", "rlusd_heavy"):
        if dev is not None and float(dev) < -0.08:
            hints.append("I")
    if stale_snapshot:
        if int(stale_snapshot.get("would_cancel_count") or 0) > 0:
            hints.append("G")
        if int(stale_snapshot.get("over_cap_count") or 0) > 0:
            hints.append("C")

    re = reentry or {}
    if re.get("active") and re.get("in_cooldown"):
        exit_type = str(re.get("exit_type") or "")
        hints.append("K" if exit_type == "sl" else "L" if exit_type == "tp" else "")

    # Dedupe preserving order
    seen: set[str] = set()
    out: List[str] = []
    for h in hints:
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out[:6]


def build_skynet_user_message(*, user_prompt: str, context: str) -> str:
    """Wrap operator prompt with intent instructions for settings requests."""
    prompt = (user_prompt or "").strip()
    settings_cues = re.search(
        r"\b(set|configure|apply|change|want|need|make|use|preset|stickier|bigger|smaller|risk\s*\d|offset|drift|pending|cooldown|ta_|reentry)\b",
        prompt,
        re.I,
    )
    intent_block = (
        "Operator intent: The operator may describe desired settings in natural language. "
        "Translate goals into concrete suggested_changes (allowlist keys only). "
        "Use scenario presets from the playbook when they fit. "
        "If they ask for configuration or preset behavior, suggested_changes must list "
        "specific keys and numeric values unless unsafe — do not only explain in prose."
        if settings_cues
        else "Operator intent: Answer the question; include suggested_changes when knob adjustments would help."
    )
    return (
        f"Context:\n{context}\n\n---\n\n{intent_block}\n\nOperator prompt:\n{prompt}"
    )
