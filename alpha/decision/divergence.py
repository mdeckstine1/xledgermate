"""Price vs momentum divergence — pivot-based RSI/Stoch/MACD disagreement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import pandas as pd

from alpha.decision.elliott_wave import Pivot, find_swing_pivots
from alpha.decision.structure import CandleData
from alpha.decision.ta_config import DivergenceConfig

try:
    import pandas_ta as pta  # type: ignore[import-untyped]

    _HAS_PANDAS_TA = True
except ImportError:
    pta = None  # type: ignore[assignment]
    _HAS_PANDAS_TA = False

_PRICE_EPS = 1e-9


@dataclass(frozen=True)
class DivergenceHit:
    """Single divergence read on one indicator."""

    kind: str  # bullish_regular | bearish_regular | bullish_hidden | bearish_hidden
    indicator: str  # rsi | stoch | macd
    strength: float
    detail: str


@dataclass(frozen=True)
class DivergenceResult:
    """Graded divergence output for TA scoring and HUD."""

    bias: str  # bullish | bearish | neutral
    fired: bool
    kind: str
    indicator: str
    strength: float
    buy_contribution: float
    sell_contribution: float
    hits: Tuple[DivergenceHit, ...]
    detail: str

    def to_dict(self) -> dict:
        return {
            "bias": self.bias,
            "fired": self.fired,
            "kind": self.kind,
            "indicator": self.indicator,
            "strength": round(self.strength, 3),
            "buy_contribution": round(self.buy_contribution, 3),
            "sell_contribution": round(self.sell_contribution, 3),
            "detail": self.detail,
            "hits": [
                {
                    "kind": h.kind,
                    "indicator": h.indicator,
                    "strength": round(h.strength, 3),
                    "detail": h.detail,
                }
                for h in self.hits
            ],
        }


def _finite_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not (out == out and abs(out) != float("inf")):  # NaN / inf
        return None
    return out


def _indicator_at(series: pd.Series, bar_idx: int) -> Optional[float]:
    if bar_idx < 0 or bar_idx >= len(series):
        return None
    return _finite_float(series.iloc[bar_idx])


def _macd_histogram(
    close: pd.Series,
    *,
    fast: int,
    slow: int,
    signal: int,
) -> pd.Series:
    if _HAS_PANDAS_TA and pta is not None:
        out = pta.macd(close, fast=fast, slow=slow, signal=signal)
        if out is not None and not out.empty:
            hist_col = next(
                (c for c in out.columns if "h" in c.lower() and "macd" in c.lower()),
                None,
            )
            if hist_col is None:
                hist_col = [c for c in out.columns if c.startswith("MACD")][-1]
            return out[hist_col]
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line - signal_line


def _divergence_strength(
    price1: float,
    price2: float,
    ind1: float,
    ind2: float,
    *,
    ind_scale: float,
) -> float:
    price_pct = abs(price2 - price1) / max(abs(price1), _PRICE_EPS) * 100.0
    ind_norm = abs(ind2 - ind1) / max(ind_scale, _PRICE_EPS)
    return min(1.0, (price_pct / 1.5 + ind_norm) / 2.0)


def _classify_low_pair(
    price1: float,
    price2: float,
    ind1: float,
    ind2: float,
    *,
    ind_scale: float,
) -> Optional[Tuple[str, float]]:
    """Pivot lows: regular/hidden bullish divergence."""
    if price2 < price1 - _PRICE_EPS and ind2 > ind1 + _PRICE_EPS:
        kind = "bullish_regular"
    elif price2 > price1 + _PRICE_EPS and ind2 < ind1 - _PRICE_EPS:
        kind = "bullish_hidden"
    else:
        return None
    strength = _divergence_strength(price1, price2, ind1, ind2, ind_scale=ind_scale)
    return kind, strength


def _classify_high_pair(
    price1: float,
    price2: float,
    ind1: float,
    ind2: float,
    *,
    ind_scale: float,
) -> Optional[Tuple[str, float]]:
    """Pivot highs: regular/hidden bearish divergence."""
    if price2 > price1 + _PRICE_EPS and ind2 < ind1 - _PRICE_EPS:
        kind = "bearish_regular"
    elif price2 < price1 - _PRICE_EPS and ind2 > ind1 + _PRICE_EPS:
        kind = "bearish_hidden"
    else:
        return None
    strength = _divergence_strength(price1, price2, ind1, ind2, ind_scale=ind_scale)
    return kind, strength


def _last_two_pivots(pivots: Sequence[Pivot], kind: str) -> Optional[Tuple[Pivot, Pivot]]:
    filtered = [p for p in pivots if p[2] == kind]
    if len(filtered) < 2:
        return None
    return filtered[-2], filtered[-1]


def _scan_indicator(
    pivots: Sequence[Pivot],
    series: pd.Series,
    *,
    indicator: str,
    ind_scale: float,
    min_strength: float,
) -> List[DivergenceHit]:
    hits: List[DivergenceHit] = []
    low_pair = _last_two_pivots(pivots, "L")
    if low_pair is not None:
        (_, p1, _), (_, p2, _) = low_pair
        i1 = _indicator_at(series, low_pair[0][0])
        i2 = _indicator_at(series, low_pair[1][0])
        if i1 is not None and i2 is not None:
            classified = _classify_low_pair(p1, p2, i1, i2, ind_scale=ind_scale)
            if classified is not None:
                kind, strength = classified
                if strength >= min_strength:
                    hits.append(
                        DivergenceHit(
                            kind=kind,
                            indicator=indicator,
                            strength=strength,
                            detail=(
                                f"L {p1:.6f}->{p2:.6f} {indicator} {i1:.2f}->{i2:.2f} "
                                f"({kind.replace('_', ' ')})"
                            ),
                        )
                    )
    high_pair = _last_two_pivots(pivots, "H")
    if high_pair is not None:
        (_, p1, _), (_, p2, _) = high_pair
        i1 = _indicator_at(series, high_pair[0][0])
        i2 = _indicator_at(series, high_pair[1][0])
        if i1 is not None and i2 is not None:
            classified = _classify_high_pair(p1, p2, i1, i2, ind_scale=ind_scale)
            if classified is not None:
                kind, strength = classified
                if strength >= min_strength:
                    hits.append(
                        DivergenceHit(
                            kind=kind,
                            indicator=indicator,
                            strength=strength,
                            detail=(
                                f"H {p1:.6f}->{p2:.6f} {indicator} {i1:.2f}->{i2:.2f} "
                                f"({kind.replace('_', ' ')})"
                            ),
                        )
                    )
    return hits


def detect_divergences(
    candles: Sequence[CandleData],
    *,
    cfg: DivergenceConfig,
    rsi: Optional[pd.Series] = None,
    stoch_k: Optional[pd.Series] = None,
    stoch_d: Optional[pd.Series] = None,
    close: Optional[pd.Series] = None,
) -> DivergenceResult:
    """
    Scan swing pivots for price vs momentum disagreement.

    Uses zigzag pivots (same family as Elliott) on the lookback window.
    """
    empty = DivergenceResult(
        bias="neutral",
        fired=False,
        kind="",
        indicator="",
        strength=0.0,
        buy_contribution=0.0,
        sell_contribution=0.0,
        hits=(),
        detail="disabled",
    )
    if not cfg.enabled or len(candles) < 6:
        return replace_detail(empty, "insufficient_bars" if cfg.enabled else "disabled")

    window = list(candles[-max(6, int(cfg.lookback_bars)) :])
    pivots = find_swing_pivots(window, min_swing_pct=cfg.min_swing_pct)
    if len(pivots) < 3:
        return replace_detail(empty, f"insufficient_pivots={len(pivots)}")

    all_hits: List[DivergenceHit] = []
    if cfg.use_rsi and rsi is not None and not rsi.empty:
        all_hits.extend(
            _scan_indicator(
                pivots,
                rsi.iloc[-len(window) :],
                indicator="rsi",
                ind_scale=25.0,
                min_strength=cfg.min_strength,
            )
        )
    if cfg.use_stochastic:
        stoch_series = stoch_k if cfg.stoch_series == "k" else stoch_d
        if stoch_series is not None and not stoch_series.empty:
            all_hits.extend(
                _scan_indicator(
                    pivots,
                    stoch_series.iloc[-len(window) :],
                    indicator=f"stoch_{cfg.stoch_series}",
                    ind_scale=30.0,
                    min_strength=cfg.min_strength,
                )
            )
    if cfg.use_macd and close is not None and not close.empty:
        hist = _macd_histogram(
            close.iloc[-len(window) :],
            fast=cfg.macd_fast,
            slow=cfg.macd_slow,
            signal=cfg.macd_signal,
        )
        all_hits.extend(
            _scan_indicator(
                pivots,
                hist,
                indicator="macd_hist",
                ind_scale=max(abs(_finite_float(hist.iloc[-1]) or 0.0), 0.05),
                min_strength=cfg.min_strength,
            )
        )

    if not all_hits:
        return replace_detail(empty, f"no_divergence pivots={len(pivots)}")

    # Best hit per direction (strongest strength wins)
    bullish = [h for h in all_hits if h.kind.startswith("bullish")]
    bearish = [h for h in all_hits if h.kind.startswith("bearish")]
    best_bull = max(bullish, key=lambda h: h.strength, default=None)
    best_bear = max(bearish, key=lambda h: h.strength, default=None)

    buy_contrib = 0.0
    sell_contrib = 0.0
    if best_bull is not None:
        mult = cfg.hidden_weight_mult if "hidden" in best_bull.kind else 1.0
        buy_contrib = cfg.buy_weight * best_bull.strength * mult
    if best_bear is not None:
        mult = cfg.hidden_weight_mult if "hidden" in best_bear.kind else 1.0
        sell_contrib = cfg.sell_weight * best_bear.strength * mult

    primary = None
    if best_bull and best_bear:
        primary = best_bull if best_bull.strength >= best_bear.strength else best_bear
    else:
        primary = best_bull or best_bear

    if primary is None:
        return replace_detail(empty, "no_divergence")

    bias = "bullish" if primary.kind.startswith("bullish") else "bearish"
    detail_parts = [h.detail for h in sorted(all_hits, key=lambda h: -h.strength)[:3]]
    return DivergenceResult(
        bias=bias,
        fired=True,
        kind=primary.kind,
        indicator=primary.indicator,
        strength=primary.strength,
        buy_contribution=buy_contrib,
        sell_contribution=sell_contrib,
        hits=tuple(all_hits),
        detail=" | ".join(detail_parts),
    )


def replace_detail(result: DivergenceResult, detail: str) -> DivergenceResult:
    return DivergenceResult(
        bias=result.bias,
        fired=result.fired,
        kind=result.kind,
        indicator=result.indicator,
        strength=result.strength,
        buy_contribution=result.buy_contribution,
        sell_contribution=result.sell_contribution,
        hits=result.hits,
        detail=detail,
    )
