"""Reservation vs BBO measurement helpers (additive; no A-S math)."""

from __future__ import annotations

from typing import Any, Dict, Optional


def reservation_quote_sides(
    *,
    reservation: float,
    best_bid: float,
    best_ask: float,
) -> tuple[bool, bool, str]:
    """
    Permitted L1 legs from reservation vs touch (pure MM posture).

    When reservation sits outside the touch band, quote the rebalancing side only:
    - below/at bid → ask-only (sell XRP when RLUSD-heavy skew pushed reservation down)
    - above/at ask → bid-only (buy XRP when XRP-heavy skew pushed reservation up)
    - strictly inside → two-sided
    """
    if best_bid < reservation < best_ask:
        return True, True, "inside"
    if reservation <= best_bid:
        return False, True, "below_bid"
    if reservation >= best_ask:
        return True, False, "above_ask"
    return False, False, "invalid"


def effective_quote_sides(
    *,
    allow_bid: bool,
    allow_ask: bool,
    pause_bids: bool,
    pause_asks: bool,
) -> tuple[bool, bool, str]:
    """
    Merge reservation posture with inventory one-sided bailout.

    Inventory rebalancing (pause one side) must still quote on book when reservation
    sits outside touch on the opposite side — e.g. rlusd_heavy → bid-only even if
    reservation is below bid (A-S would otherwise ask-only into wrong direction).
    """
    inv_bid_only = pause_asks and not pause_bids
    inv_ask_only = pause_bids and not pause_asks
    eff_bid = (allow_bid or inv_bid_only) and not pause_bids
    eff_ask = (allow_ask or inv_ask_only) and not pause_asks
    if eff_bid and eff_ask:
        if allow_bid and allow_ask:
            label = "inside"
        else:
            label = "two_sided"
    elif eff_bid:
        label = "bid_only_rebalance" if inv_bid_only else "bid_only_skew"
    elif eff_ask:
        label = "ask_only_rebalance" if inv_ask_only else "ask_only_skew"
    else:
        label = "blocked"
    return eff_bid, eff_ask, label


def reservation_bbo_metrics(
    *,
    reservation: Optional[float],
    best_bid: Optional[float],
    best_ask: Optional[float],
    mid: Optional[float],
) -> Optional[Dict[str, Any]]:
    """
    Signed distance from reservation to nearest BBO touch, in bps vs mid.

    - Inside L1: positive +min(res−bid, ask−res) / mid × 10_000
    - Outside L1: negative −min(|res−bid|, |res−ask|) / mid × 10_000
    """
    if reservation is None or best_bid is None or best_ask is None or mid is None:
        return None
    if mid <= 0 or best_bid <= 0 or best_ask <= 0:
        return None

    inside = best_bid < reservation < best_ask
    if inside:
        delta = min(reservation - best_bid, best_ask - reservation)
        bps = delta / mid * 10_000.0
    else:
        delta = min(abs(reservation - best_bid), abs(reservation - best_ask))
        bps = -delta / mid * 10_000.0

    return {
        "inside_l1": inside,
        "reservation_to_bbo_delta_bps": round(bps, 2),
    }


def format_reservation_bbo_delta(bps: Optional[float], *, inside_l1: Optional[bool] = None) -> str:
    """HUD-friendly label: inside +4.2 bps / outside −11.8 bps."""
    if bps is None:
        return "—"
    sign = "+" if bps >= 0 else ""
    label = "inside" if inside_l1 is True else ("outside" if inside_l1 is False else "")
    prefix = f"{label} " if label else ""
    return f"{prefix}{sign}{bps:.1f} bps"


def enrich_runtime_reservation_metrics(runtime: Dict[str, Any]) -> Dict[str, Any]:
    """Merge reservation BBO metrics into a runtime/HUD dict (idempotent)."""
    rt = dict(runtime)
    if rt.get("reservation_to_bbo_delta_bps") is not None and rt.get("inside_l1") is not None:
        return rt
    metrics = reservation_bbo_metrics(
        reservation=_f(rt.get("as_reservation")),
        best_bid=_f(rt.get("best_bid_rlusd_per_xrp") or rt.get("best_bid")),
        best_ask=_f(rt.get("best_ask_rlusd_per_xrp") or rt.get("best_ask")),
        mid=_f(rt.get("mid_price") or rt.get("mid")),
    )
    if metrics:
        rt.update(metrics)
    return rt


def _f(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
