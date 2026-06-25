"""Tests for SQLite OHLC cache and retention policy."""

from __future__ import annotations

from pathlib import Path

from alpha.decision.ohlc_cache import (
    cache_status,
    ensure_ohlc_cache,
    get_candles,
    rebuild_all_from_ticks,
    record_sample,
)
from alpha.decision.price_history import BookPrices, append_book_prices
from alpha.decision.retention_policy import (
    FIB_LOOKBACK_BARS,
    OHLC_BARS_PER_TF,
    indicator_warmup_status,
    max_tick_samples,
)


def _seed_ticks(path: Path, n: int = 200, base: float = 1.10) -> None:
    for i in range(n):
        p = base + i * 0.0001
        append_book_prices(BookPrices(bid=p - 0.001, ask=p, mid=p - 0.0005), path=path)


def test_record_sample_builds_candles(tmp_path: Path):
    logs = tmp_path
    for i in range(40):
        record_sample(1.10 + i * 0.001, logs_dir=logs, tick_ts=None)
    candles = get_candles(300, logs_dir=logs)
    assert len(candles) >= 1
    assert candles[0].open > 0


def test_rebuild_from_ticks_on_empty_db(tmp_path: Path):
    logs = tmp_path
    hist = logs / "alpha_price_history.json"
    _seed_ticks(hist, 120)
    counts = rebuild_all_from_ticks(
        logs_dir=logs,
        price_source="ask",
        history_path=hist,
        cycle_seconds=60,
        sample_interval_seconds=15,
    )
    assert counts[300] >= 2
    status = cache_status(logs, ta_interval_seconds=300)
    assert status["db_present"] is True
    assert status["closed_bars"] >= 1


def test_ensure_ohlc_cache_idempotent(tmp_path: Path):
    logs = tmp_path
    hist = logs / "alpha_price_history.json"
    _seed_ticks(hist, 80)
    ensure_ohlc_cache(
        logs,
        history_path=hist,
        cycle_seconds=60,
        sample_interval_seconds=15,
        ta_interval_seconds=300,
    )
    first = get_candles(300, logs_dir=logs)
    ensure_ohlc_cache(
        logs,
        history_path=hist,
        cycle_seconds=60,
        sample_interval_seconds=15,
        ta_interval_seconds=300,
    )
    second = get_candles(300, logs_dir=logs)
    assert len(second) == len(first)


def test_indicator_warmup_status():
    warm = indicator_warmup_status(20, interval_seconds=300)
    rsi = next(i for i in warm["indicators"] if i["name"] == "rsi")
    assert rsi["ready"] is True
    cold = indicator_warmup_status(5, interval_seconds=900)
    bb = next(i for i in cold["indicators"] if i["name"] == "bollinger")
    assert bb["ready"] is False
    assert bb["have"] == 5
    assert bb["need"] == 20


def test_retention_constants():
    assert OHLC_BARS_PER_TF >= FIB_LOOKBACK_BARS
    cap = max_tick_samples(cycle_seconds=60, sample_interval_seconds=15)
    assert cap >= 120


def test_custom_ta_interval_rebuild(tmp_path: Path):
    logs = tmp_path
    hist = logs / "alpha_price_history.json"
    _seed_ticks(hist, 500)
    ensure_ohlc_cache(
        logs,
        history_path=hist,
        cycle_seconds=60,
        sample_interval_seconds=15,
        ta_interval_seconds=6900,
    )
    candles = get_candles(6900, logs_dir=logs)
    assert len(candles) >= 2
