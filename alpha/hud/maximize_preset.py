"""Maximize preset — harvest loop: powder floor, core bag, redeploy dips, grow XRP stack."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from alpha.hud.operator_market_regime import OPERATOR_MARKET_REGIME_KEY
from alpha.hud.operator_phase import OPERATOR_PHASE_KEY
from alpha.hud.unassed_preset import UNASSED_OPERATOR_OVERRIDES

# Doctrine:
#   hold core XRP → harvest/strength rips into RLUSD → keep powder floor →
#   redeploy on dips/breakouts → clip size scales with portfolio → XRP count ↑
MAXIMIZE_OPERATOR_OVERRIDES: Dict[str, Any] = {
    OPERATOR_PHASE_KEY: "scale",
    OPERATOR_MARKET_REGIME_KEY: "bull",
    "trading_enabled": True,
    # Bag bias with room to harvest (not 99% permanent long).
    "inventory_target_xrp_ratio": 0.85,
    "alpha_risk_capital_sync_portfolio": True,
    "alpha_risk_per_trade_pct": 3.5,  # clips scale with bag
    "alpha_min_edge_threshold_pct": 0.06,
    "alpha_buy_limit_offset_pct": 0.14,
    "alpha_sell_limit_offset_pct": 0.08,
    "alpha_weakness_deviation": 0.03,
    # Sell into strength early enough to fund + harvest; allow momentum while heavy.
    "alpha_strength_deviation": 0.05,
    "alpha_bull_run_max_deviation": 0.15,
    "alpha_accumulation_max_deviation": 0.15,
    "alpha_max_pending_buys": 3,
    "alpha_max_pending_sells": 2,
    "alpha_stale_pending_buy_enabled": True,
    "alpha_stale_pending_buy_max_drift_pct": 0.35,
    "alpha_stale_pending_buy_max_age_seconds": 0,
    "alpha_ta_weight": 0.65,
    "alpha_ta_min_buy_score": 1.8,
    "alpha_ta_min_sell_score": 1.8,
    # Core bag: no TP/SL factory — harvest/strength sells manage inventory.
    "alpha_brackets_enabled": False,
    "bracket_trailing_enabled": False,
    "trailing_step_pct": 2.5,
    "initial_stop_loss_pct": 0.09,
    "take_profit_pct": 0.025,
    "take_profit_rr": 0.0,
    "alpha_deferred_sl_enabled": False,
    "alpha_deferred_sl_arm_buffer_pct": 0.20,
    # Healthy powder reserve so dips can be bought (XRP-eq).
    "alpha_reload_min_rlusd_deploy_xrp_equiv": 40.0,
    "alpha_reload_sell_offset_pct": 0.05,
    "alpha_reload_block_accumulation_until_funded": False,
    # Harvest more often on real legs (not only monster 5% days).
    "alpha_accumulation_harvest_move_24h_watch_pct": 3.5,
    "alpha_accumulation_harvest_pullback_arm_pct": 0.9,
    "alpha_accumulation_harvest_trim_risk_pct": 2.0,
    # Dip redeploy — arm earlier so reverse after sell-off is bought.
    "alpha_accumulation_dip_move_24h_arm_pct": 3.5,
    "alpha_accumulation_dip_bounce_arm_pct": 0.25,
    "alpha_accumulation_dip_buy_offset_pct": 0.14,
    # Drawdown funding still available as backup powder path.
    "alpha_drawdown_reload_stage1_arm_pct": 2.5,
    "alpha_drawdown_reload_stage2_arm_pct": 4.0,
    "alpha_drawdown_reload_total_bag_pct": 5.0,
    "alpha_drawdown_reload_stage1_bag_pct": 2.5,
    "alpha_drawdown_reload_stage2_bag_pct": 2.5,
    "alpha_reentry_sl_cooldown_cycles": 30,
    "alpha_reentry_sl_cooldown_minutes": 60.0,
    "alpha_reentry_scratch_sl_cooldown_cycles": 12,
}

MAXIMIZE_AGENT_PATCH: Dict[str, Any] = {
    "agent_enabled": True,
    "full_mode_enabled": False,
    "interval_cycles_min": 10,
    "interval_cycles_max": 15,
    "guardrails": {
        "alpha_risk_per_trade_pct": {"min": 2.0, "max": 4.0},
        "inventory_target_xrp_pct": {"min": 75.0, "max": 90.0},
        "alpha_ta_weight": {"min": 0.4, "max": 0.85},
        "alpha_strength_deviation": {"min": 0.03, "max": 0.10},
        "alpha_weakness_deviation": {"min": 0.02, "max": 0.08},
        "alpha_buy_limit_offset_pct": {"min": 0.08, "max": 0.25},
        "alpha_sell_limit_offset_pct": {"min": 0.05, "max": 0.18},
        "alpha_max_pending_buys": {"min": 1, "max": 4},
        "alpha_max_pending_sells": {"min": 1, "max": 3},
        "alpha_accumulation_max_deviation": {"min": 0.08, "max": 0.15},
        "alpha_bull_run_max_deviation": {"min": 0.08, "max": 0.15},
        "alpha_reload_min_rlusd_deploy_xrp_equiv": {"min": 25.0, "max": 80.0},
        "alpha_ta_min_buy_score": {"min": 1.0, "max": 3.5},
        "alpha_ta_min_sell_score": {"min": 1.0, "max": 3.5},
        "initial_stop_loss_pct": {"min": 0.05, "max": 0.12},
        "alpha_drawdown_reload_stage1_arm_pct": {"min": 1.5, "max": 5.0},
        "alpha_drawdown_reload_stage2_arm_pct": {"min": 3.0, "max": 8.0},
        "alpha_drawdown_reload_total_bag_pct": {"min": 2.0, "max": 8.0},
        "alpha_drawdown_reload_stage1_bag_pct": {"min": 1.0, "max": 4.0},
        "alpha_drawdown_reload_stage2_bag_pct": {"min": 1.0, "max": 4.0},
        "max_changes_per_cycle": 2,
    },
    "emergency_rules": {
        "enabled": True,
        "drawdown_pause_pct": 8.0,
        "session_loss_pause_xrp": 40.0,
    },
}

MAXIMIZE_DESCRIPTION = (
    "Maximize: harvest-loop bag growth — target 85% XRP, strength trim at +5% dev, "
    "powder floor 40 XRP-eq (block-until-funded OFF), harvest arms ~3.5% legs, "
    "dip redeploy ~3.5%, 3.5% portfolio clips (scale with bag), "
    "core bag brackets OFF (no SL factory). Grow XRP count over time."
)


def maximize_preset_payload() -> Dict[str, Any]:
    return {
        "label": "Maximize (harvest stack)",
        "description": MAXIMIZE_DESCRIPTION,
        "operator_overrides": dict(MAXIMIZE_OPERATOR_OVERRIDES),
        "agent_patch": dict(MAXIMIZE_AGENT_PATCH),
        "unassed_comparison": compare_maximize_to_unassed(),
    }


def compare_maximize_to_unassed() -> Dict[str, Any]:
    different: Dict[str, Dict[str, Any]] = {}
    for key in sorted(set(UNASSED_OPERATOR_OVERRIDES) | set(MAXIMIZE_OPERATOR_OVERRIDES)):
        ua = UNASSED_OPERATOR_OVERRIDES.get(key)
        mx = MAXIMIZE_OPERATOR_OVERRIDES.get(key)
        if ua != mx:
            different[key] = {"unassed": ua, "maximize": mx}
    return {
        "different_operator_keys": different,
        "summary": (
            f"{len(different)} knob(s) vs Unassed — mainly target 85%, powder 40, "
            "brackets off, earlier harvest/dip, larger clips."
        ),
    }


def apply_maximize_preset(
    *,
    patch_overrides,
    merge_agent_patch,
    base_config,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    merged, errors = patch_overrides(MAXIMIZE_OPERATOR_OVERRIDES, base=base_config)
    agent_merged, agent_errors = merge_agent_patch(MAXIMIZE_AGENT_PATCH)
    all_errors = list(errors) + list(agent_errors)
    return merged, agent_merged, all_errors
