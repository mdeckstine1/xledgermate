"""Serialize Alpha cycle state for the operator HUD."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from alpha.decision.reentry import ReentrySnapshot
from alpha.decision.structure import MarketStructureSnapshot, build_candle_from_mids, load_mid_history
from alpha.decision.price_history import PRICE_HISTORY_PATH, load_price_series, effective_sample_seconds
from alpha.decision.technical_analysis import TechnicalAnalysis, TechnicalAnalysisSnapshot
from alpha.ledger.market_conditions import build_market_conditions
from alpha.operator.activity import ActivityLog
from alpha.operator.controls import OperatorControls
from alpha.operator.runtime import derive_posture, effective_config_snapshot
from alpha.orders.types import BracketRecord
from alpha.runtime.executor import EntryExecutionResult
from alpha.types import BracketStatusSummary, LiquidityDepth, OperatorSnapshot, OrderBookSnapshot
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
    entry = record.entry_price_rlusd_per_xrp
    filled = max(0.0, record.filled_xrp)
    target = max(0.0, record.target_size_xrp)
    size_xrp = filled if filled > 0 else target
    entry_rlusd = round(size_xrp * entry, 4) if entry > 0 and size_xrp > 0 else None
    committed_rlusd = (
        round(target * entry, 4) if entry > 0 and target > 0 else None
    )
    tp_leg = record.tp_leg
    sl_leg = record.sl_leg
    open_states = ("pending_buy", "bracket_active", "trailing_placeholder")
    return {
        "bracket_id": record.bracket_id[:8],
        "bracket_id_full": record.bracket_id,
        "state": record.state.value,
        "mode": record.mode.value,
        "buy_sequence": record.buy_sequence,
        "can_cancel": record.state.value in open_states,
        "can_edit_entry": record.state.value == "pending_buy",
        "entry": entry,
        "size_xrp": round(size_xrp, 4) if size_xrp > 0 else None,
        "target_size_xrp": round(target, 4) if target > 0 else None,
        "filled_xrp": round(filled, 4) if filled > 0 else None,
        "entry_rlusd": entry_rlusd,
        "committed_rlusd": committed_rlusd,
        "size_label": (
            "filled"
            if filled > 0
            else ("order" if record.state.value == "pending_buy" else "target")
        ),
        "breakeven_passed": record.breakeven_passed,
        "breakout_confirmed": record.breakout_confirmed,
        "tp_price": tp_leg.price_rlusd_per_xrp if tp_leg else None,
        "tp_size_xrp": round(tp_leg.size_xrp, 4) if tp_leg else None,
        "sl_price": sl_leg.price_rlusd_per_xrp if sl_leg else None,
        "sl_size_xrp": round(sl_leg.size_xrp, 4) if sl_leg else None,
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


def _chart_candles_from_mids(
    mids: List[float],
    *,
    bucket: int,
    max_candles: int = 48,
    sample_seconds: int = 60,
    end_utc: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    if bucket < 1:
        bucket = 1
    chunks: List[List[float]] = []
    clean = [float(m) for m in mids if float(m) > 0]
    for i in range(0, len(clean), bucket):
        chunk = clean[i : i + bucket]
        if len(chunk) >= 2:
            chunks.append(chunk)
    chunks = chunks[-max_candles:]
    candles: List[Dict[str, Any]] = []
    n = len(chunks)
    for i, chunk in enumerate(chunks):
        candle = build_candle_from_mids(chunk)
        if candle is None:
            continue
        entry: Dict[str, Any] = {
            "o": candle.open,
            "h": candle.high,
            "l": candle.low,
            "c": candle.close,
        }
        if end_utc is not None and n > 0:
            offset_sec = (n - 1 - i) * bucket * max(1, sample_seconds)
            t = end_utc - timedelta(seconds=offset_sec)
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            entry["t"] = _iso(t)
        candles.append(entry)
    return candles


def _chart_payload(
    structure: Optional[MarketStructureSnapshot],
    mids: List[float],
    config: BotConfig,
    *,
    price_source: str = "mid",
    end_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    lookback = max(3, int(config.alpha_structure_lookback or 20))
    bucket = max(1, min(15, max(1, config.alpha_technical_analysis.candle_bucket_samples or 5)))
    sample_seconds = effective_sample_seconds(
        config.alpha_cycle_interval_seconds,
        config.alpha_price_sample_interval_seconds,
    )
    candles = _chart_candles_from_mids(
        mids,
        bucket=bucket,
        sample_seconds=sample_seconds,
        end_utc=end_utc,
    )
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
        {
            "key": "chart_price_source",
            "label": "Chart price",
            "value": str(price_source or "mid"),
            "kind": "meta",
        },
        {
            "key": "structure_price_source",
            "label": "Structure price",
            "value": str(config.alpha_structure_price_source or "ask"),
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
        "sample_seconds": sample_seconds,
        "candle_seconds": bucket * sample_seconds,
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
    reentry: Optional[ReentrySnapshot] = None,
    liquidity: Optional[LiquidityDepth] = None,
    engine_cycle: int = 0,
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
    history_path = runtime_state_path.parent / PRICE_HISTORY_PATH.name
    ta_source = effective.alpha_technical_analysis.candle_price_source
    chart_source = effective.alpha_chart_price_source or "mid"
    price_history = load_price_series(ta_source, path=history_path)
    chart_history = load_price_series(chart_source, path=history_path)
    chart = _chart_payload(
        structure,
        chart_history,
        effective,
        price_source=chart_source,
        end_utc=snap.generated_utc,
    )
    if ta is None and effective.alpha_technical_analysis.enabled:
        from alpha.decision.price_history import resolve_book_price, book_prices_from_snapshot

        ref = snap.balances.mid_rlusd_per_xrp
        if book is not None:
            resolved = resolve_book_price(book_prices_from_snapshot(book), ta_source)
            if resolved is not None:
                ref = resolved
        ta = TechnicalAnalysis(effective).analyze(price_history, mid=ref)
    ta_block = ta.to_dict() if ta is not None else {"enabled": False}
    market_conditions = build_market_conditions(
        book=book if isinstance(book, OrderBookSnapshot) else None,
        liquidity=liquidity,
        config=effective,
        portfolio_xrp_equiv=snap.balances.portfolio_xrp_equiv,
        ta=ta,
    )

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
            "edge_pct": decision.edge_pct,
        },
        "reentry": (
            reentry.to_dict()
            if reentry is not None and reentry.active
            else {"active": False}
        ),
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
        "market_conditions": market_conditions,
        "recent_activity": activity[-40:],
        "recent_events": list(recent_events),
        "report_text": report_text,
        "tax_log": {
            "path": f"logs/trades_{datetime.now(tz=timezone.utc).strftime('%Y-%m')}.csv",
            "transfers_path": "logs/transfers.csv",
        },
        "last_note": f"{decision.action.value}: {decision.reason}",
        "engine_cycle": int(engine_cycle),
        "book_updated_utc": _iso(snap.generated_utc) if book else None,
    }


def write_alpha_runtime_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def patch_runtime_book_quote(path: Path, book: OrderBookSnapshot) -> bool:
    """Merge a fresh L1 book quote into the HUD state without a full cycle publish."""
    if not book or not (book.mid or book.best_bid or book.best_ask):
        return False
    if not path.is_file():
        return False
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(state, dict):
        return False

    payload = _book_payload(book)
    if not payload:
        return False

    state["book"] = payload
    if book.mid and book.mid > 0:
        state["mid"] = book.mid
    mc = state.get("market_conditions")
    if isinstance(mc, dict) and book.mid and book.mid > 0:
        mc["mid"] = book.mid
        if book.spread_pct is not None:
            mc["spread_pct"] = book.spread_pct
        state["market_conditions"] = mc
    state["book_updated_utc"] = _iso(datetime.now(tz=timezone.utc))
    try:
        write_alpha_runtime_state(path, state)
    except OSError as exc:
        logger.warning("alpha_hud_book_patch_failed | %s", exc)
        return False
    return True


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
    reentry: Optional[ReentrySnapshot] = None,
    liquidity: Optional[LiquidityDepth] = None,
    engine_cycle: int = 0,
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
            reentry=reentry,
            liquidity=liquidity,
            engine_cycle=engine_cycle,
        )
        write_alpha_runtime_state(path, state)
    except OSError as exc:
        logger.warning("alpha_hud_state_write_failed | %s", exc)
