"""Technical analysis for Trading Bot Alpha — scoring + rule-based signals from mid history."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from alpha.decision.structure import CandleData, build_candle_from_mids
from alpha.decision.ta_config import (
    AlphaTechnicalAnalysisConfig,
    resolve_ta_candle_bucket_samples,
    ta_warmup_tick_threshold,
)
from config.settings import BotConfig

logger = logging.getLogger(__name__)

try:
    import pandas_ta as pta  # type: ignore[import-untyped]

    _HAS_PANDAS_TA = True
except ImportError:
    pta = None  # type: ignore[assignment]
    _HAS_PANDAS_TA = False

_PRICE_EPS = 1e-9


def _finite_float(value: object) -> Optional[float]:
    """Return finite floats only — NaN/inf break strict JSON (HUD / Python 3.14+)."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _series_last(series: pd.Series) -> Optional[float]:
    if series is None or series.empty:
        return None
    return _finite_float(series.iloc[-1])


@dataclass(frozen=True)
class TechnicalSignal:
    name: str
    enabled: bool
    fired: bool
    bias: str  # bullish | bearish | neutral
    score: float
    detail: str


@dataclass(frozen=True)
class TechnicalAnalysisSnapshot:
    mid: float
    enabled: bool
    buy_score: float
    sell_score: float
    breakout_score: float
    bias: str
    entry_buy_allowed: bool
    entry_sell_allowed: bool
    breakout_confirmed: bool
    signals: Tuple[TechnicalSignal, ...] = ()
    summary: str = ""
    rsi: Optional[float] = None
    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    bb_bandwidth_pct: Optional[float] = None
    fib_levels: Dict[str, float] = field(default_factory=dict)
    elliott_bias: str = "neutral"
    elliott_phase: str = "neutral"
    elliott_trend: str = "neutral"
    elliott_wave_label: str = ""
    elliott_confidence: float = 0.0
    elliott_detail: str = ""
    divergence_bias: str = "neutral"
    divergence_fired: bool = False
    divergence_kind: str = ""
    divergence_indicator: str = ""
    divergence_strength: float = 0.0
    divergence_detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "mid": _finite_float(self.mid) or 0.0,
            "buy_score": _finite_float(self.buy_score) or 0.0,
            "sell_score": _finite_float(self.sell_score) or 0.0,
            "breakout_score": _finite_float(self.breakout_score) or 0.0,
            "bias": self.bias,
            "entry_buy_allowed": self.entry_buy_allowed,
            "entry_sell_allowed": self.entry_sell_allowed,
            "breakout_confirmed": self.breakout_confirmed,
            "summary": self.summary,
            "rsi": _finite_float(self.rsi),
            "stoch_k": _finite_float(self.stoch_k),
            "stoch_d": _finite_float(self.stoch_d),
            "bb_upper": _finite_float(self.bb_upper),
            "bb_middle": _finite_float(self.bb_middle),
            "bb_lower": _finite_float(self.bb_lower),
            "bb_bandwidth_pct": _finite_float(self.bb_bandwidth_pct),
            "fib_levels": {
                k: v for k, v in self.fib_levels.items() if _finite_float(v) is not None
            },
            "elliott_bias": self.elliott_bias,
            "elliott_phase": self.elliott_phase,
            "elliott_trend": self.elliott_trend,
            "elliott_wave_label": self.elliott_wave_label,
            "elliott_confidence": _finite_float(self.elliott_confidence) or 0.0,
            "elliott_detail": self.elliott_detail,
            "divergence_bias": self.divergence_bias,
            "divergence_fired": self.divergence_fired,
            "divergence_kind": self.divergence_kind,
            "divergence_indicator": self.divergence_indicator,
            "divergence_strength": _finite_float(self.divergence_strength) or 0.0,
            "divergence_detail": self.divergence_detail,
            "signals": [
                {
                    "name": s.name,
                    "enabled": s.enabled,
                    "fired": s.fired,
                    "bias": s.bias,
                    "score": _finite_float(s.score) or 0.0,
                    "detail": s.detail,
                }
                for s in self.signals
            ],
        }


def _empty_snapshot(mid: float, *, reason: str, enabled: bool = False) -> TechnicalAnalysisSnapshot:
    return TechnicalAnalysisSnapshot(
        mid=mid,
        enabled=enabled,
        buy_score=0.0,
        sell_score=0.0,
        breakout_score=0.0,
        bias="neutral",
        entry_buy_allowed=True,
        entry_sell_allowed=True,
        breakout_confirmed=False,
        summary=reason,
        elliott_phase="neutral",
        elliott_trend="neutral",
        elliott_wave_label="",
        elliott_confidence=0.0,
        elliott_detail="",
    )


def mids_to_candles(mids: Sequence[float], *, bucket: int) -> List[CandleData]:
    clean = [float(m) for m in mids if float(m) > 0]
    if bucket < 1:
        bucket = 1
    candles: List[CandleData] = []
    for i in range(0, len(clean), bucket):
        c = build_candle_from_mids(clean[i : i + bucket])
        if c is not None:
            candles.append(c)
    return candles


def _candles_to_df(candles: Sequence[CandleData]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
        }
    )


def _rsi_series(close: pd.Series, period: int) -> pd.Series:
    if _HAS_PANDAS_TA and pta is not None:
        out = pta.rsi(close, length=period)
        if out is not None:
            return out
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, _PRICE_EPS)
    return 100 - (100 / (1 + rs))


def _stoch_series(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    k_period: int,
    d_period: int,
    smooth_k: int,
) -> Tuple[pd.Series, pd.Series]:
    if _HAS_PANDAS_TA and pta is not None:
        st = pta.stoch(high, low, close, k=k_period, d=d_period, smooth_k=smooth_k)
        if st is not None and not st.empty:
            cols = list(st.columns)
            k_col = next((c for c in cols if "STOCHk" in c.upper() or c.upper().endswith("_K")), cols[0])
            d_col = next((c for c in cols if "STOCHd" in c.upper() or c.upper().endswith("_D")), cols[-1])
            return st[k_col], st[d_col]
    lowest = low.rolling(k_period).min()
    highest = high.rolling(k_period).max()
    raw_k = 100 * (close - lowest) / (highest - lowest).replace(0, _PRICE_EPS)
    k = raw_k.rolling(smooth_k).mean()
    d = k.rolling(d_period).mean()
    return k, d


def _bollinger(
    close: pd.Series,
    *,
    period: int,
    std_dev: float,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    if _HAS_PANDAS_TA and pta is not None:
        bb = pta.bbands(close, length=period, std=std_dev)
        if bb is not None and not bb.empty:
            lower = bb[[c for c in bb.columns if c.startswith("BBL")][0]]
            mid = bb[[c for c in bb.columns if c.startswith("BBM")][0]]
            upper = bb[[c for c in bb.columns if c.startswith("BBU")][0]]
            return lower, mid, upper
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return lower, mid, upper


def _fib_levels(high: float, low: float, levels: Sequence[float]) -> Dict[str, float]:
    span = high - low
    if span <= _PRICE_EPS:
        return {}
    return {f"{lvl:.3f}": high - span * lvl for lvl in levels}


def _near_level(price: float, level: float, proximity_pct: float) -> bool:
    if level <= 0:
        return False
    return abs(price - level) / level * 100.0 <= proximity_pct


def _green_streak(candles: Sequence[CandleData]) -> int:
    n = 0
    for c in reversed(candles):
        if c.is_green:
            n += 1
        else:
            break
    return n


def _red_streak(candles: Sequence[CandleData]) -> int:
    n = 0
    for c in reversed(candles):
        if not c.is_green and c.body > _PRICE_EPS:
            n += 1
        else:
            break
    return n


def _is_consolidation(candles: Sequence[CandleData], max_band_pct: float) -> bool:
    if len(candles) < 3:
        return False
    window = candles[-len(candles) :]
    hi = max(c.high for c in window)
    lo = min(c.low for c in window)
    mid = (hi + lo) / 2.0
    if mid <= 0:
        return False
    return ((hi - lo) / mid) * 100.0 <= max_band_pct


def _bullish_pin_bar(c: CandleData, min_ratio: float) -> bool:
    body = max(c.body, _PRICE_EPS)
    lower_wick = min(c.open, c.close) - c.low
    upper_wick = c.high - max(c.open, c.close)
    return lower_wick / body >= min_ratio and lower_wick > upper_wick


def _bearish_pin_bar(c: CandleData, min_ratio: float) -> bool:
    body = max(c.body, _PRICE_EPS)
    lower_wick = min(c.open, c.close) - c.low
    upper_wick = c.high - max(c.open, c.close)
    return upper_wick / body >= min_ratio and upper_wick > lower_wick


def _bullish_engulfing(prev: CandleData, cur: CandleData) -> bool:
    return (
        cur.is_green
        and not prev.is_green
        and cur.open <= prev.close
        and cur.close >= prev.open
    )


def _bearish_engulfing(prev: CandleData, cur: CandleData) -> bool:
    return (
        not cur.is_green
        and prev.is_green
        and cur.open >= prev.close
        and cur.close <= prev.open
    )


def _inside_bar(prev: CandleData, cur: CandleData) -> bool:
    return cur.high <= prev.high and cur.low >= prev.low


def _higher_highs_lower_lows(candles: Sequence[CandleData], lookback: int) -> str:
    window = candles[-lookback:]
    if len(window) < 4:
        return "neutral"
    highs = [c.high for c in window]
    lows = [c.low for c in window]
    hh = sum(1 for i in range(1, len(highs)) if highs[i] > highs[i - 1])
    ll = sum(1 for i in range(1, len(lows)) if lows[i] < lows[i - 1])
    hl = sum(1 for i in range(1, len(lows)) if lows[i] > lows[i - 1])
    lh = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i - 1])
    if hh >= 2 and hl >= 2:
        return "bullish"
    if ll >= 2 and lh >= 2:
        return "bearish"
    return "neutral"


def _order_block_zone(candles: Sequence[CandleData], lookback: int) -> Tuple[Optional[float], Optional[float]]:
    window = candles[-lookback:]
    if len(window) < 3:
        return None, None
    bull_ob = None
    bear_ob = None
    for i in range(1, len(window)):
        prev, cur = window[i - 1], window[i]
        if cur.is_green and not prev.is_green and cur.close > prev.high:
            bull_ob = (prev.low + prev.high) / 2.0
        if not cur.is_green and prev.is_green and cur.close < prev.low:
            bear_ob = (prev.low + prev.high) / 2.0
    return bull_ob, bear_ob


def _bullish_fvg(candles: Sequence[CandleData], min_gap_pct: float) -> bool:
    if len(candles) < 3:
        return False
    c0, c2 = candles[-3], candles[-1]
    gap = c0.high
    if c2.low <= gap:
        return False
    mid = (c0.high + c2.low) / 2.0
    if mid <= 0:
        return False
    return ((c2.low - c0.high) / mid) * 100.0 >= min_gap_pct


def _liquidity_grab_buy(candles: Sequence[CandleData], lookback: int, wick_pct: float) -> bool:
    window = candles[-lookback:]
    if len(window) < 3:
        return False
    cur = window[-1]
    swing_low = min(c.low for c in window[:-1])
    if swing_low <= 0:
        return False
    pierced = cur.low < swing_low * (1.0 - wick_pct / 100.0)
    reclaimed = cur.close > swing_low
    return pierced and reclaimed and cur.is_green


def _liquidity_grab_sell(candles: Sequence[CandleData], lookback: int, wick_pct: float) -> bool:
    window = candles[-lookback:]
    if len(window) < 3:
        return False
    cur = window[-1]
    swing_high = max(c.high for c in window[:-1])
    if swing_high <= 0:
        return False
    pierced = cur.high > swing_high * (1.0 + wick_pct / 100.0)
    reclaimed = cur.close < swing_high
    return pierced and reclaimed and not cur.is_green


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _graded_below(
    value: float,
    *,
    center: float,
    threshold: float,
    weight: float,
) -> Tuple[float, bool]:
    """Bullish partial credit as value falls from center toward threshold; full weight at/below threshold."""
    fired = value < threshold
    if value <= threshold:
        return weight, fired
    if value >= center:
        return 0.0, False
    span = max(center - threshold, _PRICE_EPS)
    return weight * (center - value) / span, False


def _graded_above(
    value: float,
    *,
    center: float,
    threshold: float,
    weight: float,
) -> Tuple[float, bool]:
    """Bearish partial credit as value rises from center toward threshold; full weight at/above threshold."""
    fired = value > threshold
    if value >= threshold:
        return weight, fired
    if value <= center:
        return 0.0, False
    span = max(threshold - center, _PRICE_EPS)
    return weight * (value - center) / span, False


def _stoch_graded_scores(
    k: float,
    d: float,
    *,
    oversold: float,
    overbought: float,
    buy_weight: float,
    sell_weight: float,
) -> Tuple[float, float, bool]:
    buy, _ = _graded_below(k, center=50.0, threshold=oversold, weight=buy_weight)
    sell, _ = _graded_above(k, center=50.0, threshold=overbought, weight=sell_weight)
    if k < 50.0 and k <= d:
        buy *= 0.5
    if k > 50.0 and k >= d:
        sell *= 0.5
    strict_buy = k < oversold and k > d
    strict_sell = k > overbought and k < d
    if strict_buy:
        buy = buy_weight
    if strict_sell:
        sell = sell_weight
    return buy, sell, strict_buy or strict_sell


def _bb_graded_scores(
    price: float,
    lower: float,
    mid: float,
    upper: float,
    *,
    buy_weight: float,
    sell_weight: float,
    breakout_weight: float,
) -> Tuple[float, float, float, bool, str]:
    """Continuous %B position plus breakout credit; fired only on band pierce."""
    span = upper - lower
    if span <= _PRICE_EPS:
        return 0.0, 0.0, 0.0, False, "neutral"
    pct_b = (price - lower) / span
    if price >= upper:
        return buy_weight * 0.5, 0.0, breakout_weight, True, "bullish"
    if price <= lower:
        return 0.0, sell_weight, 0.0, True, "bearish"
    buy = sell = 0.0
    if pct_b < 0.5:
        buy = buy_weight * (0.5 - pct_b)
    elif pct_b > 0.5:
        sell = sell_weight * (pct_b - 0.5)
    bias = "bullish" if buy > sell + 0.05 else ("bearish" if sell > buy + 0.05 else "neutral")
    return buy, sell, 0.0, False, bias


def _nearest_fib_distance_pct(
    price: float,
    levels: Dict[str, float],
) -> Tuple[Optional[float], Optional[str]]:
    best_dist: Optional[float] = None
    best_side: Optional[str] = None
    for lvl in levels.values():
        if lvl <= 0:
            continue
        dist = abs(price - lvl) / lvl * 100.0
        side = "support" if lvl <= price else "resist"
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_side = side
    return best_dist, best_side


def _fib_graded_scores(
    price: float,
    fib: Dict[str, float],
    *,
    proximity_pct: float,
    buy_weight: float,
    sell_weight: float,
) -> Tuple[float, float, bool]:
    support_hit = any(_near_level(price, lvl, proximity_pct) for lvl in fib.values() if lvl <= price)
    resist_hit = any(_near_level(price, lvl, proximity_pct) for lvl in fib.values() if lvl >= price)
    fired = support_hit or resist_hit
    if support_hit:
        return buy_weight, 0.0, True
    if resist_hit:
        return 0.0, sell_weight, True
    dist, side = _nearest_fib_distance_pct(price, fib)
    if dist is None or proximity_pct <= 0:
        return 0.0, 0.0, False
    frac = _clamp01(1.0 - dist / (proximity_pct * 2.0))
    if side == "support":
        return buy_weight * frac * 0.6, 0.0, False
    if side == "resist":
        return 0.0, sell_weight * frac * 0.6, False
    return 0.0, 0.0, False


def _streak_graded_scores(
    greens: int,
    reds: int,
    *,
    min_green: int,
    min_red: int,
    buy_weight: float,
    sell_weight: float,
) -> Tuple[float, float, bool]:
    fired = greens >= min_green or reds >= min_red
    buy = buy_weight * _clamp01(greens / max(min_green, 1)) if greens > 0 else 0.0
    sell = sell_weight * _clamp01(reds / max(min_red, 1)) if reds > 0 else 0.0
    if greens >= min_green:
        buy = buy_weight
    if reds >= min_red:
        sell = sell_weight
    return buy, sell, fired


def _pattern_candles(candles: Sequence[CandleData]) -> List[CandleData]:
    """Closed bars only — pin/engulf/inside on a forming bar are noise."""
    if not candles:
        return []
    if getattr(candles[-1], "is_complete", True):
        return list(candles)
    return list(candles[:-1]) if len(candles) > 1 else []


def _closed_bar_count(candles: Sequence[CandleData]) -> int:
    return sum(1 for c in candles if getattr(c, "is_complete", True))


class TechnicalAnalysis:
    """Compute TA snapshot from mid-price history (synthetic OHLC candles)."""

    def __init__(self, config: BotConfig) -> None:
        self._bot_config = config
        self._cfg: AlphaTechnicalAnalysisConfig = config.alpha_technical_analysis

    @property
    def cfg(self) -> AlphaTechnicalAnalysisConfig:
        return self._cfg

    def analyze(
        self,
        mids: Sequence[float],
        *,
        mid: Optional[float] = None,
        candles: Optional[Sequence[CandleData]] = None,
    ) -> TechnicalAnalysisSnapshot:
        price = float(mid if mid is not None else (mids[-1] if mids else 0.0))
        if not self._cfg.enabled:
            return _empty_snapshot(price, reason="ta_disabled", enabled=False)

        tick_count = len([float(m) for m in mids if float(m) > 0])
        need_ticks = ta_warmup_tick_threshold(
            self._cfg,
            cycle_seconds=self._bot_config.alpha_cycle_interval_seconds,
            sample_interval_seconds=self._bot_config.alpha_price_sample_interval_seconds,
        )
        if tick_count < need_ticks:
            return _empty_snapshot(
                price,
                reason=f"ta_insufficient_ticks have={tick_count} need={need_ticks}",
                enabled=True,
            )

        if candles and len(candles) >= 2:
            candle_list = list(candles)
        else:
            candle_list = mids_to_candles(
                mids,
                bucket=resolve_ta_candle_bucket_samples(
                    self._cfg,
                    cycle_seconds=self._bot_config.alpha_cycle_interval_seconds,
                    sample_interval_seconds=self._bot_config.alpha_price_sample_interval_seconds,
                ),
            )
        candles = candle_list
        if len(candles) < 2:
            return _empty_snapshot(
                price,
                reason=f"ta_insufficient_candles have={len(candles)} need=2",
                enabled=True,
            )

        df = _candles_to_df(candles)
        close = df["close"]
        high = df["high"]
        low = df["low"]
        pattern_bars = _pattern_candles(candles)
        closed_count = _closed_bar_count(candles)
        if len(pattern_bars) >= 2:
            pat_cur = pattern_bars[-1]
            pat_prev = pattern_bars[-2]
        else:
            pat_cur = candles[-1]
            pat_prev = candles[-2] if len(candles) >= 2 else candles[-1]
        cur = pat_cur
        prev = pat_prev

        buy_score = 0.0
        sell_score = 0.0
        breakout_score = 0.0
        signals: List[TechnicalSignal] = []

        rsi_val: Optional[float] = None
        stoch_k_val: Optional[float] = None
        stoch_d_val: Optional[float] = None
        bb_u = bb_m = bb_l = None
        bb_bw: Optional[float] = None
        fib: Dict[str, float] = {}
        elliott = "neutral"
        elliott_phase = "neutral"
        elliott_trend = "neutral"
        elliott_wave_label = ""
        elliott_confidence = 0.0
        elliott_detail = ""
        divergence_bias = "neutral"
        divergence_fired = False
        divergence_kind = ""
        divergence_indicator = ""
        divergence_strength = 0.0
        divergence_detail = ""

        rsi_series: Optional[pd.Series] = None
        stoch_k_series: Optional[pd.Series] = None
        stoch_d_series: Optional[pd.Series] = None

        # RSI
        rc = self._cfg.rsi
        if rc.enabled:
            rsi_series = _rsi_series(close, rc.period)
            rsi_val = _series_last(rsi_series)
            fired = False
            bias = "neutral"
            score = 0.0
            detail = f"rsi={rsi_val:.1f}" if rsi_val is not None else "rsi=n/a"
            if rsi_val is not None:
                buy_part, buy_fired = _graded_below(
                    rsi_val, center=50.0, threshold=rc.oversold, weight=rc.buy_weight,
                )
                sell_part, sell_fired = _graded_above(
                    rsi_val, center=50.0, threshold=rc.overbought, weight=rc.sell_weight,
                )
                buy_score += buy_part
                sell_score += sell_part
                fired = buy_fired or sell_fired
                if buy_fired:
                    bias = "bullish"
                    detail += f" oversold<{rc.oversold}"
                elif sell_fired:
                    bias = "bearish"
                    detail += f" overbought>{rc.overbought}"
                elif buy_part > sell_part:
                    bias = "bullish"
                    detail += f" graded_buy={buy_part:.2f}"
                elif sell_part > buy_part:
                    bias = "bearish"
                    detail += f" graded_sell={sell_part:.2f}"
                score = buy_part if buy_part >= sell_part else sell_part
            signals.append(TechnicalSignal("rsi", True, fired, bias, score, detail))

        # Stochastic
        sc = self._cfg.stochastic
        if sc.enabled:
            k_s, d_s = _stoch_series(
                high, low, close,
                k_period=sc.k_period,
                d_period=sc.d_period,
                smooth_k=sc.smooth_k,
            )
            stoch_k_series, stoch_d_series = k_s, d_s
            stoch_k_val = _series_last(k_s)
            stoch_d_val = _series_last(d_s)
            fired = False
            bias = "neutral"
            score = 0.0
            detail = "stoch=n/a"
            if stoch_k_val is not None and stoch_d_val is not None:
                detail = f"%K={stoch_k_val:.1f} %D={stoch_d_val:.1f}"
                buy_part, sell_part, fired = _stoch_graded_scores(
                    stoch_k_val,
                    stoch_d_val,
                    oversold=sc.oversold,
                    overbought=sc.overbought,
                    buy_weight=sc.buy_weight,
                    sell_weight=sc.sell_weight,
                )
                buy_score += buy_part
                sell_score += sell_part
                if fired and buy_part >= sell_part:
                    bias = "bullish"
                    breakout_score += sc.breakout_weight * 0.5
                elif fired:
                    bias = "bearish"
                elif buy_part > sell_part:
                    bias = "bullish"
                elif sell_part > buy_part:
                    bias = "bearish"
                score = buy_part if buy_part >= sell_part else sell_part
            signals.append(TechnicalSignal("stochastic", True, fired, bias, score, detail))

        # Bollinger Bands
        bc = self._cfg.bollinger
        if bc.enabled:
            bb_l_s, bb_m_s, bb_u_s = _bollinger(close, period=bc.period, std_dev=bc.std_dev)
            bb_l = _series_last(bb_l_s)
            bb_m = _series_last(bb_m_s)
            bb_u = _series_last(bb_u_s)
            bb_bw = (
                _finite_float((bb_u - bb_l) / bb_m * 100.0)
                if bb_u is not None and bb_l is not None and bb_m and bb_m > 0
                else None
            )
            fired = False
            bias = "neutral"
            score = 0.0
            detail = f"bb_bw={bb_bw:.3f}%" if bb_bw is not None else "bb=n/a"
            if bb_bw is not None:
                if bb_bw <= bc.squeeze_bandwidth_pct:
                    detail += " squeeze"
            if (
                bb_l is not None
                and bb_m is not None
                and bb_u is not None
            ):
                buy_part, sell_part, brk_part, fired, bias = _bb_graded_scores(
                    price,
                    bb_l,
                    bb_m,
                    bb_u,
                    buy_weight=bc.buy_weight,
                    sell_weight=bc.sell_weight,
                    breakout_weight=bc.breakout_weight,
                )
                buy_score += buy_part
                sell_score += sell_part
                breakout_score += brk_part
                score = max(buy_part, sell_part, brk_part)
            signals.append(TechnicalSignal("bollinger", True, fired, bias, score, detail))

        # Fibonacci
        fc = self._cfg.fibonacci
        if fc.enabled:
            if closed_count < fc.lookback:
                signals.append(
                    TechnicalSignal(
                        "fibonacci",
                        True,
                        False,
                        "neutral",
                        0.0,
                        f"warming_up bars={closed_count}/{fc.lookback}",
                    )
                )
            else:
                window = candles[-fc.lookback :]
                hi = max(c.high for c in window)
                lo = min(c.low for c in window)
                fib = _fib_levels(hi, lo, fc.levels)
                buy_part, sell_part, fired = _fib_graded_scores(
                    price,
                    fib,
                    proximity_pct=fc.proximity_pct,
                    buy_weight=fc.buy_weight,
                    sell_weight=fc.sell_weight,
                )
                buy_score += buy_part
                sell_score += sell_part
                bias = "bullish" if buy_part > sell_part else ("bearish" if sell_part > buy_part else "neutral")
                score = buy_part if buy_part >= sell_part else sell_part
                detail = f"fib={','.join(f'{k}:{v:.6f}' for k, v in fib.items())}"
                signals.append(TechnicalSignal("fibonacci", True, fired, bias, score, detail))

        # Elliott wave — 5-wave swing pivots on full OHLC lookback
        ec = self._cfg.elliott_wave
        if ec.enabled:
            from alpha.decision.elliott_wave import analyze_elliott_five_wave

            if closed_count < ec.lookback:
                signals.append(
                    TechnicalSignal(
                        "elliott_wave",
                        True,
                        False,
                        "neutral",
                        0.0,
                        f"warming_up bars={closed_count}/{ec.lookback}",
                    )
                )
            else:
                ew = analyze_elliott_five_wave(
                    candles,
                    lookback=ec.lookback,
                    min_swing_pct=ec.min_swing_pct,
                    impulse_weight=ec.impulse_weight,
                    corrective_weight=ec.corrective_weight,
                    wave3_mult=ec.wave3_weight_mult,
                    wave5_mult=ec.wave5_weight_mult,
                    wave1_mult=ec.wave1_weight_mult,
                    dip_wave_mult=ec.dip_wave_weight_mult,
                )
                elliott = ew.bias
                elliott_phase = ew.phase
                elliott_trend = ew.trend
                elliott_wave_label = ew.wave_label
                elliott_confidence = ew.confidence
                elliott_detail = ew.detail
                fired = ew.confidence >= 0.3 and ew.bias != "neutral"
                bias = (
                    "bullish"
                    if ew.trend == "bullish_impulse"
                    else ("bearish" if ew.trend == "bearish_impulse" else "neutral")
                )
                buy_score += max(0.0, ew.buy_contribution)
                sell_score += max(0.0, ew.sell_contribution)
                if ew.trend == "corrective":
                    buy_score *= max(0.5, 1.0 - ec.corrective_weight * 0.25)
                    sell_score *= max(0.5, 1.0 - ec.corrective_weight * 0.25)
                score = max(ew.buy_contribution, ew.sell_contribution)
                detail = (
                    f"{ew.wave_label} trend={ew.trend} conf={ew.confidence:.2f} "
                    f"pivots={ew.pivot_count} {ew.detail}"
                )
                signals.append(TechnicalSignal("elliott_wave", True, fired, bias, score, detail))

        # Candle streaks
        csc = self._cfg.candle_streak
        if csc.enabled:
            streak_bars = pattern_bars if pattern_bars else candles
            greens = _green_streak(streak_bars)
            reds = _red_streak(streak_bars)
            buy_part, sell_part, fired = _streak_graded_scores(
                greens,
                reds,
                min_green=csc.min_green_streak,
                min_red=csc.min_red_streak,
                buy_weight=csc.buy_weight,
                sell_weight=csc.sell_weight,
            )
            buy_score += buy_part
            sell_score += sell_part
            if greens >= csc.min_green_streak:
                breakout_score += csc.breakout_weight
            bias = "neutral"
            score = 0.0
            detail = f"green_streak={greens} red_streak={reds}"
            if buy_part >= sell_part and buy_part > 0:
                bias, score = "bullish", buy_part
            elif sell_part > buy_part:
                bias, score = "bearish", sell_part
            signals.append(TechnicalSignal("candle_streak", True, fired, bias, score, detail))

        # Consolidation penalty
        cc = self._cfg.consolidation
        if cc.enabled and _is_consolidation(candles[-cc.lookback :], cc.max_band_width_pct):
            buy_score = max(0.0, buy_score - cc.penalty)
            sell_score = max(0.0, sell_score - cc.penalty)
            breakout_score = max(0.0, breakout_score - cc.penalty)
            signals.append(
                TechnicalSignal("consolidation", True, True, "neutral", -cc.penalty, "narrow_band")
            )

        # Pin bar
        pc = self._cfg.pin_bar
        if pc.enabled:
            bull = _bullish_pin_bar(cur, pc.min_wick_body_ratio)
            bear = _bearish_pin_bar(cur, pc.min_wick_body_ratio)
            fired = bull or bear
            bias = "bullish" if bull else ("bearish" if bear else "neutral")
            score = pc.buy_weight if bull else (pc.sell_weight if bear else 0.0)
            if bull:
                buy_score += score
            if bear:
                sell_score += score
            signals.append(TechnicalSignal("pin_bar", True, fired, bias, score, f"bull={bull} bear={bear}"))

        # Engulfing
        eg = self._cfg.engulfing
        if eg.enabled:
            bull = _bullish_engulfing(prev, cur)
            bear = _bearish_engulfing(prev, cur)
            fired = bull or bear
            bias = "bullish" if bull else ("bearish" if bear else "neutral")
            score = 0.0
            if bull:
                score = eg.buy_weight
                buy_score += score
                breakout_score += eg.breakout_weight
            if bear:
                score = eg.sell_weight
                sell_score += score
            signals.append(TechnicalSignal("engulfing", True, fired, bias, score, f"bull={bull} bear={bear}"))

        # Inside bar breakout
        ib = self._cfg.inside_bar
        if ib.enabled:
            inside = _inside_bar(prev, cur)
            fired = inside and (cur.close > prev.high or cur.close < prev.low)
            bias = "neutral"
            score = 0.0
            if inside and cur.close > prev.high:
                bias, score = "bullish", ib.breakout_weight
                buy_score += ib.buy_weight
                breakout_score += score
            elif inside and cur.close < prev.low:
                bias, score = "bearish", ib.breakout_weight
                sell_score += ib.sell_weight
            signals.append(TechnicalSignal("inside_bar", True, fired, bias, score, f"inside={inside}"))

        # HH / LL structure (BOS) — boosted when 5-wave trend confirms
        bos = self._cfg.structure_bos
        if bos.enabled:
            struct = _higher_highs_lower_lows(candles, bos.lookback)
            if struct == "neutral" and ec.enabled and elliott_trend == "bullish_impulse":
                struct = "bullish"
            elif struct == "neutral" and ec.enabled and elliott_trend == "bearish_impulse":
                struct = "bearish"
            fired = struct != "neutral"
            bias = struct
            score = bos.buy_weight if struct == "bullish" else (bos.sell_weight if struct == "bearish" else 0.0)
            if (
                ec.enabled
                and elliott_trend == "bullish_impulse"
                and elliott_phase in ("wave3", "wave5")
                and struct == "bullish"
            ):
                score += bos.buy_weight * 0.25 * max(0.0, elliott_confidence)
            elif (
                ec.enabled
                and elliott_trend == "bearish_impulse"
                and elliott_phase in ("wave3", "wave5")
                and struct == "bearish"
            ):
                score += bos.sell_weight * 0.25 * max(0.0, elliott_confidence)
            if struct == "bullish":
                buy_score += score
            elif struct == "bearish":
                sell_score += score
            bos_detail = f"trend={struct}"
            if elliott_wave_label:
                bos_detail += f" elliott={elliott_wave_label}"
            signals.append(TechnicalSignal("structure_bos", True, fired, bias, score, bos_detail))

        # Order blocks
        ob = self._cfg.order_block
        if ob.enabled:
            bull_ob, bear_ob = _order_block_zone(candles, ob.lookback)
            fired = False
            bias = "neutral"
            score = 0.0
            detail = "no_ob"
            if bull_ob is not None and _near_level(price, bull_ob, ob.proximity_pct):
                fired, bias, score = True, "bullish", ob.buy_weight
                buy_score += score
                detail = f"bull_ob={bull_ob:.6f}"
            elif bear_ob is not None and _near_level(price, bear_ob, ob.proximity_pct):
                fired, bias, score = True, "bearish", ob.sell_weight
                sell_score += score
                detail = f"bear_ob={bear_ob:.6f}"
            signals.append(TechnicalSignal("order_block", True, fired, bias, score, detail))

        # Fair value gap
        fvg = self._cfg.fair_value_gap
        if fvg.enabled:
            bull_gap = _bullish_fvg(candles[-fvg.lookback :], fvg.min_gap_pct)
            fired = bull_gap
            score = fvg.buy_weight if bull_gap else 0.0
            if bull_gap:
                buy_score += score
            signals.append(TechnicalSignal("fair_value_gap", True, fired, "bullish" if bull_gap else "neutral", score, f"bull_fvg={bull_gap}"))

        # Liquidity grab
        lg = self._cfg.liquidity_grab
        if lg.enabled:
            buy_grab = _liquidity_grab_buy(candles, lg.lookback, lg.wick_penetration_pct)
            sell_grab = _liquidity_grab_sell(candles, lg.lookback, lg.wick_penetration_pct)
            fired = buy_grab or sell_grab
            bias = "bullish" if buy_grab else ("bearish" if sell_grab else "neutral")
            score = lg.buy_weight if buy_grab else (lg.sell_weight if sell_grab else 0.0)
            if buy_grab:
                buy_score += score
            if sell_grab:
                sell_score += score
            signals.append(TechnicalSignal("liquidity_grab", True, fired, bias, score, f"buy={buy_grab} sell={sell_grab}"))

        # Divergence — price pivots vs RSI/Stoch/MACD
        dc = self._cfg.divergence
        if dc.enabled:
            from alpha.decision.divergence import detect_divergences

            div = detect_divergences(
                candles,
                cfg=dc,
                rsi=rsi_series,
                stoch_k=stoch_k_series,
                stoch_d=stoch_d_series,
                close=close,
            )
            divergence_bias = div.bias
            divergence_fired = div.fired
            divergence_kind = div.kind
            divergence_indicator = div.indicator
            divergence_strength = div.strength
            divergence_detail = div.detail
            buy_score += max(0.0, div.buy_contribution)
            sell_score += max(0.0, div.sell_contribution)
            fired = div.fired
            bias = div.bias if div.fired else "neutral"
            score = max(div.buy_contribution, div.sell_contribution)
            label = div.kind.replace("_", " ") if div.kind else "none"
            detail = div.detail or f"scan pivots lookback={dc.lookback_bars}"
            if div.fired:
                logger.info(
                    "divergence | %s %s strength=%.2f buy+=%.2f sell+=%.2f | %s",
                    div.kind,
                    div.indicator,
                    div.strength,
                    div.buy_contribution,
                    div.sell_contribution,
                    div.detail,
                )
            signals.append(TechnicalSignal("divergence", True, fired, bias, score, f"{label} {detail}"))

        if buy_score > sell_score + 0.25:
            bias = "bullish"
        elif sell_score > buy_score + 0.25:
            bias = "bearish"
        else:
            bias = "neutral"

        entry_buy_allowed = buy_score >= self._cfg.min_buy_score
        entry_sell_allowed = sell_score >= self._cfg.min_sell_score
        breakout_confirmed = breakout_score >= self._cfg.min_breakout_score

        if self._cfg.mode == "strict":
            entry_buy_allowed = buy_score >= self._cfg.min_buy_score and sell_score < self._cfg.min_sell_score
            entry_sell_allowed = sell_score >= self._cfg.min_sell_score and buy_score < self._cfg.min_buy_score

        bars_note = ""
        if len(candles) < self._cfg.min_candles:
            bars_note = f" bars={len(candles)}/{self._cfg.min_candles}"
        summary = (
            f"ta buy={buy_score:.2f} sell={sell_score:.2f} breakout={breakout_score:.2f} "
            f"bias={bias} elliott={elliott_wave_label or elliott}"
            f"{f' div={divergence_kind}' if divergence_fired else ''}{bars_note}"
        )
        logger.info("technical_analysis | %s", summary)

        return TechnicalAnalysisSnapshot(
            mid=_finite_float(price) or 0.0,
            enabled=True,
            buy_score=_finite_float(round(buy_score, 3)) or 0.0,
            sell_score=_finite_float(round(sell_score, 3)) or 0.0,
            breakout_score=_finite_float(round(breakout_score, 3)) or 0.0,
            bias=bias,
            entry_buy_allowed=entry_buy_allowed,
            entry_sell_allowed=entry_sell_allowed,
            breakout_confirmed=breakout_confirmed,
            signals=tuple(signals),
            summary=summary,
            rsi=rsi_val,
            stoch_k=stoch_k_val,
            stoch_d=stoch_d_val,
            bb_upper=bb_u,
            bb_middle=bb_m,
            bb_lower=bb_l,
            bb_bandwidth_pct=bb_bw,
            fib_levels=fib,
            elliott_bias=elliott,
            elliott_phase=elliott_phase,
            elliott_trend=elliott_trend,
            elliott_wave_label=elliott_wave_label,
            elliott_confidence=_finite_float(round(elliott_confidence, 3)) or 0.0,
            elliott_detail=elliott_detail,
            divergence_bias=divergence_bias,
            divergence_fired=divergence_fired,
            divergence_kind=divergence_kind,
            divergence_indicator=divergence_indicator,
            divergence_strength=_finite_float(round(divergence_strength, 3)) or 0.0,
            divergence_detail=divergence_detail,
        )
