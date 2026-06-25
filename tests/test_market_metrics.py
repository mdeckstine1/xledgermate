"""Tests for per-cycle market metrics (SQLite)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha.decision.market_metrics import (
    classify_regime,
    compute_atr_pct,
    compute_realized_vol_daily_pct,
    format_metrics_report,
    latest_metrics,
    metrics_summary,
    record_cycle_metrics,
)
from alpha.decision.ohlc_cache import cache_status, record_sample
from alpha.decision.reentry import ReentryGate
from alpha.decision.structure import CandleData
from alpha.types import InventorySnapshot


def _candles(n: int, base: float = 1.0, step: float = 0.002) -> list[CandleData]:
    out: list[CandleData] = []
    price = base
    for _ in range(n):
        out.append(
            CandleData(
                open=price,
                high=price + step,
                low=price - step * 0.5,
                close=price + step * 0.25,
            )
        )
        price += step * 0.1
    return out


def test_compute_atr_and_realized_vol():
    candles = _candles(60)
    atr = compute_atr_pct(candles, period=14)
    rv = compute_realized_vol_daily_pct(candles, interval_seconds=300, lookback=48)
    assert atr is not None and atr > 0
    assert rv is not None and rv > 0


def test_classify_regime_cooldown_and_inventory():
    assert classify_regime(
        inventory_deviation=-0.05,
        weakness_deviation=0.02,
        strength_deviation=0.04,
        structure_trend="neutral",
        reentry_in_cooldown=True,
        reentry_exit_type="sl",
        spread_pct=0.12,
        atr_pct=0.5,
        ta_bias="neutral",
        bid_depth_1pct=100.0,
        min_order_xrp=10.0,
    ) == "cooldown_sl"
    assert classify_regime(
        inventory_deviation=-0.05,
        weakness_deviation=0.02,
        strength_deviation=0.04,
        structure_trend="bullish",
        reentry_in_cooldown=False,
        reentry_exit_type="",
        spread_pct=0.12,
        atr_pct=0.5,
        ta_bias="bullish",
        bid_depth_1pct=100.0,
        min_order_xrp=10.0,
    ) == "rlusd_heavy_reload"


def test_record_cycle_metrics_and_ohlc_independent(tmp_path: Path):
    logs = tmp_path
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(100):
        record_sample(1.10 + i * 0.0005, logs_dir=logs, tick_ts=base + timedelta(minutes=i))

    before = cache_status(logs, ta_interval_seconds=300)
    closed_before = before["closed_bars"]

    inv = InventorySnapshot(
        xrp_ratio=0.64,
        target_xrp_ratio=0.75,
        deviation=-0.11,
        label="rlusd_heavy",
        pause_bids=False,
        pause_asks=False,
        summary="test",
    )
    gate = ReentryGate(
        __import__("config.settings", fromlist=["BotConfig"]).BotConfig(),
        persist_path=logs / "reentry.json",
    )
    record_cycle_metrics(
        logs_dir=logs,
        ta_interval_seconds=300,
        mid=1.12,
        spread_pct=0.13,
        bid_depth_xrp=5000.0,
        ask_depth_xrp=8000.0,
        bid_depth_1pct_xrp=1200.0,
        ask_depth_1pct_xrp=2000.0,
        inventory=inv,
        structure=None,
        ta=None,
        reentry=gate.snapshot,
        engine_cycle=42,
        weakness_deviation=0.02,
        strength_deviation=0.04,
        min_order_size_xrp=10.0,
    )

    latest = latest_metrics(logs)
    assert latest is not None
    assert latest["engine_cycle"] == 42
    assert latest["regime"] == "rlusd_heavy_reload"
    assert latest["closed_bars"] >= closed_before

    after = cache_status(logs, ta_interval_seconds=300)
    assert after["closed_bars"] >= closed_before

    summary = metrics_summary(logs, hours=24.0)
    assert summary["rows_24h"] >= 1
    report = format_metrics_report(logs)
    assert "Market metrics" in report
    assert "regime" in report
