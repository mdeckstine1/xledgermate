"""Walk-away preset — trust phase knobs + Agent Smith (guardrailed, not full SKYNET)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from alpha.hud.operator_phase import OPERATOR_PHASE_KEY

# Operator overrides: patient entries, anti-churn exits, trust phase bias.
WALKAWAY_OPERATOR_OVERRIDES: Dict[str, Any] = {
    OPERATOR_PHASE_KEY: "trust",
    "trading_enabled": True,
    "alpha_max_pending_buys": 2,
    "alpha_max_pending_sells": 2,
    "alpha_buy_limit_offset_pct": 0.18,
    "alpha_sell_limit_offset_pct": 0.12,
    "alpha_weakness_deviation": 0.05,
    "alpha_min_edge_threshold_pct": 0.08,
    "alpha_stale_pending_buy_max_drift_pct": 0.35,
    "alpha_stale_pending_buy_max_age_seconds": 0,
    "alpha_ta_weight": 0.65,
    "alpha_ta_min_buy_score": 2.5,
    "alpha_ta_min_sell_score": 3.5,
    "alpha_reentry_sl_cooldown_cycles": 45,
    "alpha_reentry_sl_cooldown_minutes": 90.0,
    "alpha_reentry_tp_cooldown_cycles": 12,
    "alpha_risk_per_trade_pct": 2.0,
}

# Agent Smith: enabled with default guardrails — NOT full autonomy (Phase 3).
WALKAWAY_AGENT_PATCH: Dict[str, Any] = {
    "agent_enabled": True,
    "full_mode_enabled": False,
    "interval_cycles_min": 4,
    "interval_cycles_max": 6,
}

WALKAWAY_DESCRIPTION = (
    "Walk-away mode: trust-phase knobs (patient buys, fewer weak sells), "
    "Agent Smith ON with guardrails, full SKYNET OFF."
)


def walkaway_preset_payload() -> Dict[str, Any]:
    return {
        "label": "Walk-away (trust + Agent Smith)",
        "description": WALKAWAY_DESCRIPTION,
        "operator_overrides": dict(WALKAWAY_OPERATOR_OVERRIDES),
        "agent_patch": dict(WALKAWAY_AGENT_PATCH),
    }


def apply_walkaway_preset(
    *,
    patch_overrides,
    merge_agent_patch,
    base_config,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    """
    Apply walk-away bundle. ``patch_overrides`` and ``merge_agent_patch`` are injected
    from operator runtime / skynet agent to avoid import cycles in routes.
    """
    merged, errors = patch_overrides(WALKAWAY_OPERATOR_OVERRIDES, base=base_config)
    agent_merged, agent_errors = merge_agent_patch(WALKAWAY_AGENT_PATCH)
    all_errors = list(errors) + list(agent_errors)
    return merged, agent_merged, all_errors
