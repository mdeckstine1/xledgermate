"""Stack-growth preset — prioritize XRP coin count (accumulate, defer strength trims)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from alpha.hud.long_build_preset import LONG_BUILD_OPERATOR_OVERRIDES
from alpha.hud.operator_market_regime import OPERATOR_MARKET_REGIME_KEY
from alpha.hud.operator_phase import OPERATOR_PHASE_KEY

# Scale phase: high XRP target, RLUSD→XRP deploy, strength sells only when very heavy.
STACK_GROWTH_OPERATOR_OVERRIDES: Dict[str, Any] = {
    OPERATOR_PHASE_KEY: "scale",
    OPERATOR_MARKET_REGIME_KEY: "bull",
    "trading_enabled": True,
    "inventory_target_xrp_ratio": 0.88,
    "alpha_risk_capital_sync_portfolio": True,
    "alpha_risk_per_trade_pct": 3.0,
    "alpha_buy_limit_offset_pct": 0.20,
    "alpha_sell_limit_offset_pct": 0.14,
    "alpha_min_edge_threshold_pct": 0.08,
    "alpha_weakness_deviation": 0.04,
    "alpha_strength_deviation": 0.11,
    "alpha_bull_run_max_deviation": 0.12,
    "alpha_accumulation_max_deviation": 0.12,
    "alpha_max_pending_buys": 2,
    "alpha_max_pending_sells": 1,
    "alpha_stale_pending_buy_enabled": True,
    "alpha_stale_pending_buy_max_drift_pct": 0.38,
    "alpha_stale_pending_buy_max_age_seconds": 0,
    "alpha_ta_weight": 0.65,
    "alpha_ta_min_buy_score": 2.5,
    "alpha_ta_min_sell_score": 4.0,
    "alpha_ta_candle_interval_seconds": 7200,
    "alpha_reentry_sl_cooldown_cycles": 45,
    "alpha_reentry_sl_cooldown_minutes": 90.0,
    "alpha_reentry_tp_cooldown_cycles": 15,
    "alpha_reentry_tp_dip_pct": 0.08,
    "initial_stop_loss_pct": 0.03,
    "take_profit_pct": 0.03,
    "take_profit_rr": 2.0,
    "bracket_trailing_enabled": True,
    "trailing_step_pct": 2.0,
    "alpha_deferred_sl_enabled": True,
    "alpha_deferred_sl_arm_buffer_pct": 0.20,
    # Harvest only on extended legs — not routine rebalance-down.
    "alpha_accumulation_harvest_move_24h_watch_pct": 5.0,
    "alpha_accumulation_harvest_pullback_arm_pct": 1.25,
    "alpha_accumulation_harvest_trim_risk_pct": 1.5,
    "alpha_accumulation_dip_move_24h_arm_pct": 5.0,
    "alpha_accumulation_dip_bounce_arm_pct": 0.30,
    "alpha_accumulation_dip_buy_offset_pct": 0.22,
}

STACK_GROWTH_AGENT_PATCH: Dict[str, Any] = {
    "agent_enabled": True,
    "full_mode_enabled": False,
    "interval_cycles_min": 8,
    "interval_cycles_max": 12,
}

STACK_GROWTH_DESCRIPTION = (
    "Stack growth: scale + bull, 88% XRP target, 3% clips, weakness bids from RLUSD "
    "(offset 0.20 / drift 0.38), strength trims deferred until dev≥0.11 + ta_min_sell 4.0, "
    "max 1 pending sell / 2 buys, wider brackets (SL 3% / TP ~6%), harvest on extended legs only. "
    "Optimize for rising XRP coin count — not rebalance-down on rips."
)


def stack_growth_preset_payload() -> Dict[str, Any]:
    return {
        "label": "Stack growth (XRP count)",
        "description": STACK_GROWTH_DESCRIPTION,
        "operator_overrides": dict(STACK_GROWTH_OPERATOR_OVERRIDES),
        "agent_patch": dict(STACK_GROWTH_AGENT_PATCH),
        "long_build_comparison": compare_stack_growth_to_long_build(),
    }


def compare_stack_growth_to_long_build() -> Dict[str, Any]:
    """Highlight deltas vs long-build (rebalance/swing preset)."""
    different: Dict[str, Dict[str, Any]] = {}
    for key in sorted(set(LONG_BUILD_OPERATOR_OVERRIDES) | set(STACK_GROWTH_OPERATOR_OVERRIDES)):
        lb = LONG_BUILD_OPERATOR_OVERRIDES.get(key)
        sg = STACK_GROWTH_OPERATOR_OVERRIDES.get(key)
        if lb != sg:
            different[key] = {"long_build": lb, "stack_growth": sg}
    return {
        "different_operator_keys": different,
        "summary": (
            f"{len(different)} knob(s) differ from long-build — "
            "mainly higher XRP target (88%), higher strength_dev (0.11), "
            "fewer pending sells, harder TA sell gate, earlier weakness buys."
        ),
    }


def apply_stack_growth_preset(
    *,
    patch_overrides,
    merge_agent_patch,
    base_config,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    merged, errors = patch_overrides(STACK_GROWTH_OPERATOR_OVERRIDES, base=base_config)
    agent_merged, agent_errors = merge_agent_patch(STACK_GROWTH_AGENT_PATCH)
    all_errors = list(errors) + list(agent_errors)
    return merged, agent_merged, all_errors
