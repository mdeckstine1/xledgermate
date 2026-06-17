"""Sacred A-S gate checks — reservation inside L1 only; advisory paths must not override."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def sacred_reservation_inside_l1(
    *,
    reservation: float,
    best_bid: float,
    best_ask: float,
) -> bool:
    return best_bid < reservation < best_ask


def enforce_reservation_gate(
    *,
    would_quote_reservation: bool,
    reservation: float,
    best_bid: float,
    best_ask: float,
    context: str = "pure_quote_path",
) -> bool:
    """
    Verify would_quote_reservation matches the sacred inside-L1 rule.
    Does not apply to pause_bids/pause_asks or final quote_count.
    """
    sacred = sacred_reservation_inside_l1(
        reservation=reservation,
        best_bid=best_bid,
        best_ask=best_ask,
    )
    if would_quote_reservation != sacred:
        logger.error(
            "ADVISORY_WOULD_QUOTE_OVERRIDE_BLOCKED context=%s computed=%s sacred=%s "
            "reservation=%.8f bid=%.8f ask=%.8f",
            context,
            would_quote_reservation,
            sacred,
            reservation,
            best_bid,
            best_ask,
        )
        return sacred
    return would_quote_reservation
