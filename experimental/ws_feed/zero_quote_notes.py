"""
B4 — Operator clarity for 0-quote and tight-book decisions (pure WS path).

Explains why the bot did or did not quote: reservation vs touch, optimal vs book,
spread floor binding. Never changes would_quote — display and summary only.
"""

from __future__ import annotations

from typing import Optional

from experimental.ws_runtime_analysis import (
    STALE_CROSS_ZERO_REASON,
    classify_zero_quote_reason,
)


def spread_floor_binding(
    optimal_spread_pct: float,
    min_spread_floor_pct: float,
    *,
    tolerance_pct: float = 0.008,
) -> bool:
    """True when optimal spread is pinned at the configured floor."""
    return abs(optimal_spread_pct - min_spread_floor_pct) <= tolerance_pct


def build_tight_book_advisory(
    *,
    would_quote: bool,
    zero_quote_reason: str,
    reservation: float,
    best_bid: float,
    best_ask: float,
    book_spread_pct: float,
    optimal_spread_pct: float,
    min_spread_floor_pct: float,
) -> str:
    """One-line operator note for HUD / decision summary."""
    gap = optimal_spread_pct - book_spread_pct
    floor_note = ""
    if spread_floor_binding(optimal_spread_pct, min_spread_floor_pct):
        floor_note = f" spread floor {min_spread_floor_pct:.2f}% binding"

    if would_quote:
        if reservation <= best_bid:
            return (
                f"ONE-SIDED ask-only: reservation {reservation:.6f} at/below bid {best_bid:.6f} "
                f"— inventory skew; posting sell side inside L1.{floor_note}"
            )
        if reservation >= best_ask:
            return (
                f"ONE-SIDED bid-only: reservation {reservation:.6f} at/above ask {best_ask:.6f} "
                f"— inventory skew; posting buy side inside L1.{floor_note}"
            )
        if gap > 0.01:
            return (
                f"TIGHT OK: optimal {optimal_spread_pct:.3f}% > book {book_spread_pct:.3f}% "
                f"(gap {gap:.3f}%) but reservation inside L1 — quoting.{floor_note}"
            )
        return ""

    if zero_quote_reason == "reservation_outside_l1":
        if reservation <= best_bid:
            side = f"reservation {reservation:.6f} at/below bid {best_bid:.6f}"
        elif reservation >= best_ask:
            side = f"reservation {reservation:.6f} at/above ask {best_ask:.6f}"
        else:
            side = "reservation not strictly inside L1"
        hint = "Inventory or vol skew pushed fair value outside the touch."
        if gap > 0.01:
            hint += f" Optimal spread also wider than book (gap {gap:.3f}%)."
        return f"BLOCKED — {side}. {hint}{floor_note}"

    if zero_quote_reason == "optimal_spread_wider_than_book":
        return (
            f"BLOCKED — A-S wants {optimal_spread_pct:.3f}% spread vs book "
            f"{book_spread_pct:.3f}% (gap {gap:.3f}%). Cannot sit inside L1 at required width.{floor_note}"
        )

    if zero_quote_reason == "quoted":
        return ""

    if zero_quote_reason == STALE_CROSS_ZERO_REASON:
        return (
            "STALE-CROSS — reservation was inside L1 at WS sample but outside after "
            "competitor/intel scrape refresh. Advisory only until M3 engine flag ships."
        )

    return f"BLOCKED — {zero_quote_reason} ({gap:.3f}% optimal−book gap).{floor_note}"


def classify_and_explain_pure_zero_quote(
    *,
    would_quote: bool,
    best_bid: float,
    best_ask: float,
    reservation: float,
    book_spread_pct: float,
    optimal_spread_pct: float,
    min_spread_floor_pct: float,
    pause_bids: bool = False,
    pause_asks: bool = False,
) -> tuple[str, str, str]:
    """
    Returns (reason, detail, operator_note).
    """
    reason = classify_zero_quote_reason(
        would_quote=would_quote,
        best_bid=best_bid,
        best_ask=best_ask,
        reservation=reservation,
        book_spread_pct=book_spread_pct,
        optimal_spread_pct=optimal_spread_pct,
        pause_bids=pause_bids,
        pause_asks=pause_asks,
    )

    detail = _detail_for_reason(
        reason,
        reservation=reservation,
        best_bid=best_bid,
        best_ask=best_ask,
        book_spread_pct=book_spread_pct,
        optimal_spread_pct=optimal_spread_pct,
        min_spread_floor_pct=min_spread_floor_pct,
    )

    operator = build_tight_book_advisory(
        would_quote=would_quote,
        zero_quote_reason=reason,
        reservation=reservation,
        best_bid=best_bid,
        best_ask=best_ask,
        book_spread_pct=book_spread_pct,
        optimal_spread_pct=optimal_spread_pct,
        min_spread_floor_pct=min_spread_floor_pct,
    )

    return reason, detail, operator


def _detail_for_reason(
    reason: str,
    *,
    reservation: float,
    best_bid: float,
    best_ask: float,
    book_spread_pct: float,
    optimal_spread_pct: float,
    min_spread_floor_pct: float,
) -> str:
    if reason == "reservation_outside_l1":
        if reservation <= best_bid:
            return f"reservation {reservation:.6f} <= bid {best_bid:.6f}"
        if reservation >= best_ask:
            return f"reservation {reservation:.6f} >= ask {best_ask:.6f}"
        return "reservation not strictly inside L1"
    if reason == "optimal_spread_wider_than_book":
        extra = ""
        if spread_floor_binding(optimal_spread_pct, min_spread_floor_pct):
            extra = f"; floor {min_spread_floor_pct:.2f}% binding"
        return (
            f"optimal {optimal_spread_pct:.3f}% > book {book_spread_pct:.3f}%"
            f" (gap {optimal_spread_pct - book_spread_pct:.3f}%){extra}"
        )
    if reason == "quoted":
        gap = optimal_spread_pct - book_spread_pct
        if gap > 0.01:
            return f"reservation inside L1; optimal wider than book by {gap:.3f}%"
        return "reservation inside L1"
    if reason == STALE_CROSS_ZERO_REASON:
        return "reservation crossed BBO during intel scrape window"
    return reason
