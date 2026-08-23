"""Serialize Alpha cycle state for the operator HUD."""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from alpha.decision.reentry import ReentrySnapshot
from alpha.decision.structure import MarketStructureSnapshot, build_candle_from_mids, load_mid_history
from alpha.decision.price_history import PRICE_HISTORY_PATH, load_price_series, effective_sample_seconds
from alpha.decision.ohlc_cache import cache_status, get_candles
from alpha.decision.ta_config import (
    CHART_CANDLE_INTERVAL_OPTIONS_SECONDS,
    CHART_DEFAULT_INTERVAL_SECONDS,
    CHART_MAX_CANDLES,
    chart_bucket_samples,
    effective_ta_candle_interval_seconds,
    resolve_ta_candle_bucket_samples,
)
from alpha.decision.technical_analysis import TechnicalAnalysis, TechnicalAnalysisSnapshot
from alpha.ledger.market_conditions import build_market_conditions, refresh_dca_vs_mid
from alpha.operator.activity import ActivityLog
from alpha.operator.controls import OperatorControls
from alpha.operator.runtime import derive_posture, effective_config_snapshot
from alpha.pro.circuit_breaker import defensive_status_snapshot
from alpha.pro.treasury import treasury_placeholder_status
from utils.risk_capital_sync import build_risk_capital_snapshot
from alpha.reporting.bag_growth import build_bag_growth_snapshot
from alpha.reporting.realized_pnl import build_realized_pnl_snapshot
from alpha.orders.types import BracketRecord
from alpha.runtime.executor import EntryExecutionResult
from alpha.types import BracketStatusSummary, LiquidityDepth, OperatorSnapshot, OrderBookSnapshot
from config.settings import BotConfig

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path("logs/alpha_runtime_state.json")


def sanitize_for_json(value: Any) -> Any:
    """Strip NaN/inf so HUD JSON responses work on strict encoders (Python 3.14+)."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_for_json(v) for v in value]
    return value


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
        "sl_deferred": (
            sl_leg is not None
            and sl_leg.sequence is None
            and record.state.value == "bracket_active"
        ),
        "peak_mid": record.peak_mid_rlusd_per_xrp,
        "created_at": record.created_at.isoformat() if record.created_at else None,
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
    max_candles: int = CHART_MAX_CANDLES,
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
    sample_seconds = effective_sample_seconds(
        config.alpha_cycle_interval_seconds,
        config.alpha_price_sample_interval_seconds,
    )
    chart_interval = CHART_DEFAULT_INTERVAL_SECONDS
    bucket = chart_bucket_samples(
        chart_interval,
        cycle_seconds=config.alpha_cycle_interval_seconds,
        sample_interval_seconds=config.alpha_price_sample_interval_seconds,
    )
    ta_bucket = resolve_ta_candle_bucket_samples(
        config.alpha_technical_analysis,
        cycle_seconds=config.alpha_cycle_interval_seconds,
        sample_interval_seconds=config.alpha_price_sample_interval_seconds,
    )
    ta_candle_interval_seconds = ta_bucket * sample_seconds
    candles = _chart_candles_from_mids(
        mids,
        bucket=bucket,
        max_candles=CHART_MAX_CANDLES,
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
            "key": "ta_candle_interval",
            "label": "TA candle",
            "value": f"{ta_candle_interval_seconds}s (~{ta_candle_interval_seconds // 60}m)" if ta_candle_interval_seconds >= 60 else f"{ta_candle_interval_seconds}s",
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
    # Live HUD polls /state every 1s — do not ship full mid history (can be 300KB+ and
    # leaves the dashboard blank). Keep enough ticks for 5m/30m resamples; longer TFs
    # use server-built candles.
    clean_mids = [round(float(m), 6) for m in mids if float(m) > 0]
    hud_mid_cap = max(500, int(CHART_MAX_CANDLES * 300 / max(1, sample_seconds)) * 2)
    return {
        "candles": candles,
        "mids": clean_mids[-hud_mid_cap:],
        "indicators": indicators,
        "bucket_samples": bucket,
        "sample_seconds": sample_seconds,
        "candle_seconds": bucket * sample_seconds,
        "max_candles": CHART_MAX_CANDLES,
        "chart_interval_options": list(CHART_CANDLE_INTERVAL_OPTIONS_SECONDS),
        "default_chart_interval_seconds": CHART_DEFAULT_INTERVAL_SECONDS,
        "mid_samples": len(clean_mids),
        "mids_capped": len(clean_mids) > hud_mid_cap,
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
    orphan_bids: int = 0,
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
    tunables = effective_config_snapshot(effective, overrides)
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
        ta_interval = effective_ta_candle_interval_seconds(
            effective.alpha_technical_analysis,
            cycle_seconds=effective.alpha_cycle_interval_seconds,
            sample_interval_seconds=effective.alpha_price_sample_interval_seconds,
        )
        ohlc = get_candles(ta_interval, logs_dir=runtime_state_path.parent)
        from alpha.decision.htf_bias import resolve_htf_interval_seconds

        htf_sec = resolve_htf_interval_seconds(
            effective.alpha_technical_analysis.htf_bias,
            ltf_interval_seconds=ta_interval,
        )
        htf_ohlc = get_candles(htf_sec, logs_dir=runtime_state_path.parent)
        ta = TechnicalAnalysis(effective).analyze(
            price_history,
            mid=ref,
            candles=ohlc if len(ohlc) >= 2 else None,
            htf_candles=htf_ohlc if len(htf_ohlc) >= 2 else None,
            htf_interval_seconds=htf_sec,
        )
    ta_interval = effective_ta_candle_interval_seconds(
        effective.alpha_technical_analysis,
        cycle_seconds=effective.alpha_cycle_interval_seconds,
        sample_interval_seconds=effective.alpha_price_sample_interval_seconds,
    )
    ohlc_cache = cache_status(runtime_state_path.parent, ta_interval_seconds=ta_interval)
    from alpha.decision.market_metrics import metrics_summary

    market_metrics = metrics_summary(runtime_state_path.parent, hours=24.0)
    ta_block = ta.to_dict() if ta is not None else {"enabled": False}
    from alpha.decision.tape_participation import evaluate_tape_participation

    ref_mid = float(book.mid) if isinstance(book, OrderBookSnapshot) and book.mid else 0.0
    tape_participation = evaluate_tape_participation(
        effective,
        mid=ref_mid,
        structure=structure,
        ta=ta,
    ).to_dict()
    from alpha.decision.momentum_entry import evaluate_bull_run_entry

    momentum_entry = evaluate_bull_run_entry(
        effective,
        inventory=snap.inventory,
        mid=ref_mid,
        structure=structure,
        ta=ta,
    ).to_dict()
    from alpha.decision.opportunity_watch import evaluate_opportunity_watch

    from alpha.decision.accumulation_regime import evaluate_accumulation_regime
    from alpha.hud.operator_market_regime import OPERATOR_MARKET_REGIME_KEY, normalize_market_regime

    operator_regime = normalize_market_regime((operator_overrides or {}).get(OPERATOR_MARKET_REGIME_KEY))
    accumulation_regime = evaluate_accumulation_regime(
        effective,
        inventory=snap.inventory,
        mid=ref_mid,
        structure=structure,
        ta=ta,
        operator_market_regime=operator_regime,
        pending_buys=bracket_summary.pending_buys,
        decision_action=decision.action.value,
        rlusd_balance=snap.balances.rlusd,
    ).to_dict()

    from alpha.decision.reload_regime import evaluate_reload_regime

    strength_sell_pending = sum(
        1 for o in open_offers if str(o.get("side") or "") == "ask"
    )
    reload_regime = evaluate_reload_regime(
        effective,
        inventory=snap.inventory,
        mid=ref_mid,
        structure=structure,
        ta=ta,
        operator_market_regime=operator_regime,
        rlusd_balance=snap.balances.rlusd,
        pending_funding_sells=strength_sell_pending,
        decision_action=decision.action.value,
    ).to_dict()

    from alpha.decision.drawdown_reload import evaluate_drawdown_reload

    drawdown_reload = evaluate_drawdown_reload(
        effective,
        inventory=snap.inventory,
        mid=ref_mid,
        balances=snap.balances,
        pending_drawdown_sells=0,
        decision_action=decision.action.value,
    ).to_dict()

    opportunity_watch = evaluate_opportunity_watch(
        effective,
        inventory=snap.inventory,
        mid=ref_mid,
        structure=structure,
        ta=ta,
        decision_action=decision.action.value,
        decision_reason=decision.reason,
        pending_buys=bracket_summary.pending_buys,
        trading_enabled=snap.trading_enabled,
        operator_paused=controls.trading_paused,
        accumulation_regime=accumulation_regime,
        reload_regime=reload_regime,
    ).to_dict()
    market_conditions = build_market_conditions(
        book=book if isinstance(book, OrderBookSnapshot) else None,
        liquidity=liquidity,
        config=effective,
        portfolio_xrp_equiv=snap.balances.portfolio_xrp_equiv,
        ta=ta,
        brackets=brackets,
        log_dir=runtime_state_path.parent,
        balance_xrp=snap.balances.xrp,
    )
    risk_capital = build_risk_capital_snapshot(
        effective,
        portfolio_xrp_equiv=snap.balances.portfolio_xrp_equiv,
        mid_rlusd_per_xrp=snap.balances.mid_rlusd_per_xrp,
    )

    realized_pnl_24h = build_realized_pnl_snapshot(
        logs_dir=runtime_state_path.parent,
        hours=24.0,
        session_pnl_xrp=snap.risk.session_pnl_xrp,
        mid_rlusd_per_xrp=snap.balances.mid_rlusd_per_xrp,
        max_recent_exits=5,
    )

    bag_growth = build_bag_growth_snapshot(
        xrp=snap.balances.xrp,
        rlusd=snap.balances.rlusd,
        mid_rlusd_per_xrp=snap.balances.mid_rlusd_per_xrp,
        logs_dir=runtime_state_path.parent,
        persist_week=True,
    )

    from alpha.reporting.tax_ledger import tax_periods_payload

    tax_log = tax_periods_payload(runtime_state_path.parent)

    pro_block = defensive_status_snapshot(
        logs_dir=runtime_state_path.parent,
        config=config_effective or BotConfig.load(),
    )
    pro_block["treasury"] = treasury_placeholder_status(logs_dir=runtime_state_path.parent)

    return {
        "hud_kind": "alpha",
        "alpha_version": snap.alpha_version,
        "updated_utc": _iso(snap.generated_utc),
        "network": snap.network,
        "dry_run": snap.dry_run,
        "trading_enabled": snap.trading_enabled,
        "posture": posture,
        "ready_state": (
            accumulation_regime.get("phase")
            if accumulation_regime.get("armed") or accumulation_regime.get("phase") == "executing"
            else opportunity_watch.get("state", "idle")
        ),
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
        "realized_pnl_24h": realized_pnl_24h,
        "bag_growth": bag_growth,
        "decision": {
            "action": decision.action.value,
            "reason": decision.reason,
            "edge_pct": decision.edge_pct,
        },
        "reentry": reentry.to_dict() if reentry is not None else {"active": False},
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
                "orphan_bids": orphan_bids,
                "labels": list(bracket_summary.labels),
            },
            "records": [_bracket_row(r) for r in brackets],
        },
        "open_offers": open_offers[:40],
        "open_offers_count": len(open_offers),
        "structure": structure_block,
        "chart": chart,
        "technical_analysis": ta_block,
        "tape_participation": tape_participation,
        "momentum_entry": momentum_entry,
        "accumulation_regime": accumulation_regime,
        "reload_regime": reload_regime,
        "drawdown_reload": drawdown_reload,
        "opportunity_watch": opportunity_watch,
        "ohlc_cache": ohlc_cache,
        "market_metrics": market_metrics,
        "book": _book_payload(book if isinstance(book, OrderBookSnapshot) else None),
        "market_conditions": market_conditions,
        "risk_capital": risk_capital,
        "recent_activity": activity[-40:],
        "recent_events": list(recent_events),
        "report_text": report_text,
        "tax_log": tax_log,
        "pro": pro_block,
        "last_note": f"{decision.action.value}: {decision.reason}",
        "engine_cycle": int(engine_cycle),
        "book_updated_utc": _iso(snap.generated_utc) if book else None,
    }


def refresh_live_metrics_in_state(
    state: Dict[str, Any],
    *,
    logs_dir: str | Path = "logs",
    persist_week: bool = False,
) -> Dict[str, Any]:
    """
    Recompute bag growth (and session MTM) when serving HUD /state.

    Operator deposits and session baseline resets apply on the next poll without
    waiting for an engine restart or cycle publish.
    """
    if not isinstance(state, dict):
        return state
    logs = Path(logs_dir)
    mid_raw = state.get("mid")
    try:
        mid = float(mid_raw) if mid_raw is not None else None
    except (TypeError, ValueError):
        mid = None
    if mid is not None and mid <= 0:
        mid = None

    xrp = float(state.get("xrp") or 0.0)
    rlusd = float(state.get("rlusd") or 0.0)

    state["bag_growth"] = build_bag_growth_snapshot(
        xrp=xrp,
        rlusd=rlusd,
        mid_rlusd_per_xrp=mid,
        logs_dir=logs,
        persist_week=persist_week,
    )

    if mid is not None:
        from risk.drawdown import portfolio_value_xrp

        portfolio = portfolio_value_xrp(xrp, rlusd, mid)
        session_path = logs / "alpha_session.json"
        if session_path.is_file():
            try:
                sess = json.loads(session_path.read_text(encoding="utf-8"))
                baseline = float(sess.get("baseline_portfolio_xrp") or 0.0)
                if baseline > 0:
                    risk = state.get("risk")
                    if not isinstance(risk, dict):
                        risk = {}
                        state["risk"] = risk
                    risk["session_pnl_xrp"] = round(portfolio - baseline, 4)
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                pass

    return state


def write_alpha_runtime_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    clean = sanitize_for_json(state)
    tmp.write_text(json.dumps(clean, indent=2, default=str, allow_nan=False), encoding="utf-8")
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
        refresh_dca_vs_mid(mc, float(book.mid))
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
    orphan_bids: int = 0,
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
            orphan_bids=orphan_bids,
        )
        write_alpha_runtime_state(path, state)
    except OSError as exc:
        logger.warning("alpha_hud_state_write_failed | %s", exc)
