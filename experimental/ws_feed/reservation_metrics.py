"""Reservation vs BBO measurement helpers (additive; no A-S math)."""

from __future__ import annotations

from typing import Any, Dict, Optional


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
