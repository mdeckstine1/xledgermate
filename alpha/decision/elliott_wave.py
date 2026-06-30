"""Elliott wave — swing pivots and 5-wave impulse detection on OHLC history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from alpha.decision.structure import CandleData

_PRICE_EPS = 1e-9

# Pivot: (bar_index, price, kind) kind = L | H
Pivot = Tuple[int, float, str]


@dataclass(frozen=True)
class ElliottWaveResult:
    """5-wave read for TA scoring and HUD."""

    bias: str  # impulse_up | impulse_down | corrective | neutral (legacy compat)
    phase: str  # wave1..wave5 | correction | neutral
    trend: str  # bullish_impulse | bearish_impulse | corrective | neutral
    wave_label: str
    confidence: float
    pivot_count: int
    detail: str
    buy_contribution: float
    sell_contribution: float

    def to_dict(self) -> dict:
        return {
            "bias": self.bias,
            "phase": self.phase,
            "trend": self.trend,
            "wave_label": self.wave_label,
            "confidence": round(self.confidence, 3),
            "pivot_count": self.pivot_count,
            "detail": self.detail,
            "buy_contribution": round(self.buy_contribution, 3),
            "sell_contribution": round(self.sell_contribution, 3),
        }


def _pct_move(a: float, b: float) -> float:
    ref = max(abs(a), _PRICE_EPS)
    return abs(b - a) / ref * 100.0


def find_swing_pivots(
    candles: Sequence[CandleData],
    *,
    min_swing_pct: float,
) -> List[Pivot]:
    """Zigzag pivots from bar highs/lows — needs min_swing_pct reversal to flip."""
    if len(candles) < 3:
        return []

    threshold = max(0.05, float(min_swing_pct))
    pivots: List[Pivot] = []

    # Seed first pivot at extreme in first few bars
    start_idx = 0
    start_low = candles[0].low
    start_high = candles[0].high
    for i in range(min(3, len(candles))):
        if candles[i].low < start_low:
            start_low = candles[i].low
            start_idx = i
        if candles[i].high > start_high:
            start_high = candles[i].high
            start_idx = i

    direction = 1  # 1 = seeking high after low pivot, -1 = seeking low after high
    last_pivot_price = start_low if candles[start_idx].low <= candles[start_idx].high else start_low
    last_pivot_kind = "L"
    last_pivot_idx = start_idx
    pivots.append((start_idx, last_pivot_price, "L"))

    candidate_idx = start_idx
    candidate_price = candles[start_idx].high

    for i in range(start_idx + 1, len(candles)):
        bar = candles[i]
        if direction > 0:
            if bar.high >= candidate_price:
                candidate_price = bar.high
                candidate_idx = i
            if _pct_move(candidate_price, bar.low) >= threshold:
                pivots.append((candidate_idx, candidate_price, "H"))
                last_pivot_price = candidate_price
                last_pivot_kind = "H"
                last_pivot_idx = candidate_idx
                direction = -1
                candidate_price = bar.low
                candidate_idx = i
        else:
            if bar.low <= candidate_price:
                candidate_price = bar.low
                candidate_idx = i
            if _pct_move(candidate_price, bar.high) >= threshold:
                pivots.append((candidate_idx, candidate_price, "L"))
                last_pivot_price = candidate_price
                last_pivot_kind = "L"
                last_pivot_idx = candidate_idx
                direction = 1
                candidate_price = bar.high
                candidate_idx = i

    # Trim duplicate consecutive kinds
    cleaned: List[Pivot] = []
    for p in pivots:
        if cleaned and cleaned[-1][2] == p[2]:
            if p[2] == "H" and p[1] >= cleaned[-1][1]:
                cleaned[-1] = p
            elif p[2] == "L" and p[1] <= cleaned[-1][1]:
                cleaned[-1] = p
        else:
            cleaned.append(p)
    return cleaned


def _validate_bullish_five_wave(p: Sequence[Pivot]) -> Tuple[bool, float, str]:
    """Six pivots L-H-L-H-L-H define five up-waves. Returns ok, confidence, note."""
    if len(p) < 6:
        return False, 0.0, "need_6_pivots"
    chunk = p[-6:]
    kinds = [x[2] for x in chunk]
    if kinds != ["L", "H", "L", "H", "L", "H"]:
        return False, 0.0, f"pivot_shape={''.join(kinds)}"

    p0, p1, p2, p3, p4, p5 = [x[1] for x in chunk]
    w1 = p1 - p0
    w2 = p1 - p2
    w3 = p3 - p2
    w4 = p3 - p4
    w5 = p5 - p4
    if w1 <= 0 or w3 <= 0 or w5 <= 0:
        return False, 0.0, "not_impulse_up"
    if w2 <= 0 or w4 <= 0:
        return False, 0.0, "pullbacks_invalid"

    conf = 0.45
    notes: List[str] = []
    if w2 < w1 * 1.001:
        conf += 0.15
        notes.append("w2<w1")
    else:
        notes.append("w2_deep")

    if w3 >= w1 and w3 >= w5:
        conf += 0.2
        notes.append("w3_strong")
    elif w3 >= w1:
        conf += 0.1
        notes.append("w3_ok")

    if p4 > p0:
        conf += 0.1
        notes.append("w4_hold")
    else:
        notes.append("w4_overlap")

    if w5 > 0 and p5 > p3:
        conf += 0.1
        notes.append("w5_ext")

    return True, min(1.0, conf), " ".join(notes)


def _validate_bearish_five_wave(p: Sequence[Pivot]) -> Tuple[bool, float, str]:
    if len(p) < 6:
        return False, 0.0, "need_6_pivots"
    chunk = p[-6:]
    kinds = [x[2] for x in chunk]
    if kinds != ["H", "L", "H", "L", "H", "L"]:
        return False, 0.0, f"pivot_shape={''.join(kinds)}"

    p0, p1, p2, p3, p4, p5 = [x[1] for x in chunk]
    w1 = p0 - p1
    w2 = p2 - p1
    w3 = p2 - p3
    w4 = p4 - p3
    w5 = p4 - p5
    if w1 <= 0 or w3 <= 0 or w5 <= 0:
        return False, 0.0, "not_impulse_down"
    if w2 <= 0 or w4 <= 0:
        return False, 0.0, "pullbacks_invalid"

    conf = 0.45
    notes: List[str] = []
    if w2 < w1 * 1.001:
        conf += 0.15
        notes.append("w2<w1")
    if w3 >= w1 and w3 >= w5:
        conf += 0.2
        notes.append("w3_strong")
    if p4 < p0:
        conf += 0.1
        notes.append("w4_hold")
    if w5 > 0 and p5 < p3:
        conf += 0.1
        notes.append("w5_ext")

    return True, min(1.0, conf), " ".join(notes)


def _best_five_wave(
    pivots: Sequence[Pivot],
    *,
    direction: str,
) -> Tuple[bool, float, str, int]:
    """Scan pivot windows; return best confidence match and start index."""
    if len(pivots) < 6:
        return False, 0.0, "need_6_pivots", -1
    validate = _validate_bullish_five_wave if direction == "bull" else _validate_bearish_five_wave
    best_conf = 0.0
    best_note = ""
    best_start = -1
    best_ok = False
    for start in range(0, len(pivots) - 5):
        chunk = pivots[start : start + 6]
        ok, conf, note = validate(chunk)
        if ok and conf >= best_conf:
            best_ok, best_conf, best_note, best_start = ok, conf, note, start
    return best_ok, best_conf, best_note, best_start


def _infer_current_wave(
    pivots: Sequence[Pivot],
    *,
    last_close: float,
    direction: str,
) -> Tuple[str, str]:
    """Map price position to wave phase within forming impulse."""
    if len(pivots) < 2:
        return "neutral", "—"

    last_kind = pivots[-1][2]
    last_price = pivots[-1][1]
    prev_price = pivots[-2][1]

    if direction == "bullish_impulse":
        # After low pivot → rallying (odd waves); after high → pullback (even)
        if last_kind == "L":
            # Count how many lows in last 6 pivots → wave 1,3,5 start territory
            n = len(pivots)
            if n >= 6:
                return "wave5", "W5↑"
            if n >= 4:
                return "wave3", "W3↑"
            return "wave1", "W1↑"
        # last pivot high — in pullback
        if last_close < last_price and _pct_move(last_price, last_close) > 0.15:
            if len(pivots) >= 5:
                return "wave4", "W4↓"
            return "wave2", "W2↓"
        return "wave5", "W5↑"

    if direction == "bearish_impulse":
        if last_kind == "H":
            if len(pivots) >= 6:
                return "wave5", "W5↓"
            if len(pivots) >= 4:
                return "wave3", "W3↓"
            return "wave1", "W1↓"
        if last_close > last_price and _pct_move(last_close, last_price) > 0.15:
            if len(pivots) >= 5:
                return "wave4", "W4↑"
            return "wave2", "W2↑"
        return "wave5", "W5↓"

    return "neutral", "—"


def analyze_elliott_five_wave(
    candles: Sequence[CandleData],
    *,
    lookback: int,
    min_swing_pct: float,
    impulse_weight: float,
    corrective_weight: float,
    wave3_mult: float = 1.0,
    wave5_mult: float = 0.5,
    wave1_mult: float = 0.35,
    dip_wave_mult: float = 0.25,
) -> ElliottWaveResult:
    """Detect 5-wave impulse on closed-bar OHLC window; score by wave position."""
    window = list(candles[-max(12, int(lookback)) :])
    if len(window) < 12:
        return ElliottWaveResult(
            bias="neutral",
            phase="neutral",
            trend="neutral",
            wave_label="—",
            confidence=0.0,
            pivot_count=0,
            detail=f"insufficient_bars={len(window)}",
            buy_contribution=0.0,
            sell_contribution=0.0,
        )

    pivots = find_swing_pivots(window, min_swing_pct=min_swing_pct)
    last_close = float(window[-1].close)

    bull_ok, bull_conf, bull_note, bull_start = _best_five_wave(pivots, direction="bull")
    bear_ok, bear_conf, bear_note, bear_start = _best_five_wave(pivots, direction="bear")

    if bull_ok and bear_ok:
        window_move = last_close - float(window[0].close)
        if window_move > 0:
            bear_ok = False
        elif window_move < 0:
            bull_ok = False
        elif bull_conf > bear_conf:
            bear_ok = False
        else:
            bull_ok = False

    # Phase inference uses pivots from the winning pattern onward
    phase_pivots = pivots
    if bull_ok and bull_start >= 0:
        phase_pivots = pivots[bull_start:]
    elif bear_ok and bear_start >= 0:
        phase_pivots = pivots[bear_start:]

    trend = "neutral"
    confidence = 0.0
    detail = f"pivots={len(pivots)}"
    if bull_ok and (not bear_ok or bull_conf >= bear_conf):
        trend = "bullish_impulse"
        confidence = bull_conf
        detail = f"bull_5wave {bull_note}"
    elif bear_ok:
        trend = "bearish_impulse"
        confidence = bear_conf
        detail = f"bear_5wave {bear_note}"
    elif len(pivots) >= 4:
        # Partial structure — higher highs / higher lows trending
        hh_ll = _simple_trend(pivots)
        if hh_ll == "bullish":
            trend = "bullish_impulse"
            confidence = 0.35
            detail = "partial_bull_pivots"
        elif hh_ll == "bearish":
            trend = "bearish_impulse"
            confidence = 0.35
            detail = "partial_bear_pivots"

    phase, wave_label = _infer_current_wave(phase_pivots, last_close=last_close, direction=trend)

    # Corrective: shallow range after 5-wave or overlapping pivots
    if trend == "neutral" and len(pivots) >= 3:
        span = _pct_move(pivots[-3][1], pivots[-1][1])
        if span < max(0.25, min_swing_pct * 0.75):
            trend = "corrective"
            phase = "correction"
            wave_label = "ABC?"
            confidence = 0.3
            detail = "range_corrective"

    buy = 0.0
    sell = 0.0
    bias = "neutral"
    w = max(0.0, float(impulse_weight)) * max(0.1, confidence)

    if trend == "bullish_impulse":
        bias = "impulse_up"
        if phase in ("wave3",):
            buy = w * wave3_mult
        elif phase in ("wave5",):
            buy = w * wave5_mult
        elif phase in ("wave1",):
            buy = w * wave1_mult
        elif phase in ("wave2", "wave4"):
            buy = w * dip_wave_mult
        else:
            buy = w * 0.4
    elif trend == "bearish_impulse":
        bias = "impulse_down"
        if phase in ("wave3",):
            sell = w * wave3_mult
        elif phase in ("wave5",):
            sell = w * wave5_mult
        elif phase in ("wave1",):
            sell = w * wave1_mult
        elif phase in ("wave2", "wave4"):
            sell = w * dip_wave_mult
        else:
            sell = w * 0.4
    elif trend == "corrective":
        bias = "corrective"
        # Dampening applied in technical_analysis — no negative score here
        buy = 0.0
        sell = 0.0

    return ElliottWaveResult(
        bias=bias,
        phase=phase,
        trend=trend,
        wave_label=wave_label,
        confidence=confidence,
        pivot_count=len(pivots),
        detail=detail,
        buy_contribution=buy,
        sell_contribution=sell,
    )


def _simple_trend(pivots: Sequence[Pivot]) -> str:
    highs = [p[1] for p in pivots if p[2] == "H"]
    lows = [p[1] for p in pivots if p[2] == "L"]
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
            return "bullish"
        if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
            return "bearish"
    return "neutral"


def legacy_thirds_bias(candles: Sequence[CandleData], lookback: int) -> str:
    """Previous coarse 3-chunk estimator — fallback when pivots are sparse."""
    window = candles[-lookback:]
    if len(window) < 6:
        return "neutral"
    closes = [c.close for c in window]
    third = len(closes) // 3
    a = sum(closes[:third]) / max(third, 1)
    b = sum(closes[third : 2 * third]) / max(third, 1)
    c = sum(closes[2 * third :]) / max(len(closes) - 2 * third, 1)
    if c > a * 1.002 and c > b:
        return "impulse_up"
    if c < a * 0.998 and c < b:
        return "impulse_down"
    if abs(c - b) / max(b, _PRICE_EPS) < 0.003:
        return "corrective"
    return "neutral"
