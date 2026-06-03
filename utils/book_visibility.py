"""How visible bot quotes are vs the live XRPL book touch."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence

# Beyond this distance from touch, the offer is effectively invisible in the queue.
VISIBLE_MAX_BPS = 8.0


def offer_vs_touch_bps(
    *,
    side: str,
    price: float,
    best_bid: float | None,
    best_ask: float | None,
) -> Optional[float]:
    """
    Signed distance from touch in basis points.

    Bids: negative = below best bid (worse queue position).
    Asks: positive = above best ask (worse queue position).
    """
    if price <= 0:
        return None
    side_l = str(side).lower()
    if side_l == "bid" and best_bid is not None and best_bid > 0:
        return (price - best_bid) / best_bid * 10_000.0
    if side_l == "ask" and best_ask is not None and best_ask > 0:
        return (price - best_ask) / best_ask * 10_000.0
    return None


def enrich_open_offers(
    offers: Sequence[Any],
    *,
    best_bid: float | None,
    best_ask: float | None,
) -> list[dict[str, Any]]:
    """Attach vs_touch_bps to each ledger offer for GUI / runtime state."""
    rows: list[dict[str, Any]] = []
    for offer in offers:
        if isinstance(offer, Mapping):
            side = str(offer.get("side", ""))
            price = float(offer.get("price", 0))
            seq = int(offer.get("sequence", 0))
            size = float(offer.get("size_xrp", 0))
        else:
            side = str(getattr(offer, "side", ""))
            price = float(getattr(offer, "price", 0))
            seq = int(getattr(offer, "sequence", 0))
            size = float(getattr(offer, "size_xrp", 0))
        bps = offer_vs_touch_bps(
            side=side, price=price, best_bid=best_bid, best_ask=best_ask
        )
        rows.append(
            {
                "sequence": seq,
                "side": side,
                "price": price,
                "size_xrp": size,
                "vs_touch_bps": bps,
            }
        )
    return rows


def quote_visibility(
    offers: Iterable[Mapping[str, Any]],
    *,
    max_visible_bps: float = VISIBLE_MAX_BPS,
) -> tuple[bool, float, str]:
    """
    Returns (at_touch, worst_abs_bps, human summary).

    Empty book → at_touch True (nothing to fix).
    """
    worst = 0.0
    count = 0
    for offer in offers:
        bps = offer.get("vs_touch_bps")
        if bps is None:
            continue
        count += 1
        # Penalize distance from touch on the wrong side of the book.
        if str(offer.get("side", "")).lower() == "bid":
            penalty = max(0.0, -float(bps))
        else:
            penalty = max(0.0, float(bps))
        worst = max(worst, penalty)

    if count == 0:
        return True, 0.0, "No open offers on the ledger."

    at_touch = worst <= max_visible_bps
    if at_touch:
        return True, worst, f"In the queue — within {worst:.1f} bps of touch."

    return (
        False,
        worst,
        f"Off the storefront — worst quote is {worst:.1f} bps behind touch "
        f"(>{max_visible_bps:.0f} bps is invisible to takers).",
    )
