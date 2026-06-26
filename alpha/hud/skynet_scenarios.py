"""Condensed scenario playbook for SKYNET / Grok context (mirrors ALPHA_TRADERS_MANUAL scenarios)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from alpha.hud.operator_phase import (
    OPERATOR_PHASE_KEY,
    build_operator_phase_playbook,
    phase_user_message_rules,
)
from alpha.hud.operator_market_regime import (
    OPERATOR_MARKET_REGIME_KEY,
    market_regime_user_message_rules,
    normalize_market_regime,
)


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

""" + build_operator_phase_playbook() + """

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
        over = int((stale_snapshot or {}).get("over_cap_count") or 0)
        if over > 0:
            hints.append("C")
        elif dev is not None and float(dev) < -0.05:
            hints.append("I")
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


def classify_prompt_intent(prompt: str) -> Dict[str, Any]:
    """Lightweight intent tags so Grok addresses operator goals, not only auto scenario hints."""
    p = (prompt or "").strip().lower()
    tags: List[str] = []
    if re.search(
        r"\b(bullish|strong\s+buy|buy\s+now|accumulat|deploy\s+rlusd|go\s+long|buy\s+side|load\s+up)\b",
        p,
    ):
        tags.append("bullish_buy")
    if re.search(r"\b(consolidat\w*|base\s+building|range\s+bound|sideways)\b", p):
        tags.append("consolidation")
    if re.search(r"\b(bearish|defensive|reduce\s+risk|stop\s+buying|pause\s+buy)\b", p):
        tags.append("defensive")
    if re.search(r"\b(full\s+summary|summarize|overview|state\s+of\s+the\s+bot)\b", p):
        tags.append("summary_request")
    if re.search(r"\b(ladder|clutter|stale|cancel.*bid|pending\s+buy)\b", p):
        tags.append("ladder_management")
    settings_cues = bool(
        re.search(
            r"\b(set|configure|apply|change|want|need|make|use|preset|stickier|bigger|smaller|risk\s*\d|offset|drift|pending|cooldown|ta_|reentry)\b",
            p,
            re.I,
        )
    )
    if settings_cues:
        tags.append("settings_request")
    return {"tags": tags, "has_settings_request": settings_cues}


def build_skynet_user_message(
    *,
    user_prompt: str,
    context: str,
    operator_phase: Optional[str] = None,
    market_regime: Optional[str] = None,
) -> str:
    """Put operator prompt first; scenarios are reference only."""
    prompt = (user_prompt or "").strip()
    intent = classify_prompt_intent(prompt)
    tags = intent.get("tags") or []

    lines = [
        "=== OPERATOR PROMPT (PRIMARY — your reasoning and summary must address this first) ===",
        prompt or "(empty)",
        "",
        "=== RESPONSE RULES ===",
        "1. Answer the operator prompt directly. Do NOT substitute an unrelated scenario preset.",
        "2. Automated `likely_scenarios` and the playbook below are REFERENCE ONLY — use when they align with operator intent.",
        "3. If operator describes market structure or strategy (e.g. consolidation + bullish → buy), translate that into analysis and knobs.",
    ]

    if "bullish_buy" in tags or ("consolidation" in tags and "defensive" not in tags):
        lines.extend(
            [
                "4. BULLISH / BUY intent detected: RLUSD-heavy + TA bullish → favor XRP accumulation knobs "
                "(e.g. alpha_buy_limit_offset_pct↓, alpha_weakness_deviation↓, alpha_ta_min_buy_score↓ if blocking, "
                "alpha_max_pending_buys≥1 to allow entries).",
                "   Do NOT tighten alpha_stale_pending_buy_max_drift_pct or cut max_pending unless operator asked to clear ladder clutter.",
            ]
        )
    elif "ladder_management" in tags:
        lines.append(
            "4. LADDER intent: address stale pending / max_pending using playbook scenarios G or C as appropriate."
        )
    elif "defensive" in tags:
        lines.append(
            "4. DEFENSIVE intent: prioritize capital protection — risk↓, cooldowns↑, patience on re-entry."
        )
    elif "summary_request" in tags:
        lines.append(
            "4. SUMMARY intent: structured state overview first; suggested_changes only if clearly warranted."
        )

    if intent.get("has_settings_request"):
        lines.append(
            "5. Operator requested specific settings — output concrete suggested_changes (allowlist keys), not prose only."
        )
    else:
        lines.append(
            "5. Include suggested_changes when knob adjustments serve operator goals; empty array is OK if HOLD is correct."
        )

    phase = operator_phase
    if phase is None and OPERATOR_PHASE_KEY + "=" in context:
        for line in context.splitlines():
            if line.startswith("phase="):
                phase = line.split("=", 1)[1].strip().split()[0]
                break
    lines.extend(phase_user_message_rules(phase or "trust"))

    regime = market_regime
    if regime is None and OPERATOR_MARKET_REGIME_KEY + "=" in context:
        for line in context.splitlines():
            if line.startswith("market_regime="):
                regime = line.split("=", 1)[1].strip().split()[0]
                break
    lines.extend(market_regime_user_message_rules(regime or "neutral"))

    lines.extend(["", "=== RUNTIME CONTEXT (secondary) ===", context])
    return "\n".join(lines)
