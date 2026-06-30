"""Operator runtime — config overrides and pending command queue (file-backed)."""

from __future__ import annotations

import json
import logging
from dataclasses import fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from alpha.hud.operator_phase import (
    DEFAULT_OPERATOR_PHASE,
    OPERATOR_PHASE_KEY,
    normalize_operator_phase,
    phase_snapshot_fields,
)
from alpha.hud.operator_market_regime import (
    DEFAULT_MARKET_REGIME,
    OPERATOR_MARKET_REGIME_KEY,
    market_regime_snapshot_fields,
    normalize_market_regime,
)
from config.settings import BotConfig, patch_config_file
from alpha.precision import MAX_ALPHA_RLUSD_PRICE_DECIMALS, MIN_ALPHA_RLUSD_PRICE_DECIMALS

logger = logging.getLogger(__name__)

_DEFAULT_OVERRIDES = Path("logs/alpha_overrides.json")
_DEFAULT_COMMANDS = Path("logs/alpha_commands.json")

# Virtual TA keys (mapped into alpha_technical_analysis nested config).
_TA_VIRTUAL_KEYS = frozenset(
    {
        "alpha_ta_enabled",
        "alpha_ta_min_buy_score",
        "alpha_ta_min_sell_score",
        "alpha_ta_rsi_enabled",
        "alpha_ta_stoch_enabled",
        "alpha_ta_bollinger_enabled",
        "alpha_ta_engulfing_enabled",
        "alpha_ta_candle_interval_seconds",
    }
)

# SKYNET-only virtual key (persisted in overrides, not BotConfig).
_VIRTUAL_SKYNET_KEYS = frozenset({OPERATOR_PHASE_KEY, OPERATOR_MARKET_REGIME_KEY})

# Keys the HUD may override at runtime (Aggressive Bag Growth — TA-Driven).
OPERATOR_TUNABLE_KEYS: Tuple[str, ...] = (
    OPERATOR_PHASE_KEY,
    OPERATOR_MARKET_REGIME_KEY,
    "dry_run",
    "trading_enabled",
    "inventory_target_xrp_ratio",
    "alpha_risk_per_trade_pct",
    "alpha_min_edge_threshold_pct",
    "alpha_buy_limit_offset_pct",
    "alpha_sell_limit_offset_pct",
    "alpha_weakness_deviation",
    "alpha_bull_run_max_deviation",
    "alpha_accumulation_max_deviation",
    "alpha_strength_deviation",
    "alpha_max_pending_buys",
    "alpha_max_pending_sells",
    "alpha_stale_pending_buy_enabled",
    "alpha_stale_pending_buy_max_drift_pct",
    "alpha_stale_pending_buy_max_age_seconds",
    "alpha_deferred_sl_enabled",
    "alpha_deferred_sl_arm_buffer_pct",
    "alpha_cycle_interval_seconds",
    "alpha_rlusd_price_decimals",
    "alpha_ta_weight",
    "alpha_ta_enabled",
    "alpha_ta_min_buy_score",
    "alpha_ta_min_sell_score",
    "alpha_ta_rsi_enabled",
    "alpha_ta_stoch_enabled",
    "alpha_ta_bollinger_enabled",
    "alpha_ta_engulfing_enabled",
    "alpha_ta_candle_interval_seconds",
    "alpha_reentry_enabled",
    "alpha_reentry_tp_dip_pct",
    "alpha_reentry_tp_cooldown_cycles",
    "alpha_reentry_tp_cooldown_minutes",
    "alpha_reentry_tp_min_ta_score",
    "alpha_reentry_sl_stabilization_pct",
    "alpha_reentry_sl_cooldown_cycles",
    "alpha_reentry_sl_cooldown_minutes",
    "alpha_reentry_sl_min_ta_score",
    "alpha_reentry_scratch_sl_max_loss_pct",
    "alpha_reentry_scratch_sl_cooldown_cycles",
    "alpha_reentry_sl_cluster_window_seconds",
    "alpha_reentry_recovery_enabled",
    "alpha_reentry_recovery_release_pct",
    "alpha_reentry_recovery_min_cycles",
    "alpha_reentry_post_clear_buy_spacing_cycles",
    "alpha_breakout_pct",
    "alpha_structure_lookback",
    "bracket_trailing_enabled",
    "trailing_step_pct",
    "initial_stop_loss_pct",
    "take_profit_pct",
    "take_profit_rr",
)

OPERATOR_SLIDER_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "inventory_target_xrp_ratio": {"min": 0.01, "max": 0.99, "step": 0.01},
    "alpha_risk_per_trade_pct": {"min": 0.1, "max": 5.0, "step": 0.1},
    "alpha_min_edge_threshold_pct": {"min": 0.0, "max": 1.0, "step": 0.01},
    "alpha_buy_limit_offset_pct": {"min": 0.05, "max": 1.0, "step": 0.01},
    "alpha_sell_limit_offset_pct": {"min": 0.05, "max": 1.0, "step": 0.01},
    "alpha_weakness_deviation": {"min": 0.005, "max": 0.15, "step": 0.005},
    "alpha_bull_run_max_deviation": {"min": 0.01, "max": 0.15, "step": 0.005},
    "alpha_accumulation_max_deviation": {"min": 0.01, "max": 0.15, "step": 0.005},
    "alpha_strength_deviation": {"min": 0.01, "max": 0.25, "step": 0.01},
    "alpha_max_pending_buys": {"min": 1, "max": 5, "step": 1},
    "alpha_max_pending_sells": {"min": 1, "max": 5, "step": 1},
    "alpha_stale_pending_buy_max_drift_pct": {"min": 0.05, "max": 5.0, "step": 0.05},
    "alpha_stale_pending_buy_max_age_seconds": {"min": 0, "max": 86400, "step": 60},
    "alpha_deferred_sl_arm_buffer_pct": {"min": 0.0, "max": 2.0, "step": 0.05},
    "alpha_cycle_interval_seconds": {"min": 5, "max": 60, "step": 1},
    "alpha_rlusd_price_decimals": {"min": 0, "max": 6, "step": 1},
    "alpha_ta_weight": {"min": 0.0, "max": 1.0, "step": 0.05},
    "alpha_ta_min_buy_score": {"min": 0.0, "max": 10.0, "step": 0.1},
    "alpha_ta_min_sell_score": {"min": 0.0, "max": 10.0, "step": 0.1},
    "alpha_ta_candle_interval_seconds": {"min": 300, "max": 9000, "step": 300},
    "alpha_reentry_tp_dip_pct": {"min": 0.01, "max": 2.0, "step": 0.01},
    "alpha_reentry_tp_cooldown_cycles": {"min": 0, "max": 50, "step": 1},
    "alpha_reentry_tp_cooldown_minutes": {"min": 0.0, "max": 240.0, "step": 1.0},
    "alpha_reentry_tp_min_ta_score": {"min": 0.0, "max": 10.0, "step": 0.1},
    "alpha_reentry_sl_stabilization_pct": {"min": 0.01, "max": 2.0, "step": 0.01},
    "alpha_reentry_sl_cooldown_cycles": {"min": 0, "max": 100, "step": 1},
    "alpha_reentry_sl_cooldown_minutes": {"min": 0.0, "max": 480.0, "step": 1.0},
    "alpha_reentry_sl_min_ta_score": {"min": 0.0, "max": 10.0, "step": 0.1},
    "alpha_reentry_scratch_sl_max_loss_pct": {"min": 0.0, "max": 1.0, "step": 0.01},
    "alpha_reentry_scratch_sl_cooldown_cycles": {"min": 0, "max": 50, "step": 1},
    "alpha_reentry_sl_cluster_window_seconds": {"min": 0, "max": 7200, "step": 60},
    "alpha_reentry_recovery_release_pct": {"min": 0.0, "max": 1.0, "step": 0.01},
    "alpha_reentry_recovery_min_cycles": {"min": 0, "max": 20, "step": 1},
    "alpha_reentry_post_clear_buy_spacing_cycles": {"min": 0, "max": 30, "step": 1},
    "alpha_breakout_pct": {"min": 0.005, "max": 0.10, "step": 0.005},
    "alpha_structure_lookback": {"min": 3, "max": 100, "step": 1},
    "trailing_step_pct": {"min": 0.5, "max": 5.0, "step": 0.1},
    "initial_stop_loss_pct": {"min": 0.005, "max": 0.10, "step": 0.001},
    "take_profit_pct": {"min": 0.01, "max": 0.20, "step": 0.01},
    "take_profit_rr": {"min": 0.5, "max": 5.0, "step": 0.1},
}


def _apply_ta_virtual_overrides(config: BotConfig, overrides: Dict[str, Any]) -> BotConfig:
    """Merge HUD TA virtual keys into nested alpha_technical_analysis."""
    ta = config.alpha_technical_analysis
    if "alpha_ta_enabled" in overrides:
        ta = replace(ta, enabled=bool(overrides["alpha_ta_enabled"]))
    if "alpha_ta_min_buy_score" in overrides:
        ta = replace(ta, min_buy_score=float(overrides["alpha_ta_min_buy_score"]))
    if "alpha_ta_min_sell_score" in overrides:
        ta = replace(ta, min_sell_score=float(overrides["alpha_ta_min_sell_score"]))
    if "alpha_ta_rsi_enabled" in overrides:
        ta = replace(ta, rsi=replace(ta.rsi, enabled=bool(overrides["alpha_ta_rsi_enabled"])))
    if "alpha_ta_stoch_enabled" in overrides:
        ta = replace(ta, stochastic=replace(ta.stochastic, enabled=bool(overrides["alpha_ta_stoch_enabled"])))
    if "alpha_ta_bollinger_enabled" in overrides:
        ta = replace(ta, bollinger=replace(ta.bollinger, enabled=bool(overrides["alpha_ta_bollinger_enabled"])))
    if "alpha_ta_engulfing_enabled" in overrides:
        ta = replace(ta, engulfing=replace(ta.engulfing, enabled=bool(overrides["alpha_ta_engulfing_enabled"])))
    if "alpha_ta_candle_interval_seconds" in overrides:
        ta = replace(ta, candle_interval_seconds=int(overrides["alpha_ta_candle_interval_seconds"]))
    return replace(config, alpha_technical_analysis=ta)


def apply_overrides(config: BotConfig, overrides: Optional[Dict[str, Any]] = None) -> BotConfig:
    """Return effective config with runtime overrides merged (does not mutate input)."""
    if not overrides:
        return config
    merged = dict(overrides)
    if "alpha_reentry_tp_min_cycles" in merged and "alpha_reentry_tp_cooldown_cycles" not in merged:
        merged["alpha_reentry_tp_cooldown_cycles"] = merged.pop("alpha_reentry_tp_min_cycles")
    if "alpha_reentry_sl_min_cycles" in merged and "alpha_reentry_sl_cooldown_cycles" not in merged:
        merged["alpha_reentry_sl_cooldown_cycles"] = merged.pop("alpha_reentry_sl_min_cycles")
    overrides = merged
    allowed = {f.name for f in fields(BotConfig)}
    kwargs: Dict[str, Any] = {}
    for key, value in overrides.items():
        if key in _TA_VIRTUAL_KEYS or key in _VIRTUAL_SKYNET_KEYS:
            continue
        if key in allowed:
            kwargs[key] = value
    result = replace(config, **kwargs) if kwargs else config
    if overrides.keys() & _TA_VIRTUAL_KEYS:
        result = _apply_ta_virtual_overrides(result, overrides)
    return result


def effective_config_snapshot(
    config: BotConfig,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Safe tunable snapshot for HUD display (no secrets)."""
    ta = config.alpha_technical_analysis
    snap: Dict[str, Any] = {}
    for key in OPERATOR_TUNABLE_KEYS:
        if key == OPERATOR_PHASE_KEY or key == OPERATOR_MARKET_REGIME_KEY:
            continue
        if key == "alpha_ta_enabled":
            snap[key] = ta.enabled
        elif key == "alpha_ta_min_buy_score":
            snap[key] = ta.min_buy_score
        elif key == "alpha_ta_min_sell_score":
            snap[key] = ta.min_sell_score
        elif key == "alpha_ta_rsi_enabled":
            snap[key] = ta.rsi.enabled
        elif key == "alpha_ta_stoch_enabled":
            snap[key] = ta.stochastic.enabled
        elif key == "alpha_ta_bollinger_enabled":
            snap[key] = ta.bollinger.enabled
        elif key == "alpha_ta_engulfing_enabled":
            snap[key] = ta.engulfing.enabled
        elif key == "alpha_ta_candle_interval_seconds":
            from alpha.decision.ta_config import effective_ta_candle_interval_seconds

            snap[key] = effective_ta_candle_interval_seconds(
                ta,
                cycle_seconds=config.alpha_cycle_interval_seconds,
                sample_interval_seconds=config.alpha_price_sample_interval_seconds,
            )
        else:
            snap[key] = getattr(config, key)
    snap["inventory_target_xrp_pct"] = round(config.inventory_target_xrp_ratio * 100.0, 1)
    snap.update(phase_snapshot_fields(overrides))
    snap.update(market_regime_snapshot_fields(overrides))
    return snap


def validate_override_updates(
    updates: Dict[str, Any],
    *,
    base: Optional[BotConfig] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Validate override patch; return (sanitized_updates, errors)."""
    errors: List[str] = []
    sanitized: Dict[str, Any] = {}
    allowed = set(OPERATOR_TUNABLE_KEYS)

    for key, raw in updates.items():
        if key not in allowed:
            errors.append(f"unknown override key: {key}")
            continue
        try:
            sanitized[key] = _coerce_override(key, raw)
        except (TypeError, ValueError) as exc:
            errors.append(f"{key}: {exc}")

    if errors:
        return {}, errors

    trial = apply_overrides(base or BotConfig(), sanitized)
    errors.extend(_validate_merged_config(trial, sanitized.keys()))
    if OPERATOR_PHASE_KEY in sanitized and sanitized[OPERATOR_PHASE_KEY] not in (
        "trust",
        "scale",
        "aggressive",
    ):
        errors.append(f"{OPERATOR_PHASE_KEY} must be trust, scale, or aggressive")
    if OPERATOR_MARKET_REGIME_KEY in sanitized and sanitized[OPERATOR_MARKET_REGIME_KEY] not in (
        "bull",
        "neutral",
        "bear",
    ):
        errors.append(f"{OPERATOR_MARKET_REGIME_KEY} must be bull, neutral, or bear")
    if errors:
        return {}, errors
    return sanitized, []


def _coerce_override(key: str, value: Any) -> Any:
    _BOOL_KEYS = {
        "dry_run",
        "trading_enabled",
        "bracket_trailing_enabled",
        "alpha_ta_enabled",
        "alpha_ta_rsi_enabled",
        "alpha_ta_stoch_enabled",
        "alpha_ta_bollinger_enabled",
        "alpha_ta_engulfing_enabled",
        "alpha_reentry_enabled",
        "alpha_stale_pending_buy_enabled",
        "alpha_deferred_sl_enabled",
    }
    if key in _BOOL_KEYS:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)
    _INT_KEYS = {
        "alpha_max_pending_buys",
        "alpha_max_pending_sells",
        "alpha_structure_lookback",
        "alpha_cycle_interval_seconds",
        "alpha_reentry_tp_cooldown_cycles",
        "alpha_reentry_sl_cooldown_cycles",
        "alpha_rlusd_price_decimals",
        "alpha_ta_candle_interval_seconds",
    }
    if key in _INT_KEYS:
        if key == "alpha_ta_candle_interval_seconds":
            sec = max(300, min(9000, int(value)))
            return int(round(sec / 300) * 300)
        return int(value)
    if key == OPERATOR_PHASE_KEY:
        phase = str(value).strip().lower()
        aliases = {"patient": "trust", "prove": "trust", "soak": "trust", "balanced": "scale", "growth": "aggressive", "eager": "aggressive"}
        phase = aliases.get(phase, phase)
        if phase not in ("trust", "scale", "aggressive"):
            raise ValueError("must be trust, scale, or aggressive")
        return phase
    if key == OPERATOR_MARKET_REGIME_KEY:
        regime = normalize_market_regime(value)
        if regime not in ("bull", "neutral", "bear"):
            raise ValueError("must be bull, neutral, or bear")
        return regime
    return float(value)


def _validate_merged_config(config: BotConfig, changed_keys: Any) -> List[str]:
    errors: List[str] = []
    keys = set(changed_keys)

    if "inventory_target_xrp_ratio" in keys:
        if config.inventory_target_xrp_ratio <= 0 or config.inventory_target_xrp_ratio >= 1:
            errors.append("inventory_target_xrp_ratio must be between 0 and 1 (exclusive)")

    if "alpha_ta_weight" in keys:
        if config.alpha_ta_weight < 0 or config.alpha_ta_weight > 1:
            errors.append("alpha_ta_weight must be between 0 and 1")

    if "alpha_risk_per_trade_pct" in keys:
        if config.alpha_risk_per_trade_pct <= 0 or config.alpha_risk_per_trade_pct > 100:
            errors.append("alpha_risk_per_trade_pct must be between 0 and 100 (exclusive of 0)")

    if "alpha_min_edge_threshold_pct" in keys and config.alpha_min_edge_threshold_pct < 0:
        errors.append("alpha_min_edge_threshold_pct must be non-negative")

    if "alpha_buy_limit_offset_pct" in keys and config.alpha_buy_limit_offset_pct <= 0:
        errors.append("alpha_buy_limit_offset_pct must be positive")

    if "alpha_sell_limit_offset_pct" in keys and config.alpha_sell_limit_offset_pct <= 0:
        errors.append("alpha_sell_limit_offset_pct must be positive")

    if "alpha_max_pending_buys" in keys and config.alpha_max_pending_buys < 1:
        errors.append("alpha_max_pending_buys must be at least 1")

    if "alpha_max_pending_sells" in keys and config.alpha_max_pending_sells < 1:
        errors.append("alpha_max_pending_sells must be at least 1")

    if "alpha_stale_pending_buy_max_drift_pct" in keys and config.alpha_stale_pending_buy_max_drift_pct <= 0:
        errors.append("alpha_stale_pending_buy_max_drift_pct must be positive")

    if (
        "alpha_stale_pending_buy_max_age_seconds" in keys
        and config.alpha_stale_pending_buy_max_age_seconds < 0
    ):
        errors.append("alpha_stale_pending_buy_max_age_seconds must be non-negative")

    if "alpha_deferred_sl_arm_buffer_pct" in keys and config.alpha_deferred_sl_arm_buffer_pct < 0:
        errors.append("alpha_deferred_sl_arm_buffer_pct must be non-negative")

    if "alpha_cycle_interval_seconds" in keys:
        if config.alpha_cycle_interval_seconds < 5 or config.alpha_cycle_interval_seconds > 60:
            errors.append("alpha_cycle_interval_seconds must be between 5 and 60")

    if "alpha_rlusd_price_decimals" in keys:
        dec = config.alpha_rlusd_price_decimals
        if dec < MIN_ALPHA_RLUSD_PRICE_DECIMALS or dec > MAX_ALPHA_RLUSD_PRICE_DECIMALS:
            errors.append("alpha_rlusd_price_decimals must be between 0 and 6")

    if "alpha_ta_candle_interval_seconds" in keys:
        from alpha.decision.ta_config import (
            TA_CANDLE_INTERVAL_MAX_SECONDS,
            TA_CANDLE_INTERVAL_MIN_SECONDS,
            effective_ta_candle_interval_seconds,
        )

        sec = effective_ta_candle_interval_seconds(
            config.alpha_technical_analysis,
            cycle_seconds=config.alpha_cycle_interval_seconds,
            sample_interval_seconds=config.alpha_price_sample_interval_seconds,
        )
        if sec < TA_CANDLE_INTERVAL_MIN_SECONDS or sec > TA_CANDLE_INTERVAL_MAX_SECONDS:
            errors.append(
                f"alpha_ta_candle_interval_seconds must be between "
                f"{TA_CANDLE_INTERVAL_MIN_SECONDS} and {TA_CANDLE_INTERVAL_MAX_SECONDS} (5m–2.5h)"
            )

    if "alpha_reentry_tp_cooldown_cycles" in keys and config.alpha_reentry_tp_cooldown_cycles < 0:
        errors.append("alpha_reentry_tp_cooldown_cycles must be non-negative")

    if "alpha_reentry_sl_cooldown_cycles" in keys and config.alpha_reentry_sl_cooldown_cycles < 0:
        errors.append("alpha_reentry_sl_cooldown_cycles must be non-negative")

    if keys & {"alpha_reentry_tp_cooldown_minutes", "alpha_reentry_sl_cooldown_minutes"}:
        if config.alpha_reentry_tp_cooldown_minutes < 0 or config.alpha_reentry_sl_cooldown_minutes < 0:
            errors.append("re-entry cooldown minutes must be non-negative")

    if "alpha_breakout_pct" in keys and config.alpha_breakout_pct <= 0:
        errors.append("alpha_breakout_pct must be positive")

    if "alpha_structure_lookback" in keys and config.alpha_structure_lookback < 3:
        errors.append("alpha_structure_lookback must be at least 3")

    if keys & {"alpha_weakness_deviation", "alpha_strength_deviation"}:
        if config.alpha_weakness_deviation <= 0 or config.alpha_strength_deviation <= 0:
            errors.append("alpha_weakness_deviation and alpha_strength_deviation must be positive")

    if "initial_stop_loss_pct" in keys:
        if config.initial_stop_loss_pct <= 0 or config.initial_stop_loss_pct >= 1.0:
            errors.append("initial_stop_loss_pct must be between 0 and 1 (exclusive)")

    if keys & {"take_profit_rr", "take_profit_pct"}:
        if config.take_profit_rr <= 0 and config.take_profit_pct <= 0:
            errors.append("set take_profit_rr > 0 or take_profit_pct > 0")

    if "trailing_step_pct" in keys and config.trailing_step_pct <= 0:
        errors.append("trailing_step_pct must be positive")

    return errors


class OperatorRuntimeStore:
    """File-backed overrides and command queue for the Alpha engine."""

    def __init__(
        self,
        *,
        overrides_path: Path = _DEFAULT_OVERRIDES,
        commands_path: Path = _DEFAULT_COMMANDS,
    ) -> None:
        self.overrides_path = overrides_path
        self.commands_path = commands_path
        self.overrides_path.parent.mkdir(parents=True, exist_ok=True)
        self.commands_path.parent.mkdir(parents=True, exist_ok=True)

    def load_overrides(self) -> Dict[str, Any]:
        if not self.overrides_path.exists():
            return {}
        try:
            data = json.loads(self.overrides_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            return {k: data[k] for k in OPERATOR_TUNABLE_KEYS if k in data}
        except (json.JSONDecodeError, OSError):
            return {}

    def save_overrides(self, overrides: Dict[str, Any]) -> Dict[str, Any]:
        merged = self.load_overrides()
        merged.update(overrides)
        payload = {
            **merged,
            "updated_utc": datetime.now(tz=timezone.utc).isoformat(),
        }
        self.overrides_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("alpha_overrides_saved | keys=%s", sorted(overrides.keys()))
        return merged

    def patch_overrides(self, updates: Dict[str, Any], *, base: Optional[BotConfig] = None) -> Tuple[Dict[str, Any], List[str]]:
        sanitized, errors = validate_override_updates(updates, base=base)
        if errors:
            return self.load_overrides(), errors
        return self.save_overrides(sanitized), []

    def clear_overrides(self) -> None:
        if self.overrides_path.exists():
            self.overrides_path.unlink(missing_ok=True)

    def queue_command(self, command: Dict[str, Any]) -> None:
        pending = self._load_commands()
        pending.append(
            {
                **command,
                "queued_utc": datetime.now(tz=timezone.utc).isoformat(),
            }
        )
        self._write_commands(pending)
        logger.info("alpha_command_queued | type=%s", command.get("type"))

    def drain_commands(self) -> List[Dict[str, Any]]:
        pending = self._load_commands()
        if pending:
            self._write_commands([])
        return pending

    def set_dry_run(
        self,
        dry_run: bool,
        *,
        persist_yaml: bool = False,
        base: Optional[BotConfig] = None,
    ) -> Dict[str, Any]:
        overrides, errors = self.patch_overrides({"dry_run": dry_run}, base=base)
        if errors:
            raise ValueError("; ".join(errors))
        if persist_yaml:
            patch_config_file({"dry_run": dry_run})
            logger.info("alpha_dry_run_persisted | dry_run=%s", dry_run)
        return overrides

    def _load_commands(self) -> List[Dict[str, Any]]:
        if not self.commands_path.exists():
            return []
        try:
            data = json.loads(self.commands_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [c for c in data if isinstance(c, dict)]
            if isinstance(data, dict) and isinstance(data.get("commands"), list):
                return [c for c in data["commands"] if isinstance(c, dict)]
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def _write_commands(self, commands: List[Dict[str, Any]]) -> None:
        self.commands_path.parent.mkdir(parents=True, exist_ok=True)
        self.commands_path.write_text(json.dumps(commands, indent=2), encoding="utf-8")

    def has_pending_commands(self) -> bool:
        return bool(self._load_commands())


def derive_posture(
    *,
    decision_action: str,
    pending_buys: int,
    active_brackets: int,
) -> str:
    """HUD posture label: patient | buying | in_position."""
    if active_brackets > 0:
        return "in_position"
    if pending_buys > 0 or decision_action == "place_bid":
        return "buying"
    return "patient"
