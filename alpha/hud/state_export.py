"""Serialize Alpha cycle state for the operator HUD."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from alpha.decision.engine import DecisionResult
from alpha.decision.structure import MarketStructureSnapshot, build_candle_from_mids, load_mid_history
from alpha.decision.technical_analysis import TechnicalAnalysis, TechnicalAnalysisSnapshot
from alpha.operator.activity import ActivityLog
from alpha.operator.controls import OperatorControls
from alpha.operator.runtime import derive_posture, effective_config_snapshot
from alpha.orders.types import BracketRecord
from alpha.runtime.executor import EntryExecutionResult
from alpha.types import BracketStatusSummary, OperatorSnapshot, OrderBookSnapshot
from config.settings import BotConfig

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path("logs/alpha_runtime_state.json")


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.isoformat()


def _book_payload(book: Optional[OrderBookSnapshot]) -> Dict[str, Any]:
    if book is None:
        return {}
    bids = [{"price": lv.price, "size_xrp": lv.size_xrp} for lv in book.bids[:8]]
    asks = [{"price": lv.price, "size_xrp": lv.size_xrp} for lv in book.asks[:8]]
    return {
        "best_bid": book.best_bid,
        "best_ask": book.best_ask,
        "mid": book.mid,
        "spread": book.spread,
        "spread_pct": book.spread_pct,
        "bids": bids,
        "asks": asks,
    }


def _bracket_row(record: BracketRecord) -> Dict[str, Any]:
    return {
        "bracket_id": record.bracket_id[:8],
        "bracket_id_full": record.bracket_id,
        "state": record.state.value,
        "mode": record.mode.value,
        "entry": record.entry_price_rlusd_per_xrp,
        "target_size_xrp": record.target_size_xrp,
        "filled_xrp": record.filled_xrp,
        "breakeven_passed": record.breakeven_passed,
        "breakout_confirmed": record.breakout_confirmed,
        "tp_price": record.tp_leg.price_rlusd_per_xrp if record.tp_leg else None,
        "sl_price": record.sl_leg.price_rlusd_per_xrp if record.sl_leg else None,
        "peak_mid": record.peak_mid_rlusd_per_xrp,
    }


def _load_mid_history(path: Path) -> List[float]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        samples = data.get("mids", [])
        return [float(x) for x in samples if float(x) > 0]
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return []


def _chart_candles_from_mids(mids: List[float], *, bucket: int, max_candles: int = 48) -> List[Dict[str, float]]:
    if bucket < 1:
        bucket = 1
    candles: List[Dict[str, float]] = []
    for i in range(0, len(mids), bucket):
        chunk = mids[i : i + bucket]
        candle = build_candle_from_mids(chunk)
        if candle is None:
            continue
        candles.append(
            {"o": candle.open, "h": candle.high, "l": candle.low, "c": candle.close},
        )
    return candles[-max_candles:]


def _chart_payload(
    structure: Optional[MarketStructureSnapshot],
    mids: List[float],
    config: BotConfig,
) -> Dict[str, Any]:
    lookback = max(3, int(config.alpha_structure_lookback or 20))
    bucket = max(1, min(15, lookback // 4))
    candles = _chart_candles_from_mids(mids, bucket=bucket)
    indicators: List[Dict[str, Any]] = [
        {
            "key": "structure_lookback",
            "label": "Structure lookback",
            "value": str(lookback),
            "kind": "meta",
        },
        {
            "key": "breakout_tf",
            "label": "Breakout TF",
            "value": str(config.breakout_confirmation_tf or "15m"),
            "kind": "meta",
        },
        {
            "key": "breakout_pct",
            "label": "Breakout %",
            "value": f"{float(config.alpha_breakout_pct):.3f}",
            "kind": "meta",
        },
    ]
    if structure is not None:
        indicators.extend(
            [
                {"key": "trend", "label": "Trend", "value": structure.trend, "kind": "tag"},
                {
                    "key": "mean_mid",
                    "label": "Mean mid",
                    "value": structure.mean_mid,
                    "kind": "line",
                    "color": "#60a5fa",
                },
                {
                    "key": "swing_high",
                    "label": "Swing high",
                    "value": structure.swing_high,
                    "kind": "line",
                    "color": "#fde047",
                },
                {
                    "key": "recent_high",
                    "label": "Recent high",
                    "value": structure.recent_high,
                    "kind": "line",
                    "color": "#fca5a5",
                },
                {
                    "key": "recent_low",
                    "label": "Recent low",
                    "value": structure.recent_low,
                    "kind": "line",
                    "color": "#86efac",
                },
                {
                    "key": "breakout_up",
                    "label": "Breakout up",
                    "value": "yes" if structure.breakout_up else "no",
                    "kind": "tag",
                },
                {
                    "key": "breakout_down",
                    "label": "Breakout down",
                    "value": "yes" if structure.breakout_down else "no",
                    "kind": "tag",
                },
                {
                    "key": "sample_count",
                    "label": "Samples",
                    "value": str(structure.sample_count),
                    "kind": "meta",
                },
            ]
        )
        cc = structure.confirmation_candle
        if cc is not None:
            indicators.extend(
                [
                    {
                        "key": "htf_open",
                        "label": "HTF open",
                        "value": cc.open,
                        "kind": "line",
                        "color": "#94a3b8",
                    },
                    {
                        "key": "htf_high",
                        "label": "HTF high",
                        "value": cc.high,
                        "kind": "line",
                        "color": "#f472b6",
                    },
                    {
                        "key": "htf_low",
                        "label": "HTF low",
                        "value": cc.low,
                        "kind": "line",
                        "color": "#34d399",
                    },
                    {
                        "key": "htf_close",
                        "label": "HTF close",
                        "value": cc.close,
                        "kind": "line",
                        "color": "#c084fc",
                    },
                ]
            )
    return {
        "candles": candles,
        "indicators": indicators,
        "bucket_samples": bucket,
        "mid_samples": len(mids),
    }


def build_hud_state(
    *,
    snapshot: OperatorSnapshot,
    decision: DecisionResult,
    execution: Optional[EntryExecutionResult],
    recent_events: tuple[str, ...],
    book: Optional[OrderBookSnapshot] = None,
    structure: Optional[MarketStructureSnapshot] = None,
    ta: Optional[TechnicalAnalysisSnapshot] = None,
    bracket_summary: BracketStatusSummary,
    brackets: Iterable[BracketRecord],
    open_offers: List[dict[str, Any]],
    activity: List[Dict[str, Any]],
    controls: OperatorControls,
    report_text: str = "",
    operator_overrides: Optional[Dict[str, Any]] = None,
    config_effective: Optional[BotConfig] = None,
    runtime_state_path: Path = DEFAULT_PATH,
) -> Dict[str, Any]:
    """Build JSON-serializable HUD payload from one Alpha cycle."""
    snap = snapshot

    structure_block: Dict[str, Any] = {}
    if structure is not None:
        structure_block = {
            "mid": structure.mid,
            "trend": structure.trend,
            "mean_mid": structure.mean_mid,
            "recent_high": structure.recent_high,
            "recent_low": structure.recent_low,
            "swing_high": structure.swing_high,
            "breakout_up": structure.breakout_up,
            "breakout_down": structure.breakout_down,
            "sample_count": structure.sample_count,
            "summary": structure.summary,
        }
        if structure.confirmation_candle is not None:
            cc = structure.confirmation_candle
            structure_block["confirmation_candle"] = {
                "o": cc.open,
                "h": cc.high,
                "l": cc.low,
                "c": cc.close,
            }

    active_brackets = (
        bracket_summary.active_fixed
        + bracket_summary.active_sl_trailing
        + bracket_summary.active_breakout_trailing
    )
    posture = derive_posture(
        decision_action=decision.action.value,
        pending_buys=bracket_summary.pending_buys,
        active_brackets=active_brackets,
    )
    overrides = operator_overrides or {}
    effective = config_effective or BotConfig()
    tunables = effective_config_snapshot(effective)
    mid_history = load_mid_history(runtime_state_path.parent / "alpha_mid_history.json")
    chart = _chart_payload(structure, mid_history, effective)
    if ta is None and effective.alpha_technical_analysis.enabled:
        ta = TechnicalAnalysis(effective).analyze(mid_history, mid=snap.balances.mid_rlusd_per_xrp)
    ta_block = ta.to_dict() if ta is not None else {"enabled": False}

    return {
        "hud_kind": "alpha",
        "alpha_version": snap.alpha_version,
        "updated_utc": _iso(snap.generated_utc),
        "network": snap.network,
        "dry_run": snap.dry_run,
        "trading_enabled": snap.trading_enabled,
        "posture": posture,
        "operator_overrides": overrides,
        "config_effective": tunables,
        "account_address": snap.account_address,
        "operator_paused": controls.trading_paused,
        "pause_reason": controls.pause_reason,
        "mid": snap.balances.mid_rlusd_per_xrp,
        "portfolio_xrp_equiv": snap.balances.portfolio_xrp_equiv,
        "xrp": snap.balances.xrp,
        "rlusd": snap.balances.rlusd,
        "inventory": {
            "xrp_ratio": snap.inventory.xrp_ratio,
            "target_xrp_ratio": snap.inventory.target_xrp_ratio,
            "deviation": snap.inventory.deviation,
            "label": snap.inventory.label,
            "summary": snap.inventory.summary,
            "buy_blocked": snap.inventory.buy_blocked_imbalance,
        },
        "risk": {
            "kill_switch_active": snap.risk.kill_switch_active,
            "kill_switch_reason": snap.risk.kill_switch_reason,
            "drawdown_pct": snap.risk.drawdown_pct,
            "max_drawdown_pct": snap.risk.max_drawdown_pct,
            "session_pnl_xrp": snap.risk.session_pnl_xrp,
            "preflight_ready": snap.risk.preflight_ready,
            "preflight_summary": snap.risk.preflight_summary,
            "trading_allowed": snap.risk.trading_allowed,
            "alerts": list(snap.risk.alerts),
        },
        "decision": {
            "action": decision.action.value,
            "reason": decision.reason,
        },
        "execution": (
            {
                "action": execution.action,
                "executed": execution.executed,
                "dry_run": execution.dry_run,
                "message": execution.message,
            }
            if execution
            else None
        ),
        "brackets": {
            "summary": {
                "total": bracket_summary.total,
                "pending_buys": bracket_summary.pending_buys,
                "active_fixed": bracket_summary.active_fixed,
                "active_sl_trailing": bracket_summary.active_sl_trailing,
                "active_breakout_trailing": bracket_summary.active_breakout_trailing,
                "labels": list(bracket_summary.labels),
            },
            "records": [_bracket_row(r) for r in brackets],
        },
        "open_offers": open_offers[:40],
        "open_offers_count": len(open_offers),
        "structure": structure_block,
        "chart": chart,
        "technical_analysis": ta_block,
        "book": _book_payload(book if isinstance(book, OrderBookSnapshot) else None),
        "recent_activity": activity[-40:],
        "recent_events": list(recent_events),
        "report_text": report_text,
        "last_note": f"{decision.action.value}: {decision.reason}",
    }


def write_alpha_runtime_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def publish_cycle_to_hud(
    *,
    snapshot: OperatorSnapshot,
    decision: DecisionResult,
    execution: Optional[EntryExecutionResult],
    recent_events: tuple[str, ...],
    path: Path = DEFAULT_PATH,
    book: Optional[OrderBookSnapshot] = None,
    structure: Optional[MarketStructureSnapshot] = None,
    ta: Optional[TechnicalAnalysisSnapshot] = None,
    bracket_summary: BracketStatusSummary,
    brackets: Iterable[BracketRecord],
    open_offers: List[dict[str, Any]],
    activity_log: ActivityLog,
    controls: OperatorControls,
    report_text: str = "",
    operator_overrides: Optional[Dict[str, Any]] = None,
    config_effective: Optional[BotConfig] = None,
) -> None:
    try:
        state = build_hud_state(
            snapshot=snapshot,
            decision=decision,
            execution=execution,
            recent_events=recent_events,
            book=book,
            structure=structure,
            ta=ta,
            bracket_summary=bracket_summary,
            brackets=brackets,
            open_offers=open_offers,
            activity=activity_log.tail(40),
            controls=controls,
            report_text=report_text,
            operator_overrides=operator_overrides,
            config_effective=config_effective,
            runtime_state_path=path,
        )
        write_alpha_runtime_state(path, state)
    except OSError as exc:
        logger.warning("alpha_hud_state_write_failed | %s", exc)
