"""Higher-timeframe structure and breakout detection for trailing brackets."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)

_HISTORY_PATH = Path("logs/alpha_mid_history.json")
_MAX_SAMPLES = 120
_PRICE_EPS = 1e-9


@dataclass(frozen=True)
class CandleData:
    """
    OHLC candle for breakout confirmation on ``breakout_confirmation_tf``.

    Synthesized from mid-price samples when full exchange candles are unavailable.
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
    """Lightweight structure view — rolling mid stats for HTF breakout context."""

    mid: float
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


def breakout_lookback_samples(timeframe: str, cycle_seconds: int = 60) -> int:
    """
    Map ``breakout_confirmation_tf`` to mid-sample count.

    Examples (60s cycle): ``15m`` → 15, ``1h`` → 60, ``4h`` → 240.
    Bare integers are treated as sample counts.
    """
    tf = (timeframe or "15m").strip().lower()
    cycle = max(1, int(cycle_seconds))

    if tf.isdigit():
        return max(1, int(tf))

    match = re.fullmatch(r"(\d+)([smhd])", tf)
    if not match:
        logger.warning("breakout_tf_unrecognized | tf=%s | default=15", timeframe)
        return 15

    value, unit = int(match.group(1)), match.group(2)
    seconds_map = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    total_seconds = value * seconds_map[unit]
    return max(1, total_seconds // cycle)


def _load_history(path: Path = _HISTORY_PATH) -> List[float]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        samples = data.get("mids", [])
        return [float(x) for x in samples if float(x) > 0][-_MAX_SAMPLES:]
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return []


def _save_history(mids: List[float], path: Path = _HISTORY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mids": mids[-_MAX_SAMPLES:]}, indent=2), encoding="utf-8")


def record_mid(mid: float, *, path: Path = _HISTORY_PATH) -> None:
    if mid <= 0:
        return
    history = _load_history(path)
    history.append(mid)
    _save_history(history, path)


def build_candle_from_mids(mids: Sequence[float]) -> Optional[CandleData]:
    """Build one OHLC candle from a sequence of mid prices."""
    clean = [float(m) for m in mids if float(m) > 0]
    if len(clean) < 2:
        return None
    return CandleData(
        open=clean[0],
        high=max(clean),
        low=min(clean),
        close=clean[-1],
    )


def build_confirmation_candle(
    mid: float,
    *,
    timeframe: str = "15m",
    cycle_seconds: int = 60,
    path: Path = _HISTORY_PATH,
) -> Optional[CandleData]:
    """Synthesize the current ``breakout_confirmation_tf`` candle from mid history."""
    lookback = breakout_lookback_samples(timeframe, cycle_seconds)
    history = _load_history(path)
    if mid > 0:
        history = (history + [mid])[-_MAX_SAMPLES:]
    window = history[-lookback:] if history else ([mid] if mid > 0 else [])
    return build_candle_from_mids(window)


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
    mid: float,
    *,
    breakout_pct: float = 0.02,
    trend_threshold_pct: float = 0.008,
    lookback: int = 20,
    breakout_tf: str = "15m",
    cycle_seconds: int = 60,
    path: Path = _HISTORY_PATH,
) -> MarketStructureSnapshot:
    """Rolling mid stats plus HTF confirmation candle for trailing breakout."""
    history = _load_history(path)
    if mid > 0:
        history = (history + [mid])[-_MAX_SAMPLES:]
        _save_history(history, path)

    window = history[-lookback:] if history else ([mid] if mid > 0 else [])
    tf_lookback = breakout_lookback_samples(breakout_tf, cycle_seconds)
    tf_window = history[-tf_lookback:] if history else window
    confirmation_candle = build_candle_from_mids(tf_window) if tf_window else None
    swing_high = recent_swing_high(tf_window) if tf_window else mid

    if not window:
        return MarketStructureSnapshot(
            mid=mid,
            sample_count=0,
            mean_mid=mid,
            recent_high=mid,
            recent_low=mid,
            trend="neutral",
            breakout_up=False,
            breakout_down=False,
            summary="no_mid_history",
            swing_high=swing_high,
            confirmation_candle=confirmation_candle,
        )

    mean_mid = sum(window) / len(window)
    recent_high = max(window)
    recent_low = min(window)
    trend = "neutral"
    if mean_mid > 0:
        drift = (mid - mean_mid) / mean_mid
        if drift >= trend_threshold_pct:
            trend = "bullish"
        elif drift <= -trend_threshold_pct:
            trend = "bearish"

    breakout_up = mid >= recent_high * (1.0 + breakout_pct / 100.0) if recent_high > 0 else False
    breakout_down = mid <= recent_low * (1.0 - breakout_pct / 100.0) if recent_low > 0 else False

    summary = (
        f"trend={trend} mean={mean_mid:.6f} swing_high={swing_high:.6f} "
        f"breakout_up={breakout_up} breakout_down={breakout_down}"
    )
    logger.info("market_structure | %s", summary)

    return MarketStructureSnapshot(
        mid=mid,
        sample_count=len(window),
        mean_mid=mean_mid,
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
