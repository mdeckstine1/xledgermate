"""Unassed preset — unbrick stranded bag-growth (powder + dead zone + SL factory)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from alpha.hud.operator_market_regime import OPERATOR_MARKET_REGIME_KEY
from alpha.hud.operator_phase import OPERATOR_PHASE_KEY

# Emergency recovery knobs for "99% XRP / no RLUSD / hold forever / SL factory".
# Does not rewrite decision priority in code — only operator-tunable policy numbers.
UNASSED_OPERATOR_OVERRIDES: Dict[str, Any] = {
    OPERATOR_PHASE_KEY: "scale",
    OPERATOR_MARKET_REGIME_KEY: "bull",
    "trading_enabled": True,
    # Still bag-biased, but 99% XRP must read as clearly heavy for funding trims.
    "inventory_target_xrp_ratio": 0.88,
    "alpha_risk_capital_sync_portfolio": True,
    "alpha_risk_per_trade_pct": 3.0,
    "alpha_min_edge_threshold_pct": 0.06,
    "alpha_buy_limit_offset_pct": 0.15,
    # Tighter asks so funding / strength sells actually fill.
    "alpha_sell_limit_offset_pct": 0.08,
    "alpha_weakness_deviation": 0.03,
    # Collapse dead zone: sell when overweight, allow momentum while heavy.
    "alpha_strength_deviation": 0.06,
    "alpha_bull_run_max_deviation": 0.15,
    "alpha_accumulation_max_deviation": 0.15,
    "alpha_max_pending_buys": 3,
    "alpha_max_pending_sells": 2,
    "alpha_stale_pending_buy_enabled": True,
    "alpha_stale_pending_buy_max_drift_pct": 0.38,
    "alpha_stale_pending_buy_max_age_seconds": 0,
    # Soften sell TA so funding trims are not blocked forever.
    "alpha_ta_weight": 0.65,
    "alpha_ta_min_buy_score": 2.0,
    "alpha_ta_min_sell_score": 2.0,
    # Stop the SL factory — wide stop, no trail, fixed modest TP (not RR chase).
    "bracket_trailing_enabled": False,
    "trailing_step_pct": 2.5,
    "initial_stop_loss_pct": 0.09,
    "take_profit_pct": 0.025,
    "take_profit_rr": 0.0,
    "alpha_deferred_sl_enabled": False,
    "alpha_deferred_sl_arm_buffer_pct": 0.20,
    # Unlock accumulation with partial powder + allow residual bids.
    "alpha_reload_min_rlusd_deploy_xrp_equiv": 18.0,
    "alpha_reload_sell_offset_pct": 0.04,
    "alpha_reload_block_accumulation_until_funded": False,
    # Keep harvest/dip sane (not the brick path).
    "alpha_accumulation_harvest_move_24h_watch_pct": 5.0,
    "alpha_accumulation_harvest_pullback_arm_pct": 1.25,
    "alpha_accumulation_harvest_trim_risk_pct": 1.5,
    "alpha_accumulation_dip_move_24h_arm_pct": 5.0,
    "alpha_accumulation_dip_bounce_arm_pct": 0.30,
    "alpha_accumulation_dip_buy_offset_pct": 0.15,
    # Longer chill after stops so we do not re-arm the factory immediately.
    "alpha_reentry_sl_cooldown_cycles": 45,
    "alpha_reentry_sl_cooldown_minutes": 90.0,
    "alpha_reentry_scratch_sl_cooldown_cycles": 15,
}

UNASSED_AGENT_PATCH: Dict[str, Any] = {
    "agent_enabled": True,
    "full_mode_enabled": False,
    "interval_cycles_min": 8,
    "interval_cycles_max": 12,
}

UNASSED_DESCRIPTION = (
    "Unassed: unbrick stranded bag-growth — lower strength gate (dev≥0.06), "
    "bull/accum max dev 0.15, softer sell TA (2.0), reload floor 18 XRP-eq + "
    "accumulation not hard-blocked, tighter funding asks (0.04/0.08), "
    "wide SL 9% / no trail / fixed TP 2.5% (kill SL factory). "
    "Still scale+bull bag bias (target 88%). Knobs only — not full code rewrite. "
    "Recovery only — switch back to Maximize once powder + trims are healthy."
)


def unassed_preset_payload() -> Dict[str, Any]:
    return {
        "label": "Unassed (unbrick bag-growth)",
        "description": UNASSED_DESCRIPTION,
        "operator_overrides": dict(UNASSED_OPERATOR_OVERRIDES),
        "agent_patch": dict(UNASSED_AGENT_PATCH),
        "maximize_comparison": compare_unassed_to_maximize(),
    }


def compare_unassed_to_maximize() -> Dict[str, Any]:
    """Highlight deltas vs Maximize (default harvest-loop posture). Lazy import avoids cycle."""
    from alpha.hud.maximize_preset import MAXIMIZE_OPERATOR_OVERRIDES

    different: Dict[str, Dict[str, Any]] = {}
    for key in sorted(set(MAXIMIZE_OPERATOR_OVERRIDES) | set(UNASSED_OPERATOR_OVERRIDES)):
        mx = MAXIMIZE_OPERATOR_OVERRIDES.get(key)
        ua = UNASSED_OPERATOR_OVERRIDES.get(key)
        if mx != ua:
            different[key] = {"maximize": mx, "unassed": ua}
    return {
        "different_operator_keys": different,
        "summary": (
            f"{len(different)} knob(s) differ from Maximize — mainly lower powder floor, "
            "slightly higher strength gate, wider/softer recovery SL path."
        ),
    }


def apply_unassed_preset(
    *,
    patch_overrides,
    merge_agent_patch,
    base_config,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    merged, errors = patch_overrides(UNASSED_OPERATOR_OVERRIDES, base=base_config)
    agent_merged, agent_errors = merge_agent_patch(UNASSED_AGENT_PATCH)
    all_errors = list(errors) + list(agent_errors)
    return merged, agent_merged, all_errors
