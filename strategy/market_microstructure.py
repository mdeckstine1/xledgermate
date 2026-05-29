"""Book pressure, momentum tiers, and market-edge assessment for defensive quoting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from core.perception import Profile


@dataclass(frozen=True)
class MomentumTier:
    name: str
    spread_mult: float
    size_mult: float
    pause_vulnerable: bool


@dataclass(frozen=True)
class BookPressure:
    label: str
    bid_spread_add_pct: float
    ask_spread_add_pct: float
    bid_size_mult: float
    ask_size_mult: float
    summary: str


@dataclass(frozen=True)
class MarketEdgeAssessment:
    book_spread_pct: float
    our_l1_spread_pct: float
    required_edge_pct: float
    capture_edge_pct: float
    met: bool
    summary: str


# |momentum| thresholds (% over lookback window).
_MOMENTUM_TIERS: Tuple[Tuple[float, MomentumTier], ...] = (
    (
        0.50,
        MomentumTier("extreme", 1.25, 0.20, True),
    ),
    (
        0.28,
        MomentumTier("strong", 0.90, 0.45, False),
    ),
    (
        0.12,
        MomentumTier("moderate", 0.55, 0.65, False),
    ),
    (
        0.04,
        MomentumTier("mild", 0.30, 0.82, False),
    ),
)


def classify_momentum(mid_momentum_pct: float) -> Tuple[MomentumTier, str]:
    """Return tier and vulnerable side note (rising mid → bids vulnerable)."""
    magnitude = abs(mid_momentum_pct)
    for threshold, tier in _MOMENTUM_TIERS:
        if magnitude >= threshold:
            if mid_momentum_pct > 0:
                note = f"momentum {tier.name} +{mid_momentum_pct:.2f}% → protect bids"
            elif mid_momentum_pct < 0:
                note = f"momentum {tier.name} {mid_momentum_pct:.2f}% → protect asks"
            else:
                note = "momentum flat"
            return tier, note
    return MomentumTier("none", 0.0, 1.0, False), "momentum flat"


def assess_book_pressure(
    *,
    depth_imbalance: float,
    sensitivity: float = 1.0,
) -> BookPressure:
    """
    depth_imbalance in [-1, 1]: positive = more bid depth (buy-side stacked).
    Heavy bid depth → price may rise → protect bids; heavy ask depth → protect asks.
    """
    imb = max(-1.0, min(1.0, depth_imbalance))
    strength = max(0.5, min(2.0, sensitivity))
    magnitude = abs(imb)

    if magnitude < 0.08:
        return BookPressure(
            label="balanced",
            bid_spread_add_pct=0.0,
            ask_spread_add_pct=0.0,
            bid_size_mult=1.0,
            ask_size_mult=1.0,
            summary="book pressure balanced",
        )

    if imb > 0:
        # Percentage points added to half-spread in OrderManager (÷100); keep small vs book.
        add = min(0.35, magnitude * 0.35 * strength)
        return BookPressure(
            label="bid_heavy",
            bid_spread_add_pct=add,
            ask_spread_add_pct=0.0,
            bid_size_mult=max(0.45, 1.0 - magnitude * 0.35 * strength),
            ask_size_mult=min(1.25, 1.0 + magnitude * 0.12 * strength),
            summary=f"bid-heavy book ({imb:+.0%}) → protect bids",
        )

    add = min(0.35, magnitude * 0.35 * strength)
    return BookPressure(
        label="ask_heavy",
        bid_spread_add_pct=0.0,
        ask_spread_add_pct=add,
        bid_size_mult=min(1.25, 1.0 + magnitude * 0.12 * strength),
        ask_size_mult=max(0.45, 1.0 - magnitude * 0.35 * strength),
        summary=f"ask-heavy book ({imb:+.0%}) → protect asks",
    )


def assess_market_edge(
    *,
    book_spread_pct: float,
    our_l1_spread_pct: float,
    min_edge_pct: float,
    xrpl_fee_bps: float = 2.0,
) -> MarketEdgeAssessment:
    """
    Defensive edge filter: require the live book to offer enough spread to cover
    fees + minimum profit, and ensure our L1 is not tighter than we can afford.
    """
    required = min_edge_pct + xrpl_fee_bps / 100.0
    half_book = max(0.0, book_spread_pct) / 2.0
    capture = half_book - required
    spread_ok = our_l1_spread_pct >= required
    book_ok = book_spread_pct >= required * 0.85
    met = spread_ok and book_ok

    if met:
        summary = (
            f"market edge OK (book {book_spread_pct:.3f}%, "
            f"L1 {our_l1_spread_pct:.3f}%, need {required:.3f}%)"
        )
    elif not book_ok:
        summary = (
            f"book too tight ({book_spread_pct:.3f}% < need ~{required:.3f}%) → defensive only"
        )
    else:
        summary = (
            f"our L1 too tight ({our_l1_spread_pct:.3f}% < need {required:.3f}%) → widen/shrink"
        )

    return MarketEdgeAssessment(
        book_spread_pct=book_spread_pct,
        our_l1_spread_pct=our_l1_spread_pct,
        required_edge_pct=required,
        capture_edge_pct=capture,
        met=met,
        summary=summary,
    )


def resolve_effective_min_edge_pct(
    *,
    profile: "Profile",
    edge_strictness: float = 1.0,
    book_spread_pct: float = 0.0,
    dynamic_enabled: bool = False,
) -> tuple[float, str]:
    """
    Option A: each profile owns a min edge target, scaled by operator strictness.
    Option C (optional): adapt required edge to live book spread (never above profile cap).
    """
    strictness = max(0.85, min(1.15, float(edge_strictness)))
    from core.profile_edge import profile_min_edge_pct

    baseline = profile_min_edge_pct(profile)
    profile_edge = baseline * strictness

    if not dynamic_enabled or book_spread_pct <= 0:
        return profile_edge, (
            f"Profile '{profile.name}' edge {profile_edge:.3f}% "
            f"(baseline {baseline:.2f}% × strictness {strictness:.2f})"
        )

    book_based = max(0.05, book_spread_pct * 0.55)
    effective = min(profile_edge, book_based)
    return effective, (
        f"Dynamic edge {effective:.3f}% — profile cap {profile_edge:.3f}%, "
        f"book {book_spread_pct:.3f}% → book-based {book_based:.3f}%"
    )
