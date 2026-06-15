"""
G4 (E.4) — peer-lane pressure → size_mult / side bias in PureQuotePath.

Advisory only: never touches reservation or would_quote.
Empty peer lane → neutral pressure (no whale inheritance).
Brake-only size reductions; fled-touch → modest side bias toward rebalance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.5) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def prepare_quoting_intel(intel: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Normalize competitor intel for quoting: peer-lane pressure/spread only.

    When the peer lane is empty, force neutral pressure (0.5) so book-wide
    top-N activity does not steer sizes.
    """
    if not intel:
        return None
    out: Dict[str, Any] = dict(intel)
    if "peer_lane_count" not in intel and "peer_lane_empty" not in intel:
        return out

    peer_count = _safe_int(intel.get("peer_lane_count"))
    peer_empty = bool(intel.get("peer_lane_empty")) or peer_count <= 0

    if peer_empty:
        out["competitor_pressure"] = 0.5
        out["peer_competitor_pressure"] = 0.5
        return out

    peer_p = intel.get("peer_pressure_score")
    if peer_p is not None:
        out["competitor_pressure"] = _safe_float(peer_p)
        out["peer_competitor_pressure"] = out["competitor_pressure"]

    peer_spread = intel.get("peer_observed_spread_pct")
    if peer_spread is not None and _safe_float(peer_spread, 0.0) > 0:
        out["competitor_observed_spread_pct"] = _safe_float(peer_spread)

    return out


@dataclass(frozen=True)
class G4Adjustments:
    size_mult: float = 1.0
    bid_size_mult: float = 1.0
    ask_size_mult: float = 1.0
    active: bool = False
    grade: str = "neutral"
    summary: str = ""
    peer_lane_count: int = 0
    peer_pressure: Optional[float] = None


def compute_g4_adjustments(
    intel: Optional[Mapping[str, Any]],
    *,
    inventory_skew: float = 0.0,
    inventory_label: str = "",
    g2_size_mult: float = 1.0,
) -> G4Adjustments:
    """Peer-lane structural nudges after competitor pressure + G2 (brake-only size)."""
    if not intel:
        return G4Adjustments()

    if "peer_lane_count" not in intel and "peer_lane_empty" not in intel:
        return G4Adjustments()

    peer_count = _safe_int(intel.get("peer_lane_count"))
    peer_empty = bool(intel.get("peer_lane_empty")) or peer_count <= 0

    if peer_empty:
        return G4Adjustments(
            grade="empty_lane",
            summary="G4 neutral — empty peer lane",
            peer_lane_count=0,
            peer_pressure=0.5,
        )

    peer_p = _safe_float(
        intel.get("peer_pressure_score") or intel.get("competitor_pressure"),
        0.5,
    )
    fled = _safe_int(intel.get("peer_fled_touch_count"))
    widened = bool(intel.get("peer_lane_widened"))

    size_mult = 1.0
    bid_m = 1.0
    ask_m = 1.0
    active = False
    grade = "neutral"
    parts: list[str] = []

    if peer_p > 0.65:
        size_mult = 0.92
        active = True
        grade = "cautious"
        parts.append(f"high peer pressure {peer_p:.2f}")
    elif widened:
        size_mult = 0.96
        active = True
        grade = "sparse"
        parts.append("widened peer band")

    label = (inventory_label or "").lower()
    if peer_p < 0.4 and fled >= 1:
        active = True
        if grade == "neutral":
            grade = "skim"
        fled_boost = min(0.06, 0.02 * min(fled, 3))
        if inventory_skew > 0.1 or "xrp_heavy" in label:
            ask_m = 1.0 + fled_boost
            parts.append(f"peer fled×{fled} ask+{fled_boost:.0%}")
        elif inventory_skew < -0.1 or "rlusd_heavy" in label:
            bid_m = 1.0 + fled_boost
            parts.append(f"peer fled×{fled} bid+{fled_boost:.0%}")
        else:
            parts.append(f"peer fled×{fled} balanced")

    if g2_size_mult < 0.95:
        bid_m = min(bid_m, 1.0)
        ask_m = min(ask_m, 1.0)

    size_mult = min(1.0, size_mult)
    bid_m = _clamp(bid_m, 0.85, 1.08)
    ask_m = _clamp(ask_m, 0.85, 1.08)

    summary = f"G4 {grade}"
    if parts:
        summary += ": " + "; ".join(parts)

    return G4Adjustments(
        size_mult=size_mult,
        bid_size_mult=bid_m,
        ask_size_mult=ask_m,
        active=active or grade != "neutral",
        grade=grade,
        summary=summary,
        peer_lane_count=peer_count,
        peer_pressure=round(peer_p, 3),
    )
