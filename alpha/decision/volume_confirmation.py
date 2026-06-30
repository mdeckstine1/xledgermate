"""Volume confirmation — tick-activity proxy on OHLC bars (real move vs noise)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from alpha.decision.structure import CandleData
from alpha.decision.ta_config import VolumeConfirmationConfig

_PRICE_EPS = 1e-9


@dataclass(frozen=True)
class VolumeConfirmationResult:
    fired: bool
    bias: str  # bullish | bearish | neutral
    ratio: float
    buy_contribution: float
    sell_contribution: float
    breakout_contribution: float
    score_dampen: float  # multiply buy/sell/breakout when low-activity chop
    detail: str

    def to_dict(self) -> dict:
        return {
            "fired": self.fired,
            "bias": self.bias,
            "ratio": round(self.ratio, 3),
            "buy_contribution": round(self.buy_contribution, 3),
            "sell_contribution": round(self.sell_contribution, 3),
            "breakout_contribution": round(self.breakout_contribution, 3),
            "score_dampen": round(self.score_dampen, 3),
            "detail": self.detail,
        }


def bar_volume(candle: CandleData) -> float:
    """Activity proxy: SQLite tick_count or synthetic bucket size."""
    vol = getattr(candle, "volume", None)
    if vol is not None and float(vol) > 0:
        return float(vol)
    return 1.0


def _closed_candles(candles: Sequence[CandleData]) -> List[CandleData]:
    return [c for c in candles if getattr(c, "is_complete", True)]


def evaluate_volume_confirmation(
    candles: Sequence[CandleData],
    cfg: VolumeConfirmationConfig,
) -> VolumeConfirmationResult:
    """Compare last closed bar activity to rolling average."""
    empty = VolumeConfirmationResult(
        fired=False,
        bias="neutral",
        ratio=0.0,
        buy_contribution=0.0,
        sell_contribution=0.0,
        breakout_contribution=0.0,
        score_dampen=1.0,
        detail="disabled",
    )
    if not cfg.enabled:
        return empty

    closed = _closed_candles(candles)
    need = max(3, int(cfg.lookback_bars) + 1)
    if len(closed) < need:
        return VolumeConfirmationResult(
            fired=False,
            bias="neutral",
            ratio=0.0,
            buy_contribution=0.0,
            sell_contribution=0.0,
            breakout_contribution=0.0,
            score_dampen=1.0,
            detail=f"warming_up bars={len(closed)}/{need}",
        )

    window = closed[-need:]
    prior = window[:-1]
    last = window[-1]
    avg_vol = sum(bar_volume(c) for c in prior) / max(len(prior), 1)
    last_vol = bar_volume(last)
    ratio = last_vol / max(avg_vol, _PRICE_EPS)

    strength = min(1.0, max(0.0, (ratio - 1.0) / max(cfg.min_spike_ratio - 1.0, _PRICE_EPS)))

    buy_contrib = sell_contrib = breakout_contrib = 0.0
    dampen = 1.0
    fired = False
    bias = "neutral"
    detail = f"vol_ratio={ratio:.2f} avg_ticks={avg_vol:.1f} last={last_vol:.1f}"

    if ratio >= cfg.min_spike_ratio:
        fired = True
        if last.is_green:
            bias = "bullish"
            buy_contrib = cfg.buy_weight * strength
            breakout_contrib = cfg.breakout_weight * strength
            detail += " spike_up"
        elif last.body > _PRICE_EPS:
            bias = "bearish"
            sell_contrib = cfg.sell_weight * strength
            detail += " spike_down"
        else:
            detail += " spike_doji"
    elif ratio <= cfg.low_volume_ratio:
        dampen = max(0.5, 1.0 - float(cfg.noise_penalty))
        detail += " low_vol_noise"

    return VolumeConfirmationResult(
        fired=fired,
        bias=bias,
        ratio=ratio,
        buy_contribution=buy_contrib,
        sell_contribution=sell_contrib,
        breakout_contribution=breakout_contrib,
        score_dampen=dampen,
        detail=detail,
    )
