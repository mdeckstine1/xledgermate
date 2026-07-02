"""Bracket edge cleanup preset — trust entries + closer TP / wider SL (anti-churn)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from alpha.hud.operator_phase import OPERATOR_PHASE_KEY

# One-click bundle for SL-heavy / zero-TP chop (pairs with walk-away; no Agent Smith change).
BRACKET_EDGE_CLEANUP_OVERRIDES: Dict[str, Any] = {
    OPERATOR_PHASE_KEY: "trust",
    "trading_enabled": True,
    # Risk & entry — fewer, patient bids
    "alpha_risk_per_trade_pct": 2.0,
    "alpha_buy_limit_offset_pct": 0.20,
    "alpha_sell_limit_offset_pct": 0.12,
    "alpha_min_edge_threshold_pct": 0.08,
    "alpha_weakness_deviation": 0.05,
    "alpha_max_pending_buys": 1,
    "alpha_max_pending_sells": 2,
    "alpha_stale_pending_buy_enabled": True,
    "alpha_stale_pending_buy_max_drift_pct": 0.35,
    "alpha_stale_pending_buy_max_age_seconds": 0,
    "alpha_ta_weight": 0.65,
    "alpha_ta_min_buy_score": 3.0,
    "alpha_ta_min_sell_score": 3.5,
    # Re-entry — stop re-buying the same chop pocket
    "alpha_reentry_sl_cooldown_cycles": 45,
    "alpha_reentry_sl_cooldown_minutes": 90.0,
    "alpha_reentry_sl_min_ta_score": 3.0,
    "alpha_reentry_sl_stabilization_pct": 0.05,
    "alpha_reentry_scratch_sl_cooldown_cycles": 12,
    "alpha_reentry_scratch_sl_max_loss_pct": 0.10,
    # Brackets — closer TP, slightly wider SL, deferred arm
    "initial_stop_loss_pct": 0.025,
    "take_profit_pct": 0.025,
    "take_profit_rr": 1.5,
    "bracket_trailing_enabled": True,
    "trailing_step_pct": 1.5,
    "alpha_deferred_sl_enabled": True,
    "alpha_deferred_sl_arm_buffer_pct": 0.15,
}

BRACKET_EDGE_DESCRIPTION = (
    "Bracket edge cleanup: trust phase, 1 pending buy, higher min buy TA, "
    "longer SL re-entry cooldown, TP ~2.5% / SL ~2.5% (RR 1.5), deferred SL buffer. "
    "Does not enable full SKYNET or change Agent Smith."
)


def bracket_edge_preset_payload() -> Dict[str, Any]:
    return {
        "label": "Bracket edge cleanup",
        "description": BRACKET_EDGE_DESCRIPTION,
        "operator_overrides": dict(BRACKET_EDGE_CLEANUP_OVERRIDES),
        "keys_applied": len(BRACKET_EDGE_CLEANUP_OVERRIDES),
    }


def apply_bracket_edge_preset(
    *,
    patch_overrides,
    base_config,
) -> Tuple[Dict[str, Any], List[str]]:
    merged, errors = patch_overrides(BRACKET_EDGE_CLEANUP_OVERRIDES, base=base_config)
    return merged, list(errors)
