"""Auto-defensive circuit breaker — SL-heavy nights trigger bear posture knobs."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from alpha.hud.operator_market_regime import OPERATOR_MARKET_REGIME_KEY
from alpha.operator.runtime import OperatorRuntimeStore, apply_overrides, effective_config_snapshot
from alpha.pro.replay import build_replay_report
from config.settings import BotConfig

logger = logging.getLogger(__name__)

_STATE_PATH = Path("logs/alpha_defensive_circuit.json")

# Keys the circuit may auto-adjust (restored on release).
_DEFENSIVE_KEYS: Tuple[str, ...] = (
    OPERATOR_MARKET_REGIME_KEY,
    "alpha_max_pending_buys",
    "alpha_buy_limit_offset_pct",
    "alpha_reentry_sl_cooldown_cycles",
    "alpha_risk_per_trade_pct",
)


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _load_state(path: Path = _STATE_PATH) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: Dict[str, Any], path: Path = _STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _defensive_bundle(effective: Dict[str, Any]) -> Dict[str, Any]:
    """Knob patch applied when circuit trips."""
    risk = float(effective.get("alpha_risk_per_trade_pct") or 2.0)
    offset = float(effective.get("alpha_buy_limit_offset_pct") or 0.15)
    sl_cd = int(effective.get("alpha_reentry_sl_cooldown_cycles") or 10)
    max_buys = int(effective.get("alpha_max_pending_buys") or 1)
    return {
        OPERATOR_MARKET_REGIME_KEY: "bear",
        "alpha_max_pending_buys": min(max_buys, 1),
        "alpha_buy_limit_offset_pct": max(offset, 0.18),
        "alpha_reentry_sl_cooldown_cycles": max(sl_cd, 20),
        "alpha_risk_per_trade_pct": min(risk, 2.5),
    }


def _should_trigger(report: Dict[str, Any], config: BotConfig) -> Tuple[bool, str]:
    verdict = str(report.get("verdict") or "")
    sl = int(report.get("sl_exits") or 0)
    tp = int(report.get("tp_exits") or 0)
    total = sl + tp
    realized = float(report.get("realized_profit_xrp_equiv") or 0.0)
    min_exits = max(1, int(config.alpha_defensive_min_exits))
    sl_thresh = max(1, int(config.alpha_defensive_sl_exit_threshold))

    if verdict in ("sl_heavy", "bleeding", "churn"):
        return True, f"replay_verdict={verdict}"
    if sl >= sl_thresh and total >= min_exits:
        return True, f"sl_exits={sl}>={sl_thresh}"
    if realized <= -abs(float(config.alpha_defensive_realized_loss_xrp)) and total >= min_exits:
        return True, f"realized_pnl={realized:.4f}"
    return False, ""


def _manual_suppress_active(state: Dict[str, Any]) -> bool:
    until_raw = state.get("manual_suppress_until_utc")
    if not until_raw:
        return False
    try:
        until = datetime.fromisoformat(str(until_raw).replace("Z", "+00:00"))
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return _utc_now() < until
    except ValueError:
        return False


def _should_release(report: Dict[str, Any], state: Dict[str, Any], config: BotConfig) -> Tuple[bool, str]:
    if not state.get("active"):
        return False, ""
    triggered_raw = state.get("triggered_utc")
    if triggered_raw:
        try:
            triggered = datetime.fromisoformat(str(triggered_raw).replace("Z", "+00:00"))
            if triggered.tzinfo is None:
                triggered = triggered.replace(tzinfo=timezone.utc)
            release_h = max(1.0, float(config.alpha_defensive_auto_release_hours))
            if _utc_now() - triggered < timedelta(hours=release_h):
                tp = int(report.get("tp_exits") or 0)
                sl = int(report.get("sl_exits") or 0)
                if tp > sl and float(report.get("realized_profit_xrp_equiv") or 0) >= 0:
                    return True, "tp_recovery"
                return False, ""
        except ValueError:
            pass
    tp = int(report.get("tp_exits") or 0)
    sl = int(report.get("sl_exits") or 0)
    if tp > 0 and tp >= sl and str(report.get("verdict")) == "healthy":
        return True, "healthy_replay"
    return False, ""


def defensive_status_snapshot(
    *,
    logs_dir: str | Path = "logs",
    config: Optional[BotConfig] = None,
) -> Dict[str, Any]:
    cfg = config or BotConfig.load()
    state_path = Path(logs_dir) / "alpha_defensive_circuit.json"
    state = _load_state(state_path)
    report = build_replay_report(
        logs_dir=logs_dir,
        hours=float(cfg.alpha_defensive_window_hours),
    )
    suppress_until = state.get("manual_suppress_until_utc")
    return {
        "enabled": bool(cfg.alpha_defensive_circuit_enabled),
        "active": bool(state.get("active")),
        "triggered_utc": state.get("triggered_utc"),
        "reason": state.get("reason"),
        "release_utc": state.get("release_utc"),
        "release_reason": state.get("release_reason"),
        "manual_suppress_until_utc": suppress_until,
        "manual_suppress_active": _manual_suppress_active(state),
        "applied_overrides": state.get("applied_overrides") or {},
        "saved_overrides": state.get("saved_overrides") or {},
        "replay": report,
        "thresholds": {
            "sl_exit_threshold": cfg.alpha_defensive_sl_exit_threshold,
            "window_hours": cfg.alpha_defensive_window_hours,
            "realized_loss_xrp": cfg.alpha_defensive_realized_loss_xrp,
            "min_exits": cfg.alpha_defensive_min_exits,
            "auto_release_hours": cfg.alpha_defensive_auto_release_hours,
            "manual_release_hours": cfg.alpha_defensive_manual_release_hours,
        },
    }


class DefensiveCircuit:
    """Evaluate replay metrics each cycle; auto-apply or release defensive overrides."""

    def __init__(
        self,
        *,
        store: OperatorRuntimeStore,
        state_path: Path = _STATE_PATH,
    ) -> None:
        self._store = store
        self._state_path = state_path

    def tick(
        self,
        config: BotConfig,
        *,
        logs_dir: str | Path = "logs",
        force_evaluate: bool = False,
    ) -> Dict[str, Any]:
        """Run trigger/release logic. Returns event dict (may be empty)."""
        if not config.alpha_defensive_circuit_enabled or config.dry_run:
            return {"event": "skipped", "reason": "disabled_or_dry_run"}

        state = _load_state(self._state_path)
        report = build_replay_report(
            logs_dir=logs_dir,
            hours=float(config.alpha_defensive_window_hours),
        )
        overrides = self._store.load_overrides()
        effective_cfg = apply_overrides(config, overrides)
        effective = effective_config_snapshot(effective_cfg, overrides)

        if state.get("active"):
            release, release_reason = _should_release(report, state, config)
            if release:
                return self._release(state, release_reason)
            return {"event": "hold", "active": True, "reason": state.get("reason")}

        if not force_evaluate and _manual_suppress_active(state):
            return {
                "event": "suppressed",
                "active": False,
                "manual_suppress_until_utc": state.get("manual_suppress_until_utc"),
            }

        trigger, reason = _should_trigger(report, config)
        if not trigger:
            return {"event": "ok", "active": False}

        return self._activate(state, effective, reason, report)

    def release_manual(self, config: Optional[BotConfig] = None) -> Dict[str, Any]:
        cfg = config or BotConfig.load()
        state = _load_state(self._state_path)
        if not state.get("active"):
            return {"event": "noop", "ok": False, "message": "circuit not active"}
        suppress_h = max(1.0, float(cfg.alpha_defensive_manual_release_hours))
        state["manual_suppress_until_utc"] = (_utc_now() + timedelta(hours=suppress_h)).isoformat()
        result = self._release(state, "operator_manual")
        result["manual_suppress_until_utc"] = state["manual_suppress_until_utc"]
        return result

    def _activate(
        self,
        state: Dict[str, Any],
        effective: Dict[str, Any],
        reason: str,
        report: Dict[str, Any],
    ) -> Dict[str, Any]:
        bundle = _defensive_bundle(effective)
        saved = {k: effective.get(k) for k in _DEFENSIVE_KEYS if k in effective}
        merged = self._store.load_overrides()
        merged.update(bundle)
        self._store.save_overrides(merged)
        new_state = {
            "active": True,
            "triggered_utc": _utc_now().isoformat(),
            "reason": reason,
            "applied_overrides": bundle,
            "saved_overrides": saved,
            "replay_verdict": report.get("verdict"),
        }
        _save_state(new_state, self._state_path)
        logger.warning(
            "defensive_circuit_activated | reason=%s | overrides=%s",
            reason,
            bundle,
        )
        return {"event": "activated", "reason": reason, "applied": bundle}

    def _release(self, state: Dict[str, Any], release_reason: str) -> Dict[str, Any]:
        merged = deepcopy(self._store.load_overrides())
        for key in _DEFENSIVE_KEYS:
            if key in state.get("saved_overrides", {}):
                merged[key] = state["saved_overrides"][key]
            else:
                merged.pop(key, None)
        self._store.save_overrides(merged)
        state["active"] = False
        state["release_utc"] = _utc_now().isoformat()
        state["release_reason"] = release_reason
        state.pop("applied_overrides", None)
        _save_state(state, self._state_path)
        logger.info("defensive_circuit_released | reason=%s", release_reason)
        return {"event": "released", "reason": release_reason}
