"""Retention limits for tick history and OHLC cache (max HUD/TA settings)."""

from __future__ import annotations

from alpha.decision.price_history import effective_sample_seconds
from alpha.decision.ta_config import (
    CHART_CANDLE_INTERVAL_OPTIONS_SECONDS,
    CHART_MAX_CANDLES,
    TA_CANDLE_INTERVAL_MAX_SECONDS,
)

# Longest indicator window in bars (Fibonacci).
FIB_LOOKBACK_BARS = 50

# Store enough bars for chart display and full Fib at any TF.
OHLC_BARS_PER_TF = max(CHART_MAX_CANDLES, FIB_LOOKBACK_BARS + 2)

# Standard TFs maintained in SQLite (HUD TA + live chart).
CACHED_INTERVALS_SECONDS: tuple[int, ...] = (300, 900, 1800, 3600, 7200, 9000)

OHLC_DB_PATH = "alpha_market.db"

# Indicator minimum closed bars (defaults from ta_config).
INDICATOR_MIN_BARS: dict[str, int] = {
    "rsi": 14,
    "stochastic": 20,
    "bollinger": 20,
    "fibonacci": 50,
    "elliott_wave": 50,
    "volume_confirmation": 21,
    "htf_bias": 21,
    "min_candles": 20,
}


def max_retention_seconds() -> int:
    """Wall-clock window covering widest TA + deepest chart view."""
    ta_wall = (FIB_LOOKBACK_BARS + 2) * int(TA_CANDLE_INTERVAL_MAX_SECONDS)
    chart_wall = int(CHART_MAX_CANDLES) * max(int(x) for x in CHART_CANDLE_INTERVAL_OPTIONS_SECONDS)
    return max(ta_wall, chart_wall)


def max_tick_samples(*, cycle_seconds: int, sample_interval_seconds: int) -> int:
    """Rolling tick cap for ``alpha_price_history.json``."""
    sample = effective_sample_seconds(cycle_seconds, sample_interval_seconds)
    return max(120, int(max_retention_seconds() / sample) + 1)


def indicator_warmup_status(
    closed_bars: int,
    *,
    interval_seconds: int,
) -> dict[str, object]:
    """Per-indicator readiness for HUD (bar count at active TF)."""
    rows = []
    for name, need in INDICATOR_MIN_BARS.items():
        rows.append(
            {
                "name": name,
                "need": need,
                "have": closed_bars,
                "ready": closed_bars >= need,
            }
        )
    return {
        "interval_seconds": int(interval_seconds),
        "closed_bars": int(closed_bars),
        "indicators": rows,
    }
