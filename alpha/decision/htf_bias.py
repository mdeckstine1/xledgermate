"""Higher-timeframe bias — light SMA trend filter for LTF TA scores."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from alpha.decision.retention_policy import CACHED_INTERVALS_SECONDS
from alpha.decision.structure import CandleData
from alpha.decision.ta_config import HtfBiasConfig

_PRICE_EPS = 1e-9


@dataclass(frozen=True)
class HtfBiasResult:
    bias: str  # bullish | bearish | neutral
    interval_seconds: int
    strength: float
    buy_multiplier: float
    sell_multiplier: float
    breakout_multiplier: float
    detail: str

    def to_dict(self) -> dict:
        return {
            "bias": self.bias,
            "interval_seconds": self.interval_seconds,
            "strength": round(self.strength, 3),
            "buy_multiplier": round(self.buy_multiplier, 3),
            "sell_multiplier": round(self.sell_multiplier, 3),
            "breakout_multiplier": round(self.breakout_multiplier, 3),
            "detail": self.detail,
        }


def resolve_htf_interval_seconds(
    cfg: HtfBiasConfig,
    *,
    ltf_interval_seconds: int,
) -> int:
    """Pick HTF bar width strictly above LTF when possible."""
    want = max(1, int(cfg.interval_seconds))
    ltf = max(1, int(ltf_interval_seconds))
    if want > ltf:
        return want
    for sec in CACHED_INTERVALS_SECONDS:
        if sec > ltf:
            return max(sec, want)
    return want


def _sma(values: Sequence[float], period: int) -> Optional[float]:
    if period < 1 or len(values) < period:
        return None
    chunk = values[-period:]
    return sum(chunk) / len(chunk)


def _closed_candles(candles: Sequence[CandleData]) -> List[CandleData]:
    return [c for c in candles if getattr(c, "is_complete", True)]


def evaluate_htf_bias(
    htf_candles: Sequence[CandleData],
    cfg: HtfBiasConfig,
    *,
    interval_seconds: int,
) -> HtfBiasResult:
    """Light trend anchor: fast/slow SMA stack on HTF closes."""
    neutral = HtfBiasResult(
        bias="neutral",
        interval_seconds=interval_seconds,
        strength=0.0,
        buy_multiplier=1.0,
        sell_multiplier=1.0,
        breakout_multiplier=1.0,
        detail="disabled",
    )
    if not cfg.enabled:
        return neutral

    closed = _closed_candles(htf_candles)
    need = max(int(cfg.min_closed_bars), int(cfg.slow_sma) + 2)
    if len(closed) < need:
        return HtfBiasResult(
            bias="neutral",
            interval_seconds=interval_seconds,
            strength=0.0,
            buy_multiplier=1.0,
            sell_multiplier=1.0,
            breakout_multiplier=1.0,
            detail=f"warming_up bars={len(closed)}/{need}",
        )

    closes = [c.close for c in closed]
    fast = _sma(closes, int(cfg.fast_sma))
    slow = _sma(closes, int(cfg.slow_sma))
    if fast is None or slow is None or slow <= _PRICE_EPS:
        return HtfBiasResult(
            bias="neutral",
            interval_seconds=interval_seconds,
            strength=0.0,
            buy_multiplier=1.0,
            sell_multiplier=1.0,
            breakout_multiplier=1.0,
            detail="sma_unavailable",
        )

    last_close = closes[-1]
    sep_pct = abs(fast - slow) / slow * 100.0
    strength = min(1.0, sep_pct / max(float(cfg.trend_sep_pct), _PRICE_EPS))

    bullish = last_close >= slow and fast >= slow
    bearish = last_close <= slow and fast <= slow

    if bullish and not bearish:
        bias = "bullish"
        buy_mult = 1.0 + float(cfg.buy_align_boost) * strength
        sell_mult = max(0.7, 1.0 - float(cfg.counter_trend_dampen) * strength)
        brk_mult = 1.0 + float(cfg.breakout_align_boost) * strength
        detail = f"HTF{interval_seconds}s bull close={last_close:.6f} fast={fast:.6f} slow={slow:.6f}"
    elif bearish and not bullish:
        bias = "bearish"
        sell_mult = 1.0 + float(cfg.sell_align_boost) * strength
        buy_mult = max(0.7, 1.0 - float(cfg.counter_trend_dampen) * strength)
        brk_mult = max(0.75, 1.0 - float(cfg.counter_trend_dampen) * 0.5 * strength)
        detail = f"HTF{interval_seconds}s bear close={last_close:.6f} fast={fast:.6f} slow={slow:.6f}"
    else:
        bias = "neutral"
        buy_mult = sell_mult = brk_mult = 1.0
        detail = f"HTF{interval_seconds}s mix close={last_close:.6f} fast={fast:.6f} slow={slow:.6f}"

    return HtfBiasResult(
        bias=bias,
        interval_seconds=interval_seconds,
        strength=strength,
        buy_multiplier=buy_mult,
        sell_multiplier=sell_mult,
        breakout_multiplier=brk_mult,
        detail=detail,
    )
