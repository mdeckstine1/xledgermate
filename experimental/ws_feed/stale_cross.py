"""M3 lab helper — detect reservation stale-cross across WS sample windows."""

from __future__ import annotations

from typing import Optional


def reservation_inside_l1(
    reservation: Optional[float],
    best_bid: Optional[float],
    best_ask: Optional[float],
) -> bool:
    if reservation is None or best_bid is None or best_ask is None:
        return False
    if best_bid <= 0 or best_ask <= 0:
        return False
    return best_bid < reservation < best_ask


def detect_stale_cross(
    *,
    reservation: Optional[float],
    best_bid_before: Optional[float],
    best_ask_before: Optional[float],
    best_bid_after: Optional[float],
    best_ask_after: Optional[float],
) -> bool:
    """
    True when reservation was inside pre-scrape BBO but not inside post-scrape BBO.

    Engine M3 will set `reservation_crossed_after_ws_sample` using the same rule.
    """
    inside_before = reservation_inside_l1(reservation, best_bid_before, best_ask_before)
    inside_after = reservation_inside_l1(reservation, best_bid_after, best_ask_after)
    return inside_before and not inside_after
