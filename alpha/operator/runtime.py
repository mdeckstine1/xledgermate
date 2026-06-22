"""Operator runtime — config overrides and pending command queue (file-backed)."""

from __future__ import annotations

import json
import logging
from dataclasses import fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config.settings import BotConfig, patch_config_file

logger = logging.getLogger(__name__)

_DEFAULT_OVERRIDES = Path("logs/alpha_overrides.json")
_DEFAULT_COMMANDS = Path("logs/alpha_commands.json")

# Keys the HUD may override at runtime (Alpha v1 tunables).
OPERATOR_TUNABLE_KEYS: Tuple[str, ...] = (
    "dry_run",
    "trading_enabled",
    "alpha_risk_per_trade_pct",
    "alpha_min_edge_threshold_pct",
    "alpha_buy_limit_offset_pct",
    "alpha_weakness_deviation",
    "alpha_strength_deviation",
    "alpha_max_pending_buys",
    "alpha_breakout_pct",
    "alpha_structure_lookback",
    "bracket_trailing_enabled",
    "alpha_ta_enabled",
    "trailing_step_pct",
    "initial_stop_loss_pct",
    "take_profit_pct",
    "take_profit_rr",
)

# Slider/toggle defaults for HUD (min, max, step) — bool/int fields omit step.
OPERATOR_SLIDER_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "alpha_risk_per_trade_pct": {"min": 0.1, "max": 5.0, "step": 0.1},
    "alpha_min_edge_threshold_pct": {"min": 0.0, "max": 1.0, "step": 0.01},
    "alpha_buy_limit_offset_pct": {"min": 0.05, "max": 1.0, "step": 0.01},
    "alpha_weakness_deviation": {"min": 0.01, "max": 0.25, "step": 0.01},
    "alpha_strength_deviation": {"min": 0.01, "max": 0.25, "step": 0.01},
    "alpha_max_pending_buys": {"min": 1, "max": 5, "step": 1},
    "alpha_breakout_pct": {"min": 0.005, "max": 0.10, "step": 0.005},
    "alpha_structure_lookback": {"min": 3, "max": 100, "step": 1},
    "trailing_step_pct": {"min": 0.5, "max": 5.0, "step": 0.1},
    "initial_stop_loss_pct": {"min": 0.005, "max": 0.10, "step": 0.001},
    "take_profit_pct": {"min": 0.01, "max": 0.20, "step": 0.01},
    "take_profit_rr": {"min": 0.5, "max": 5.0, "step": 0.1},
}


def apply_overrides(config: BotConfig, overrides: Optional[Dict[str, Any]] = None) -> BotConfig:
    """Return effective config with runtime overrides merged (does not mutate input)."""
    if not overrides:
        return config
    allowed = {f.name for f in fields(BotConfig)}
    kwargs: Dict[str, Any] = {}
    ta_enabled = overrides.get("alpha_ta_enabled")
    for key, value in overrides.items():
        if key == "alpha_ta_enabled":
            continue
        if key in allowed:
            kwargs[key] = value
    result = replace(config, **kwargs) if kwargs else config
    if ta_enabled is not None:
        result = replace(
            result,
            alpha_technical_analysis=replace(result.alpha_technical_analysis, enabled=bool(ta_enabled)),
        )
    return result


def effective_config_snapshot(config: BotConfig) -> Dict[str, Any]:
    """Safe tunable snapshot for HUD display (no secrets)."""
    snap: Dict[str, Any] = {}
    for key in OPERATOR_TUNABLE_KEYS:
        if key == "alpha_ta_enabled":
            snap[key] = config.alpha_technical_analysis.enabled
        else:
            snap[key] = getattr(config, key)
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
    if errors:
        return {}, errors
    return sanitized, []


def _coerce_override(key: str, value: Any) -> Any:
    if key in ("dry_run", "trading_enabled", "bracket_trailing_enabled", "alpha_ta_enabled"):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)
    if key == "alpha_max_pending_buys":
        return int(value)
    if key == "alpha_structure_lookback":
        return int(value)
    return float(value)


def _validate_merged_config(config: BotConfig, changed_keys: Any) -> List[str]:
    errors: List[str] = []
    keys = set(changed_keys)

    if "alpha_risk_per_trade_pct" in keys:
        if config.alpha_risk_per_trade_pct <= 0 or config.alpha_risk_per_trade_pct > 100:
            errors.append("alpha_risk_per_trade_pct must be between 0 and 100 (exclusive of 0)")

    if "alpha_min_edge_threshold_pct" in keys and config.alpha_min_edge_threshold_pct < 0:
        errors.append("alpha_min_edge_threshold_pct must be non-negative")

    if "alpha_buy_limit_offset_pct" in keys and config.alpha_buy_limit_offset_pct <= 0:
        errors.append("alpha_buy_limit_offset_pct must be positive")

    if "alpha_max_pending_buys" in keys and config.alpha_max_pending_buys < 1:
        errors.append("alpha_max_pending_buys must be at least 1")

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
        self.commands_path.write_text(json.dumps(commands, indent=2), encoding="utf-8")


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
