"""Long-build preset — scale-phase bag growth (patient entries, wider brackets, swing overlays)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from alpha.hud.operator_market_regime import OPERATOR_MARKET_REGIME_KEY
from alpha.hud.operator_phase import OPERATOR_PHASE_KEY
from alpha.hud.walkaway_preset import WALKAWAY_AGENT_PATCH, WALKAWAY_OPERATOR_OVERRIDES

# Scale phase: patient sniper entries, fewer clips, wider bracket/harvest horizons.
LONG_BUILD_OPERATOR_OVERRIDES: Dict[str, Any] = {
    OPERATOR_PHASE_KEY: "scale",
    OPERATOR_MARKET_REGIME_KEY: "bull",
    "trading_enabled": True,
    "inventory_target_xrp_ratio": 0.80,
    "alpha_risk_capital_sync_portfolio": True,
    "alpha_risk_per_trade_pct": 3.0,
    "alpha_buy_limit_offset_pct": 0.22,
    "alpha_sell_limit_offset_pct": 0.14,
    "alpha_min_edge_threshold_pct": 0.08,
    "alpha_weakness_deviation": 0.05,
    "alpha_strength_deviation": 0.05,
    "alpha_bull_run_max_deviation": 0.10,
    "alpha_accumulation_max_deviation": 0.10,
    "alpha_max_pending_buys": 1,
    "alpha_max_pending_sells": 2,
    "alpha_stale_pending_buy_enabled": True,
    "alpha_stale_pending_buy_max_drift_pct": 0.40,
    "alpha_stale_pending_buy_max_age_seconds": 0,
    "alpha_ta_weight": 0.65,
    "alpha_ta_min_buy_score": 2.5,
    "alpha_ta_min_sell_score": 3.5,
    "alpha_ta_candle_interval_seconds": 7200,
    "alpha_reentry_sl_cooldown_cycles": 60,
    "alpha_reentry_sl_cooldown_minutes": 120.0,
    "alpha_reentry_tp_cooldown_cycles": 18,
    "alpha_reentry_tp_dip_pct": 0.10,
    # Wider trend brackets (opposite of bracket-edge cleanup).
    "initial_stop_loss_pct": 0.03,
    "take_profit_pct": 0.03,
    "take_profit_rr": 2.0,
    "bracket_trailing_enabled": True,
    "trailing_step_pct": 2.0,
    "alpha_deferred_sl_enabled": True,
    "alpha_deferred_sl_arm_buffer_pct": 0.20,
    # Swing overlays — harvest trims + dip deploy patience.
    "alpha_accumulation_harvest_move_24h_watch_pct": 4.0,
    "alpha_accumulation_harvest_pullback_arm_pct": 1.25,
    "alpha_accumulation_harvest_trim_risk_pct": 2.0,
    "alpha_accumulation_dip_move_24h_arm_pct": 5.0,
    "alpha_accumulation_dip_bounce_arm_pct": 0.30,
    "alpha_accumulation_dip_buy_offset_pct": 0.25,
}

# Agent Smith ON but slower cadence than walk-away (less micro-tuning).
LONG_BUILD_AGENT_PATCH: Dict[str, Any] = {
    "agent_enabled": True,
    "full_mode_enabled": False,
    "interval_cycles_min": 8,
    "interval_cycles_max": 12,
}

LONG_BUILD_DESCRIPTION = (
    "Long-build mode: scale phase + bull regime, 80% XRP target, 3% clips, sticky bids "
    "(offset 0.22 / drift 0.40), 1 pending buy, wider brackets (SL 3% / TP ~6% RR2), "
    "harvest/dip swing overlays, Agent Smith ON (8–12 cycles). "
    "Patient bag growth — not rip-chase accumulation."
)


def long_build_preset_payload() -> Dict[str, Any]:
    return {
        "label": "Long build (scale + swing)",
        "description": LONG_BUILD_DESCRIPTION,
        "operator_overrides": dict(LONG_BUILD_OPERATOR_OVERRIDES),
        "agent_patch": dict(LONG_BUILD_AGENT_PATCH),
        "walkaway_comparison": compare_long_build_to_walkaway(),
    }


def compare_long_build_to_walkaway() -> Dict[str, Any]:
    """Keys shared vs different — for HUD copy and tests."""
    shared: List[str] = []
    different: Dict[str, Dict[str, Any]] = {}
    long_only: Dict[str, Any] = {}
    walk_only: Dict[str, Any] = {}

    walk_keys = set(WALKAWAY_OPERATOR_OVERRIDES)
    long_keys = set(LONG_BUILD_OPERATOR_OVERRIDES)

    for key in sorted(walk_keys & long_keys):
        w = WALKAWAY_OPERATOR_OVERRIDES[key]
        lb = LONG_BUILD_OPERATOR_OVERRIDES[key]
        if w == lb:
            shared.append(key)
        else:
            different[key] = {"walkaway": w, "long_build": lb}

    for key in sorted(long_keys - walk_keys):
        long_only[key] = LONG_BUILD_OPERATOR_OVERRIDES[key]

    for key in sorted(walk_keys - long_keys):
        walk_only[key] = WALKAWAY_OPERATOR_OVERRIDES[key]

    agent_diff: Dict[str, Dict[str, Any]] = {}
    for key in sorted(set(WALKAWAY_AGENT_PATCH) | set(LONG_BUILD_AGENT_PATCH)):
        w = WALKAWAY_AGENT_PATCH.get(key)
        lb = LONG_BUILD_AGENT_PATCH.get(key)
        if w != lb:
            agent_diff[key] = {"walkaway": w, "long_build": lb}

    return {
        "shared_operator_keys": shared,
        "different_operator_keys": different,
        "long_build_only_operator_keys": long_only,
        "walkaway_only_operator_keys": walk_only,
        "agent_patch_diff": agent_diff,
        "summary": (
            f"{len(shared)} operator keys identical; "
            f"{len(different)} differ; "
            f"{len(long_only)} long-build-only (brackets/harvest/regime/target)."
        ),
    }


def apply_long_build_preset(
    *,
    patch_overrides,
    merge_agent_patch,
    base_config,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    merged, errors = patch_overrides(LONG_BUILD_OPERATOR_OVERRIDES, base=base_config)
    agent_merged, agent_errors = merge_agent_patch(LONG_BUILD_AGENT_PATCH)
    all_errors = list(errors) + list(agent_errors)
    return merged, agent_merged, all_errors
