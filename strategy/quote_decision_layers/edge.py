"""
Layer 3 — Profitable edge filter.

Solo books: hard gate — a side is off unless capture clears a relaxed solo threshold.
Crowded/sparse: no hard gate here; edge scales size only. Side ``allowed``
flags are set in Layer 5 only (intent, bleed, inventory, tape).

Solo vs crowded design:
  Solo books are acquisition-first: we accept reasonably good spread capture to
  grow inventory when the book is empty, while bleed (L4) and the L5 inventory
  circuit breaker (crowded/sparse only) still block clearly bad fills.
  Crowded/sparse books keep stricter net-edge standards — L3 never hard-blocks
  there, but size scales down on weak capture and L5 applies inventory/tape guards.
"""

from __future__ import annotations

from strategy.quote_decision_layers.types import BookMode, EdgeViability

# Percentage points (not bps) — matches assess_market_edge conventions.
FEE_PCT = 0.02  # ~2 bps XRPL round-trip cushion
ADVERSE_SOLO_PCT = 0.005
ADVERSE_CROWDED_PCT = 0.01
MIN_CAPTURE_SOLO_PCT = 0.01
MIN_CAPTURE_CROWDED_PCT = 0.025

# Solo acquisition gate tuning (Layer 3 hard gate only — crowded unchanged).
# Pass if capture >= min_edge * SOLO_EDGE_MULT OR capture >= SOLO_EDGE_ABSOLUTE_FLOOR_PCT.
SOLO_EDGE_MULT = 0.65
SOLO_EDGE_ABSOLUTE_FLOOR_PCT = 0.012  # 1.2 bps — blocks clearly negative EV tails

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


def solo_edge_viable(
    capture: float,
    min_edge: float,
    *,
    solo_edge_mult: float = SOLO_EDGE_MULT,
    solo_edge_absolute_floor_pct: float = SOLO_EDGE_ABSOLUTE_FLOOR_PCT,
) -> bool:
    """
    Solo hard gate — more permissive than full ``min_edge`` for acquisition MM.

    A side is viable when capture clears **either** bar (whichever is more permissive):
      - ``capture >= min_edge * solo_edge_mult`` (default 65% of net threshold)
      - ``capture >= solo_edge_absolute_floor_pct`` (default 1.2 bps absolute floor)

    Still rejects clearly sub-floor capture (e.g. 1.0 bps when floor is 1.2 bps).
    Crowded/sparse do not use this function — they keep the existing size-only path.
    """
    scaled = min_edge * solo_edge_mult
    return capture >= scaled or capture >= solo_edge_absolute_floor_pct


def evaluate_side_edge(
    *,
    side: str,
    book_spread_pct: float,
    our_half_spread_pct: float,
    profile_min_edge_pct: float,
    book_mode: BookMode,
    market_edge_met: bool,
    solo_edge_mult: float = SOLO_EDGE_MULT,
    solo_edge_absolute_floor_pct: float = SOLO_EDGE_ABSOLUTE_FLOOR_PCT,
) -> EdgeViability:
    """
    Should we quote this side?

    Solo (hard gate, acquisition-relaxed):
      - ``solo_edge_viable(capture, min_edge)`` — see module constants for tuning
      - ``market_edge_met`` is retained for callers/logging but does not further
        relax the solo threshold (superseded by ``solo_edge_mult``).

    Crowded/sparse (intentionally no hard gate):
      - Always ``viable=True``; insufficient capture only lowers size via
        ``edge_size_mult()``. Side pauses come from bleed, inventory, tape, and intent.
    """
    _ = side  # reserved for side-specific buffers if added later
    capture = side_capture_pct(
        book_spread_pct=book_spread_pct,
        our_half_spread_pct=our_half_spread_pct,
    )
    min_edge = min_net_edge_pct(
        book_mode=book_mode,
        profile_min_edge_pct=profile_min_edge_pct,
    )

    if book_mode != BookMode.SOLO:
        # Crowded/sparse: edge scales size only — stricter solo hard gate by design.
        # Aggregate market_edge_met is enforced via spread/size guards in quote_decision.py.
        return EdgeViability(
            implied_edge_pct=capture,
            min_edge_pct=min_edge,
            viable=True,
            reason="" if capture >= 0 else "marginal_capture",
        )

    if solo_edge_viable(
        capture,
        min_edge,
        solo_edge_mult=solo_edge_mult,
        solo_edge_absolute_floor_pct=solo_edge_absolute_floor_pct,
    ):
        return EdgeViability(
            implied_edge_pct=capture,
            min_edge_pct=min_edge,
            viable=True,
            reason="",
        )

    scaled = min_edge * solo_edge_mult
    return EdgeViability(
        implied_edge_pct=capture,
        min_edge_pct=min_edge,
        viable=False,
        reason=(
            f"edge_gate capture@{capture:.3f}%"
            f"<scaled@{scaled:.3f}%|floor@{solo_edge_absolute_floor_pct:.3f}%"
        ),
    )


def edge_size_mult(*, edge_pct: float, book_mode: BookMode) -> float:
    """Better edge → larger size (bounded)."""
    if edge_pct <= 0:
        return EDGE_SIZE_FLOOR
    ref = EDGE_SIZE_REF_PCT * (1.25 if book_mode != BookMode.SOLO else 1.0)
    mult = EDGE_SIZE_FLOOR + (edge_pct / ref) * (EDGE_SIZE_CEILING - EDGE_SIZE_FLOOR)
    return round(min(EDGE_SIZE_CEILING, max(EDGE_SIZE_FLOOR, mult)), 3)
