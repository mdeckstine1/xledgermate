"""Persist per-cycle volatility, liquidity, and regime metrics in SQLite."""

from __future__ import annotations

import logging
import math
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

from alpha.decision.ohlc_cache import _connect, _db_path, _init_schema, get_candles
from alpha.decision.structure import CandleData

if TYPE_CHECKING:
    from alpha.decision.reentry import ReentrySnapshot
    from alpha.decision.structure import MarketStructureSnapshot
    from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
    from alpha.types import InventorySnapshot, LiquidityDepth, OrderBookSnapshot

logger = logging.getLogger(__name__)

_METRICS_RETENTION_DAYS = 7
_METRICS_MAX_ROWS = 15_000
_ATR_PERIOD = 14
_REALIZED_VOL_LOOKBACK = 48


def _utc_ts(dt: Optional[datetime] = None) -> int:
    if dt is None:
        dt = datetime.now(tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _ensure_metrics_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cycle_metrics (
            ts INTEGER NOT NULL PRIMARY KEY,
            ts_utc TEXT NOT NULL,
            mid REAL,
            spread_pct REAL,
            bid_depth_xrp REAL,
            ask_depth_xrp REAL,
            bid_depth_1pct_xrp REAL,
            ask_depth_1pct_xrp REAL,
            atr_pct REAL,
            realized_vol_daily_pct REAL,
            bb_bandwidth_pct REAL,
            ta_buy_score REAL,
            ta_bias TEXT,
            inventory_deviation REAL,
            inventory_label TEXT,
            structure_trend TEXT,
            regime TEXT NOT NULL,
            engine_cycle INTEGER,
            closed_bars INTEGER,
            reentry_active INTEGER NOT NULL DEFAULT 0,
            reentry_in_cooldown INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_cycle_metrics_ts ON cycle_metrics(ts);
        """
    )


def compute_atr_pct(candles: Sequence[CandleData], *, period: int = _ATR_PERIOD) -> Optional[float]:
    """Average true range as % of last close."""
    if len(candles) < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, len(candles)):
        cur = candles[i]
        prev = candles[i - 1]
        tr = max(
            cur.high - cur.low,
            abs(cur.high - prev.close),
            abs(cur.low - prev.close),
        )
        trs.append(max(0.0, tr))
    if len(trs) < period:
        return None
    atr = sum(trs[-period:]) / period
    close = candles[-1].close
    if close <= 0:
        return None
    return (atr / close) * 100.0


def compute_realized_vol_daily_pct(
    candles: Sequence[CandleData],
    *,
    interval_seconds: int,
    lookback: int = _REALIZED_VOL_LOOKBACK,
) -> Optional[float]:
    """Annualized-style daily vol from recent bar log returns."""
    if len(candles) < lookback + 1 or interval_seconds <= 0:
        return None
    closes = [c.close for c in candles[-(lookback + 1) :]]
    returns: List[float] = []
    for i in range(1, len(closes)):
        a, b = closes[i - 1], closes[i]
        if a <= 0 or b <= 0:
            continue
        returns.append(math.log(b / a))
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    stdev = math.sqrt(max(0.0, var))
    bars_per_day = 86_400.0 / float(interval_seconds)
    return stdev * math.sqrt(bars_per_day) * 100.0


def classify_regime(
    *,
    inventory_deviation: float,
    weakness_deviation: float,
    strength_deviation: float,
    structure_trend: str,
    reentry_in_cooldown: bool,
    reentry_exit_type: str,
    spread_pct: Optional[float],
    atr_pct: Optional[float],
    ta_bias: str,
    bid_depth_1pct: float,
    min_order_xrp: float,
) -> str:
    """Human-readable regime tag for HUD and reports."""
    if reentry_in_cooldown:
        et = (reentry_exit_type or "exit").lower()
        return f"cooldown_{et}" if et in ("tp", "sl") else "cooldown"

    if bid_depth_1pct > 0 and bid_depth_1pct < min_order_xrp * 2:
        return "low_liquidity"

    if inventory_deviation <= -weakness_deviation:
        return "rlusd_heavy_reload"
    if inventory_deviation >= strength_deviation:
        return "xrp_heavy_trim"

    trend = (structure_trend or "neutral").lower()
    atr = atr_pct or 0.0
    if trend == "bullish":
        return "bull_volatile" if atr >= 1.2 else "bull_grind"
    if trend == "bearish":
        return "bear_defensive"
    if (ta_bias or "").lower() == "bearish" and atr >= 1.0:
        return "bear_chop"

    if spread_pct is not None and spread_pct < 0.08:
        return "tight_spread"

    if abs(inventory_deviation) < weakness_deviation * 0.35:
        return "balanced"
    return "neutral"


def _trim_metrics(conn: sqlite3.Connection, *, now_ts: int) -> None:
    cutoff = now_ts - _METRICS_RETENTION_DAYS * 86_400
    conn.execute("DELETE FROM cycle_metrics WHERE ts < ?", (cutoff,))
    conn.execute(
        """
        DELETE FROM cycle_metrics
        WHERE ts NOT IN (
            SELECT ts FROM cycle_metrics ORDER BY ts DESC LIMIT ?
        )
        """,
        (_METRICS_MAX_ROWS,),
    )


def record_cycle_metrics(
    *,
    logs_dir,
    ta_interval_seconds: int,
    mid: Optional[float],
    spread_pct: Optional[float],
    bid_depth_xrp: Optional[float],
    ask_depth_xrp: Optional[float],
    bid_depth_1pct_xrp: Optional[float],
    ask_depth_1pct_xrp: Optional[float],
    inventory: "InventorySnapshot",
    structure: Optional["MarketStructureSnapshot"],
    ta: Optional["TechnicalAnalysisSnapshot"],
    reentry: "ReentrySnapshot",
    engine_cycle: int,
    weakness_deviation: float,
    strength_deviation: float,
    min_order_size_xrp: float,
    tick_ts: Optional[datetime] = None,
) -> None:
    """Append one cycle row (does not touch OHLC bar tables)."""
    ts = _utc_ts(tick_ts)
    candles = get_candles(int(ta_interval_seconds), logs_dir=logs_dir)
    atr = compute_atr_pct(candles)
    rv = compute_realized_vol_daily_pct(
        candles,
        interval_seconds=int(ta_interval_seconds),
    )
    bb_bw = ta.bb_bandwidth_pct if ta is not None else None
    ta_buy = ta.buy_score if ta is not None else None
    ta_bias = ta.bias if ta is not None else ""

    from alpha.decision.ohlc_cache import _closed_bar_count

    path = _db_path(logs_dir)
    with _connect(path) as conn:
        _init_schema(conn)
        _ensure_metrics_schema(conn)
        closed = _closed_bar_count(conn, int(ta_interval_seconds))
        regime = classify_regime(
            inventory_deviation=inventory.deviation,
            weakness_deviation=weakness_deviation,
            strength_deviation=strength_deviation,
            structure_trend=structure.trend if structure else "neutral",
            reentry_in_cooldown=reentry.in_cooldown,
            reentry_exit_type=reentry.exit_type.value if reentry.active else "",
            spread_pct=spread_pct,
            atr_pct=atr,
            ta_bias=ta_bias,
            bid_depth_1pct=float(bid_depth_1pct_xrp or 0.0),
            min_order_xrp=min_order_size_xrp,
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO cycle_metrics(
                ts, ts_utc, mid, spread_pct,
                bid_depth_xrp, ask_depth_xrp,
                bid_depth_1pct_xrp, ask_depth_1pct_xrp,
                atr_pct, realized_vol_daily_pct, bb_bandwidth_pct,
                ta_buy_score, ta_bias, inventory_deviation, inventory_label,
                structure_trend, regime, engine_cycle, closed_bars,
                reentry_active, reentry_in_cooldown
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                mid,
                spread_pct,
                bid_depth_xrp,
                ask_depth_xrp,
                bid_depth_1pct_xrp,
                ask_depth_1pct_xrp,
                atr,
                rv,
                bb_bw,
                ta_buy,
                ta_bias,
                inventory.deviation,
                inventory.label,
                structure.trend if structure else None,
                regime,
                int(engine_cycle),
                closed,
                1 if reentry.active else 0,
                1 if reentry.in_cooldown else 0,
            ),
        )
        _trim_metrics(conn, now_ts=ts)
        conn.commit()


def latest_metrics(logs_dir) -> Optional[Dict[str, Any]]:
    path = _db_path(logs_dir)
    if not path.is_file():
        return None
    with _connect(path) as conn:
        _ensure_metrics_schema(conn)
        row = conn.execute(
            """
            SELECT * FROM cycle_metrics ORDER BY ts DESC LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def metrics_summary(logs_dir, *, hours: float = 24.0) -> Dict[str, Any]:
    """Rolling summary for HUD."""
    path = _db_path(logs_dir)
    if not path.is_file():
        return {"rows": 0, "latest": None}
    cutoff = _utc_ts() - int(hours * 3600)
    with _connect(path) as conn:
        _ensure_metrics_schema(conn)
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM cycle_metrics WHERE ts >= ?",
            (cutoff,),
        ).fetchone()
        count = int(rows["n"]) if rows else 0
        avg = conn.execute(
            """
            SELECT
                AVG(atr_pct) AS atr_pct,
                AVG(realized_vol_daily_pct) AS realized_vol_daily_pct,
                AVG(spread_pct) AS spread_pct,
                AVG(bid_depth_1pct_xrp) AS bid_depth_1pct_xrp,
                AVG(ask_depth_1pct_xrp) AS ask_depth_1pct_xrp
            FROM cycle_metrics WHERE ts >= ?
            """,
            (cutoff,),
        ).fetchone()
        latest = latest_metrics(logs_dir)

    def _r(val: object, places: int = 4) -> Optional[float]:
        if val is None:
            return None
        try:
            return round(float(val), places)
        except (TypeError, ValueError):
            return None

    return {
        "rows_24h": count,
        "hours": hours,
        "avg_atr_pct": _r(avg["atr_pct"] if avg else None, 3),
        "avg_realized_vol_daily_pct": _r(avg["realized_vol_daily_pct"] if avg else None, 3),
        "avg_spread_pct": _r(avg["spread_pct"] if avg else None, 4),
        "avg_bid_depth_1pct_xrp": _r(avg["bid_depth_1pct_xrp"] if avg else None, 2),
        "avg_ask_depth_1pct_xrp": _r(avg["ask_depth_1pct_xrp"] if avg else None, 2),
        "latest": latest,
    }


def format_metrics_report(logs_dir, *, hours: float = 24.0) -> str:
    summary = metrics_summary(logs_dir, hours=hours)
    latest = summary.get("latest") or {}
    lines = [
        "=== Market metrics (SQLite) ===",
        f"window: last {hours:.0f}h",
        f"rows: {summary.get('rows_24h', 0)}",
        "",
        "24h averages:",
        f"  atr_pct: {summary.get('avg_atr_pct')}",
        f"  realized_vol_daily_pct: {summary.get('avg_realized_vol_daily_pct')}",
        f"  spread_pct: {summary.get('avg_spread_pct')}",
        f"  bid_depth_1pct_xrp: {summary.get('avg_bid_depth_1pct_xrp')}",
        f"  ask_depth_1pct_xrp: {summary.get('avg_ask_depth_1pct_xrp')}",
        "",
        "Latest cycle:",
    ]
    if not latest:
        lines.append("  (no rows yet)")
        return "\n".join(lines)
    for key in (
        "ts_utc",
        "regime",
        "mid",
        "atr_pct",
        "realized_vol_daily_pct",
        "bb_bandwidth_pct",
        "spread_pct",
        "bid_depth_1pct_xrp",
        "ask_depth_1pct_xrp",
        "inventory_deviation",
        "structure_trend",
        "closed_bars",
        "engine_cycle",
    ):
        lines.append(f"  {key}: {latest.get(key)}")
    return "\n".join(lines)
