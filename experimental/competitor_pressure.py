"""
Formal competitor pressure model for pure A-S input tuning.

0.0 = defensive / wide makers (skim harder). 1.0 = aggressive competitors (back off).
Monotonic effects on volatility, gamma scale, and size multiplier — never on reservation directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class CompetitorPressure:
    """Normalized competitor pressure for A-S input adjustment."""

    value: float
    observed_l1_spread_pct: float = 0.0
    depth_ahead_xrp: float = 0.0
    ask_pressure: Optional[float] = None
    bid_pressure: Optional[float] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _clamp(float(self.value), 0.0, 1.0))
        if self.ask_pressure is not None:
            object.__setattr__(self, "ask_pressure", _clamp(float(self.ask_pressure), 0.0, 1.0))
        if self.bid_pressure is not None:
            object.__setattr__(self, "bid_pressure", _clamp(float(self.bid_pressure), 0.0, 1.0))

    def effective_for_inventory(self, inventory_skew: float) -> float:
        """XRP-heavy rebalance: prefer ask-side pressure when set."""
        if inventory_skew > 0.15 and self.ask_pressure is not None:
            return self.ask_pressure
        if inventory_skew < -0.15 and self.bid_pressure is not None:
            return self.bid_pressure
        return self.value


@dataclass(frozen=True)
class PressureAdjustedInputs:
    volatility_pct: float
    size_mult: float
    gamma_scale: float
    book_spread_pct: float
    effective_pressure: float
    rationale: str = ""


def from_intel_dict(data: Optional[Mapping[str, Any]]) -> Optional[CompetitorPressure]:
    if not data:
        return None
    raw = data.get("competitor_pressure", data.get("pressure_score"))
    if raw is None:
        return None
    return CompetitorPressure(
        value=float(raw),
        observed_l1_spread_pct=float(
            data.get("competitor_observed_spread_pct") or data.get("observed_market_spread_pct") or 0.0
        ),
        depth_ahead_xrp=float(data.get("competitor_depth_xrp") or data.get("total_competitor_depth_xrp") or 0.0),
        ask_pressure=_optional_float(data.get("ask_pressure")),
        bid_pressure=_optional_float(data.get("bid_pressure")),
    )


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def apply_competitor_pressure(
    pressure: CompetitorPressure,
    *,
    base_volatility_pct: float,
    base_book_spread_pct: float,
    inventory_skew: float = 0.0,
    base_size_mult: float = 1.0,
    low_threshold: float = 0.4,
    high_threshold: float = 0.7,
) -> PressureAdjustedInputs:
    """
    Map pressure -> A-S inputs. Low pressure = more aggressive (lower vol, larger size).
    Uses observed competitor spread as book anchor when pressure is low and spread is tighter.
    """
    p = pressure.effective_for_inventory(inventory_skew)
    defensive = 1.0 - p

    vol = base_volatility_pct
    if p < low_threshold:
        vol = max(0.3, vol * (0.75 + 0.1 * (p / max(low_threshold, 1e-6))))
    elif p > high_threshold:
        vol = min(3.0, vol * (1.0 + 0.3 * ((p - high_threshold) / max(1.0 - high_threshold, 1e-6))))

    size_mult = base_size_mult * (1.0 + defensive * 0.4)
    gamma_scale = 0.7 + p * 0.3

    book_spread = base_book_spread_pct
    if p < low_threshold and pressure.observed_l1_spread_pct > 0:
        book_spread = min(base_book_spread_pct, pressure.observed_l1_spread_pct)

    if p < 0.3:
        tag = "SCRAPE HARDER"
    elif p > 0.7:
        tag = "CAUTIOUS"
    else:
        tag = "NEUTRAL"

    rationale = (
        f"{tag}: pressure={p:.2f} vol={vol:.3f}% size_mult={size_mult:.2f} "
        f"gamma_scale={gamma_scale:.2f} book_spread={book_spread:.3f}%"
    )
    return PressureAdjustedInputs(
        volatility_pct=vol,
        size_mult=size_mult,
        gamma_scale=gamma_scale,
        book_spread_pct=book_spread,
        effective_pressure=p,
        rationale=rationale,
    )
