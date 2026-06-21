"""Solo L3 edge gate — acquisition-relaxed threshold vs crowded unchanged."""

from __future__ import annotations

import pytest

from strategy.quote_decision_layers.edge import (
    SOLO_EDGE_ABSOLUTE_FLOOR_PCT,
    SOLO_EDGE_MULT,
    evaluate_side_edge,
    min_net_edge_pct,
    solo_edge_viable,
)
from strategy.quote_decision_layers.types import BookMode


def test_solo_edge_constants_defaults() -> None:
    assert SOLO_EDGE_MULT == 0.65
    assert SOLO_EDGE_ABSOLUTE_FLOOR_PCT == 0.012


def test_solo_edge_viable_or_logic() -> None:
    min_edge = 0.025
    assert solo_edge_viable(0.013, min_edge)  # absolute floor
    assert solo_edge_viable(0.017, min_edge)  # scaled 0.01625
    assert not solo_edge_viable(0.010, min_edge)


def test_before_after_marginal_solo_capture() -> None:
    """
    Before (full min_edge 2.5%): capture 1.3% → blocked.
    After (solo acquire gate): capture 1.3% → viable.
    """
    min_edge = min_net_edge_pct(book_mode=BookMode.SOLO, profile_min_edge_pct=0.0)
    capture = 0.013
    assert capture < min_edge
    result = evaluate_side_edge(
        side="bid",
        book_spread_pct=0.07,
        our_half_spread_pct=0.022,
        profile_min_edge_pct=0.0,
        book_mode=BookMode.SOLO,
        market_edge_met=False,
    )
    assert result.implied_edge_pct == pytest.approx(capture)
    assert result.viable


def test_solo_edge_mult_configurable() -> None:
    """Tighter mult blocks capture that looser mult allows (high floor isolates mult)."""
    kwargs = dict(
        side="bid",
        book_spread_pct=0.07,
        our_half_spread_pct=0.021,
        profile_min_edge_pct=0.0,
        book_mode=BookMode.SOLO,
        market_edge_met=False,
        solo_edge_absolute_floor_pct=0.015,
    )
    # capture = 0.014 — passes 0.50×min (0.0125), fails 0.65×min (0.01625) and floor (0.015)
    assert evaluate_side_edge(**kwargs, solo_edge_mult=0.50).viable
    assert not evaluate_side_edge(**kwargs, solo_edge_mult=0.65).viable


def test_crowded_unchanged_negative_capture_still_viable() -> None:
    result = evaluate_side_edge(
        side="bid",
        book_spread_pct=0.04,
        our_half_spread_pct=0.03,
        profile_min_edge_pct=0.08,
        book_mode=BookMode.CROWDED,
        market_edge_met=False,
    )
    assert result.implied_edge_pct < 0
    assert result.viable
