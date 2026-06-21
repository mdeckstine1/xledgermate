"""
Layer 3 — Profitable edge filter.

Solo books: hard gate — a side is off unless capture clears net edge (fees + adverse).
Crowded/sparse: no hard gate here; edge scales size only. Side ``allowed``
flags are set in Layer 5 only (intent, bleed, inventory, tape).
"""

from __future__ import annotations

from strategy.quote_decision_layers.types import BookMode, EdgeViability

# Percentage points (not bps) — matches assess_market_edge conventions.
FEE_PCT = 0.02  # ~2 bps XRPL round-trip cushion
ADVERSE_SOLO_PCT = 0.005
ADVERSE_CROWDED_PCT = 0.01
MIN_CAPTURE_SOLO_PCT = 0.01
MIN_CAPTURE_CROWDED_PCT = 0.025

EDGE_SIZE_FLOOR = 0.65
EDGE_SIZE_CEILING = 1.15
EDGE_SIZE_REF_PCT = 0.08


def min_net_edge_pct(*, book_mode: BookMode, profile_min_edge_pct: float) -> float:
    """Net threshold: profile min edge + fees + adverse buffer (solo softer)."""
    adverse = ADVERSE_SOLO_PCT if book_mode == BookMode.SOLO else ADVERSE_CROWDED_PCT
    floor = MIN_CAPTURE_SOLO_PCT if book_mode == BookMode.SOLO else MIN_CAPTURE_CROWDED_PCT
    return max(floor, profile_min_edge_pct + FEE_PCT + adverse)


def side_capture_pct(
    *,
    book_spread_pct: float,
    our_half_spread_pct: float,
) -> float:
    """Spread capture for one side before fee/adverse buffers."""
    half_book = max(0.0, book_spread_pct) / 2.0
    return half_book - our_half_spread_pct


def evaluate_side_edge(
    *,
    side: str,
    book_spread_pct: float,
    our_half_spread_pct: float,
    profile_min_edge_pct: float,
    book_mode: BookMode,
    market_edge_met: bool,
) -> EdgeViability:
    """
    Should we quote this side?

    Solo (hard gate):
      - ``capture >= min_edge`` normally (net-profitable after fees + adverse buffer)
      - ``capture >= min_edge * 0.75`` when ``market_edge_met`` (softer floor when
        aggregate book edge already passes)

    Crowded/sparse (intentionally no hard gate):
      - Always ``viable=True``; insufficient capture only lowers size via
        ``edge_size_mult()``. Side pauses come from bleed, inventory, tape, and intent.
    """
    capture = side_capture_pct(
        book_spread_pct=book_spread_pct,
        our_half_spread_pct=our_half_spread_pct,
    )
    min_edge = min_net_edge_pct(
        book_mode=book_mode,
        profile_min_edge_pct=profile_min_edge_pct,
    )

    if book_mode != BookMode.SOLO:
        # Crowded/sparse: edge scales size only — weaker than solo hard gate by design.
        # Aggregate market_edge_met is enforced via spread/size guards in quote_decision.py.
        return EdgeViability(
            implied_edge_pct=capture,
            min_edge_pct=min_edge,
            viable=True,
            reason="" if capture >= 0 else "marginal_capture",
        )

    threshold = min_edge * 0.75 if market_edge_met else min_edge
    if capture >= threshold:
        return EdgeViability(
            implied_edge_pct=capture,
            min_edge_pct=min_edge,
            viable=True,
            reason="",
        )

    return EdgeViability(
        implied_edge_pct=capture,
        min_edge_pct=min_edge,
        viable=False,
        reason=f"edge_gate capture@{capture:.3f}%<{threshold:.3f}%",
    )


def edge_size_mult(*, edge_pct: float, book_mode: BookMode) -> float:
    """Better edge → larger size (bounded)."""
    if edge_pct <= 0:
        return EDGE_SIZE_FLOOR
    ref = EDGE_SIZE_REF_PCT * (1.25 if book_mode != BookMode.SOLO else 1.0)
    mult = EDGE_SIZE_FLOOR + (edge_pct / ref) * (EDGE_SIZE_CEILING - EDGE_SIZE_FLOOR)
    return round(min(EDGE_SIZE_CEILING, max(EDGE_SIZE_FLOOR, mult)), 3)
