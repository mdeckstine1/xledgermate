"""Higher-timeframe structure and breakout detection for trailing brackets."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Union

from alpha.decision.price_history import (
    PRICE_HISTORY_PATH,
    append_book_prices,
    book_prices_from_snapshot,
    build_candle_from_prices,
    effective_sample_seconds,
    load_mid_history,
    load_price_series,
    record_mid,
    resolve_book_price,
)

logger = logging.getLogger(__name__)

_HISTORY_PATH = PRICE_HISTORY_PATH
_MAX_SAMPLES = 120
_PRICE_EPS = 1e-9


@dataclass(frozen=True)
class CandleData:
    """
    OHLC candle for breakout confirmation on ``breakout_confirmation_tf``.

    Synthesized from book price samples (bid/ask/mid) when exchange candles are unavailable.
    """

    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return max(self.high - self.low, 0.0)

    @property
    def is_green(self) -> bool:
        return self.close > self.open + _PRICE_EPS

    @property
    def close_in_upper_half(self) -> bool:
        """Close sits in the upper half of the candle range (momentum confirmation)."""
        rng = self.range
        if rng <= _PRICE_EPS:
            return self.is_green
        return (self.close - self.low) / rng >= 0.5


@dataclass(frozen=True)
class MarketStructureSnapshot:
    """Lightweight structure view — rolling price stats for HTF breakout context."""

    mid: float  # reference price (structure_source; field name kept for HUD compat)
    sample_count: int
    mean_mid: float
    recent_high: float
    recent_low: float
    trend: str  # bullish | bearish | neutral
    breakout_up: bool
    breakout_down: bool
    summary: str
    swing_high: float = 0.0
    confirmation_candle: Optional[CandleData] = None


def breakout_lookback_samples(
    timeframe: str,
    cycle_seconds: int = 60,
    *,
    sample_interval_seconds: int = 0,
) -> int:
    """
    Map ``breakout_confirmation_tf`` to price-sample count.

    Uses ``sample_interval_seconds`` when sub-cycle book sampling is enabled.
    Examples (60s cycle, 15s samples): ``15m`` → 60 samples.
    """
    tf = (timeframe or "15m").strip().lower()
    cycle = effective_sample_seconds(cycle_seconds, sample_interval_seconds)

    if tf.isdigit():
        return max(1, int(tf))

    match = re.fullmatch(r"(\d+)([smhd])", tf)
    if not match:
        logger.warning("breakout_tf_unrecognized | tf=%s | default=15", timeframe)
        return max(1, 15 * 60 // cycle)

    value, unit = int(match.group(1)), match.group(2)
    seconds_map = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    total_seconds = value * seconds_map[unit]
    return max(1, total_seconds // cycle)


# Re-export for callers that imported from structure.
__all__ = [
    "CandleData",
    "MarketStructureSnapshot",
    "analyze_structure",
    "breakout_lookback_samples",
    "build_candle_from_mids",
    "build_confirmation_candle",
    "confirm_breakout",
    "load_mid_history",
    "record_mid",
]


def build_candle_from_mids(mids: Sequence[float]) -> Optional[CandleData]:
    """Build one OHLC candle from a price sample sequence (legacy name)."""
    return build_candle_from_prices(mids)


def build_confirmation_candle(
    price: float,
    *,
    timeframe: str = "15m",
    cycle_seconds: int = 60,
    sample_interval_seconds: int = 0,
    price_source: str = "ask",
    path: Path = _HISTORY_PATH,
) -> Optional[CandleData]:
    """Synthesize the current ``breakout_confirmation_tf`` candle from price history."""
    lookback = breakout_lookback_samples(
        timeframe,
        cycle_seconds,
        sample_interval_seconds=sample_interval_seconds,
    )
    history = load_price_series(price_source, path=path)
    window = history[-lookback:] if history else ([price] if price > 0 else [])
    return build_candle_from_prices(window)


def _average_body(candles: Sequence[CandleData]) -> float:
    bodies = [c.body for c in candles if c.body > _PRICE_EPS]
    if not bodies:
        return 0.0
    return sum(bodies) / len(bodies)


def is_strong_momentum_candle(
    candle: CandleData,
    *,
    prior_candles: Sequence[CandleData] = (),
    min_body_ratio: float = 1.25,
) -> bool:
    """
    Strong momentum: large green candle with close in upper half of range.

    ``large`` means body >= ``min_body_ratio`` × average prior candle body.
    """
    if not candle.is_green or not candle.close_in_upper_half:
        return False
    if not prior_candles:
        return (
            candle.is_green
            and candle.close_in_upper_half
            and candle.range > _PRICE_EPS
            and candle.body / candle.range >= 0.5
        )

    avg_body = _average_body(prior_candles)
    if avg_body <= _PRICE_EPS:
        return candle.body > _PRICE_EPS
    return candle.body >= avg_body * min_body_ratio


def recent_swing_high(
    mids: Sequence[float],
    *,
    exclude_last: bool = True,
) -> float:
    """Highest price in the lookback window (optionally excluding the current close)."""
    clean = [float(m) for m in mids if float(m) > 0]
    if not clean:
        return 0.0
    window = clean[:-1] if exclude_last and len(clean) > 1 else clean
    return max(window) if window else clean[-1]


def confirm_breakout(
    candle: CandleData,
    *,
    swing_high: float,
    prior_candles: Sequence[CandleData] = (),
    volume_ok: bool = True,
) -> bool:
    """
    Breakout confirmation (spec):

    - Close above recent swing high / key resistance
    - Strong momentum candle (green, large body, close in upper half)
    - Optional volume filter when ``volume_ok`` is False
    """
    if swing_high <= 0 or candle.close <= swing_high + _PRICE_EPS:
        return False
    if not volume_ok:
        return False
    if not is_strong_momentum_candle(candle, prior_candles=prior_candles):
        return False
    logger.info(
        "breakout_confirmed | close=%.6f | swing_high=%.6f | body=%.6f | green=%s",
        candle.close,
        swing_high,
        candle.body,
        candle.is_green,
    )
    return True


def analyze_structure(
    price: float,
    *,
    breakout_pct: float = 0.02,
    trend_threshold_pct: float = 0.008,
    lookback: int = 20,
    breakout_tf: str = "15m",
    cycle_seconds: int = 60,
    sample_interval_seconds: int = 0,
    price_source: str = "ask",
    path: Path = _HISTORY_PATH,
    book: Optional[object] = None,
    record_sample: bool = True,
) -> MarketStructureSnapshot:
    """Rolling price stats plus HTF confirmation candle for trailing breakout."""
    if record_sample and book is not None:
        append_book_prices(book_prices_from_snapshot(book), path=path)
        resolved = resolve_book_price(book_prices_from_snapshot(book), price_source)
        if resolved is not None:
            price = resolved

    history = load_price_series(price_source, path=path)
    window = history[-lookback:] if history else ([price] if price > 0 else [])
    tf_lookback = breakout_lookback_samples(
        breakout_tf,
        cycle_seconds,
        sample_interval_seconds=sample_interval_seconds,
    )
    tf_window = history[-tf_lookback:] if history else window
    confirmation_candle = build_candle_from_prices(tf_window) if tf_window else None
    swing_high = recent_swing_high(tf_window) if tf_window else price

    if not window:
        return MarketStructureSnapshot(
            mid=price,
            sample_count=0,
            mean_mid=price,
            recent_high=price,
            recent_low=price,
            trend="neutral",
            breakout_up=False,
            breakout_down=False,
            summary=f"no_price_history source={price_source}",
            swing_high=swing_high,
            confirmation_candle=confirmation_candle,
        )

    mean_price = sum(window) / len(window)
    recent_high = max(window)
    recent_low = min(window)
    trend = "neutral"
    if mean_price > 0:
        drift = (price - mean_price) / mean_price
        if drift >= trend_threshold_pct:
            trend = "bullish"
        elif drift <= -trend_threshold_pct:
            trend = "bearish"

    breakout_up = price >= recent_high * (1.0 + breakout_pct / 100.0) if recent_high > 0 else False
    breakout_down = price <= recent_low * (1.0 - breakout_pct / 100.0) if recent_low > 0 else False

    summary = (
        f"trend={trend} source={price_source} mean={mean_price:.6f} swing_high={swing_high:.6f} "
        f"breakout_up={breakout_up} breakout_down={breakout_down}"
    )
    logger.info("market_structure | %s", summary)

    return MarketStructureSnapshot(
        mid=price,
        sample_count=len(window),
        mean_mid=mean_price,
        recent_high=recent_high,
        recent_low=recent_low,
        trend=trend,
        breakout_up=breakout_up,
        breakout_down=breakout_down,
        summary=summary,
        swing_high=swing_high,
        confirmation_candle=confirmation_candle,
    )


def breakout_confirmed_for_long(
    structure: MarketStructureSnapshot,
    entry_price: float,
    *,
    min_breakout_pct: float = 0.02,
) -> bool:
    """Legacy helper — prefer ``confirm_breakout`` on ``confirmation_candle``."""
    if entry_price <= 0:
        return False
    if structure.breakout_up:
        return True
    return structure.mid >= entry_price * (1.0 + min_breakout_pct / 100.0)
