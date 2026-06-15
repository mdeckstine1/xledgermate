"""
B3 — WS book age modulator (pure A-S inputs only).

Stale book → higher effective volatility (wider / more defensive).
Fresh book + low competitor pressure → allow aggression (lower vol, slight size boost).

Never touches reservation directly — only vol (and optional size mult for B2 chain).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

DEFAULT_FRESH_AGE_S = 5.0
DEFAULT_STALE_AGE_S = 12.0
DEFAULT_MAX_STALE_AGE_S = 45.0
DEFAULT_LOW_PRESSURE_THRESHOLD = 0.4
DEFAULT_MAX_STALE_VOL_MULT = 1.45
DEFAULT_MIN_FRESH_VOL_MULT = 0.82
DEFAULT_FRESH_SIZE_MULT = 1.06


@dataclass(frozen=True)
class BookAgeAdjustedInputs:
    volatility_pct: float
    vol_mult: float
    size_mult: float
    tag: str
    rationale: str


def apply_ws_book_age_modulator(
    *,
    base_volatility_pct: float,
    ws_book_age_s: float,
    competitor_pressure: Optional[float] = None,
    fresh_age_s: float = DEFAULT_FRESH_AGE_S,
    stale_age_s: float = DEFAULT_STALE_AGE_S,
    max_stale_age_s: float = DEFAULT_MAX_STALE_AGE_S,
    low_pressure_threshold: float = DEFAULT_LOW_PRESSURE_THRESHOLD,
    max_stale_vol_mult: float = DEFAULT_MAX_STALE_VOL_MULT,
    min_fresh_vol_mult: float = DEFAULT_MIN_FRESH_VOL_MULT,
    fresh_size_mult: float = DEFAULT_FRESH_SIZE_MULT,
) -> BookAgeAdjustedInputs:
    """Map WS book age (+ optional pressure) → vol/size input multipliers."""
    age = max(0.0, float(ws_book_age_s))
    vol_mult = 1.0
    size_mult = 1.0
    tag = "NEUTRAL"

    if age >= stale_age_s:
        span = max(max_stale_age_s - stale_age_s, 1e-6)
        t = min(1.0, (age - stale_age_s) / span)
        vol_mult = 1.0 + t * (max_stale_vol_mult - 1.0)
        tag = "STALE"
    elif age <= fresh_age_s:
        low_p = (
            competitor_pressure is not None
            and competitor_pressure < low_pressure_threshold
        )
        if low_p:
            p = float(competitor_pressure)  # type: ignore[arg-type]
            aggress = (low_pressure_threshold - p) / max(low_pressure_threshold, 1e-6)
            vol_mult = 1.0 - aggress * (1.0 - min_fresh_vol_mult)
            size_mult = 1.0 + aggress * (fresh_size_mult - 1.0)
            tag = "FRESH+LOW_P"
        else:
            tag = "FRESH"

    vol = max(0.02, base_volatility_pct * vol_mult)
    rationale = (
        f"BOOK_AGE age={age:.1f}s {tag} vol×{vol_mult:.2f}"
        + (f" size×{size_mult:.2f}" if size_mult != 1.0 else "")
        + f" → {vol:.3f}%"
    )
    return BookAgeAdjustedInputs(
        volatility_pct=vol,
        vol_mult=vol_mult,
        size_mult=size_mult,
        tag=tag,
        rationale=rationale,
    )
