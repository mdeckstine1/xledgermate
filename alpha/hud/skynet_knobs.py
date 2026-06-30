"""SKYNET operator knob catalog — aliases, normalization, allowlist reference for the advisor."""

from __future__ import annotations

from typing import Any, Dict, List

from alpha.operator.runtime import OPERATOR_TUNABLE_KEYS

# Friendly / HUD short names → canonical override keys (Apply accepts either).
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
    "stale_max_age_seconds": "alpha_stale_pending_buy_max_age_seconds",
    "deferred_sl_enabled": "alpha_deferred_sl_enabled",
    "deferred_sl_arm_buffer_pct": "alpha_deferred_sl_arm_buffer_pct",
    "cycle_interval_seconds": "alpha_cycle_interval_seconds",
    "target_xrp_pct": "inventory_target_xrp_ratio",
    "inventory_target_xrp_pct": "inventory_target_xrp_ratio",
    "ta_weight": "alpha_ta_weight",
    "ta_enabled": "alpha_ta_enabled",
    "ta_min_buy_score": "alpha_ta_min_buy_score",
    "ta_min_sell_score": "alpha_ta_min_sell_score",
    "min_buy_score": "alpha_ta_min_buy_score",
    "min_sell_score": "alpha_ta_min_sell_score",
    "ta_candle_interval_seconds": "alpha_ta_candle_interval_seconds",
    "ta_candle_window": "alpha_ta_candle_interval_seconds",
    "ta_rsi_enabled": "alpha_ta_rsi_enabled",
    "ta_stoch_enabled": "alpha_ta_stoch_enabled",
    "ta_bollinger_enabled": "alpha_ta_bollinger_enabled",
    "ta_engulfing_enabled": "alpha_ta_engulfing_enabled",
    "ta_divergence_enabled": "alpha_ta_divergence_enabled",
    "reentry_enabled": "alpha_reentry_enabled",
    "tp_cooldown_cycles": "alpha_reentry_tp_cooldown_cycles",
    "tp_cooldown_minutes": "alpha_reentry_tp_cooldown_minutes",
    "tp_dip_pct": "alpha_reentry_tp_dip_pct",
    "tp_min_ta_score": "alpha_reentry_tp_min_ta_score",
    "sl_cooldown_cycles": "alpha_reentry_sl_cooldown_cycles",
    "sl_cooldown_minutes": "alpha_reentry_sl_cooldown_minutes",
    "sl_stabilization_pct": "alpha_reentry_sl_stabilization_pct",
    "sl_min_ta_score": "alpha_reentry_sl_min_ta_score",
    "scratch_sl_max_loss_pct": "alpha_reentry_scratch_sl_max_loss_pct",
    "scratch_sl_cooldown_cycles": "alpha_reentry_scratch_sl_cooldown_cycles",
    "sl_cluster_window_seconds": "alpha_reentry_sl_cluster_window_seconds",
    "recovery_enabled": "alpha_reentry_recovery_enabled",
    "recovery_release_pct": "alpha_reentry_recovery_release_pct",
    "recovery_min_cycles": "alpha_reentry_recovery_min_cycles",
    "post_clear_buy_spacing_cycles": "alpha_reentry_post_clear_buy_spacing_cycles",
    "breakout_pct": "alpha_breakout_pct",
    "structure_lookback": "alpha_structure_lookback",
    "bracket_trailing_enabled": "bracket_trailing_enabled",
    "trailing_step_pct": "trailing_step_pct",
    "initial_stop_loss_pct": "initial_stop_loss_pct",
    "take_profit_pct": "take_profit_pct",
    "take_profit_rr": "take_profit_rr",
    "operator_phase": "alpha_operator_phase",
    "market_regime": "alpha_operator_market_regime",
    "trading_enabled": "trading_enabled",
}

_KNOB_HINTS: Dict[str, str] = {
    "alpha_operator_phase": "SKYNET strategy bias: trust | scale | aggressive",
    "alpha_operator_market_regime": "SKYNET tape bias: bull | neutral | bear",
    "inventory_target_xrp_ratio": "Target XRP share of portfolio (0–1, not %)",
    "alpha_risk_per_trade_pct": "Max XRP per entry as % of portfolio",
    "alpha_weakness_deviation": "RLUSD deploy when this far below XRP target",
    "alpha_bull_run_max_deviation": "Bull-run/momentum bids allowed until this far above XRP target",
    "alpha_accumulation_max_deviation": "Accumulation regime deploy cap above XRP target (scale ~0.08)",
    "alpha_strength_deviation": "Strength sell when this far above XRP target",
    "alpha_max_pending_buys": "Max concurrent resting buy brackets",
    "alpha_stale_pending_buy_max_age_seconds": "Cancel stale bids after N seconds (0=off)",
    "alpha_reentry_scratch_sl_max_loss_pct": "Breakeven/scratch SL tier threshold %",
    "alpha_reentry_post_clear_buy_spacing_cycles": "Cycles between bids after re-entry clears",
    "dry_run": "BLOCKED from SKYNET Apply — HUD only",
}


def normalize_suggestion_key(key: str) -> str:
    """Map HUD alias or canonical key to operator override key."""
    k = (key or "").strip()
    if not k:
        return k
    if k in OPERATOR_TUNABLE_KEYS:
        return k
    return KNOB_ALIASES.get(k, k)


def build_skynet_knob_catalog() -> str:
    """Compact allowlist for SKYNET prompts (all HUD-tunable keys)."""
    lines: List[str] = [
        "=== Operator knob allowlist (suggested_changes keys — aliases OK) ===",
    ]
    for key in OPERATOR_TUNABLE_KEYS:
        if key == "dry_run":
            continue
        hint = _KNOB_HINTS.get(key, "")
        aliases = sorted(a for a, canon in KNOB_ALIASES.items() if canon == key and a != key)
        alias_note = f" aliases={','.join(aliases[:4])}" if aliases else ""
        lines.append(f"- {key}{alias_note}" + (f" — {hint}" if hint else ""))
    lines.append(
        "Virtual SKYNET keys (alpha_operator_phase, alpha_operator_market_regime) bias advice only unless operator asks to change them."
    )
    return "\n".join(lines)
