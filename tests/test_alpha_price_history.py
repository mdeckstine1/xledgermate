"""Tests for Alpha multi-series price history."""

from __future__ import annotations

from pathlib import Path

from alpha.decision.price_history import (
    BookPrices,
    append_book_prices,
    load_mid_history,
    load_price_series,
    resolve_book_price,
)
from alpha.decision.structure import analyze_structure, breakout_lookback_samples


def test_append_and_load_price_series(tmp_path: Path):
    path = tmp_path / "alpha_price_history.json"
    append_book_prices(BookPrices(bid=1.10, ask=1.12, mid=1.11), path=path)
    append_book_prices(BookPrices(bid=1.11, ask=1.13, mid=1.12), path=path)
    assert load_price_series("ask", path=path) == [1.12, 1.13]
    assert load_price_series("bid", path=path) == [1.10, 1.11]
    assert load_price_series("mid", path=path) == [1.11, 1.12]


def test_resolve_book_price_directional():
    prices = BookPrices(bid=1.10, ask=1.12, mid=1.11)
    assert resolve_book_price(prices, "ask") == 1.12
    assert resolve_book_price(prices, "bid") == 1.10
    assert resolve_book_price(prices, "mid") == 1.11


def test_breakout_lookback_uses_sample_interval():
    # 15m at 15s samples => 60 points (not 15)
    assert breakout_lookback_samples("15m", 60, sample_interval_seconds=15) == 60
    assert breakout_lookback_samples("15m", 60, sample_interval_seconds=0) == 15


def test_structure_uses_ask_series(tmp_path: Path):
    path = tmp_path / "alpha_price_history.json"
    append_book_prices(BookPrices(bid=1.10, ask=1.20, mid=1.15), path=path)
    append_book_prices(BookPrices(bid=1.10, ask=1.22, mid=1.16), path=path)
    snap = analyze_structure(
        1.22,
        lookback=2,
        path=path,
        record_sample=False,
        price_source="ask",
    )
    assert snap.mid == 1.22
    assert "source=ask" in snap.summary


def test_load_mid_history_compat(tmp_path: Path):
    path = tmp_path / "alpha_price_history.json"
    append_book_prices(BookPrices(bid=1.0, ask=1.0, mid=1.05), path=path)
    assert load_mid_history(path) == [1.05]
