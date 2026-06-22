"""Liquidity depth helpers — slippage-aware book walking (no MM logic)."""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from alpha.types import BookLevel, LiquidityDepth, OrderBookSnapshot, utc_now


def _sorted_bids(levels: Sequence[BookLevel]) -> List[BookLevel]:
    return sorted(levels, key=lambda level: level.price, reverse=True)


def _sorted_asks(levels: Sequence[BookLevel]) -> List[BookLevel]:
    return sorted(levels, key=lambda level: level.price)


def depth_within_slippage(
    levels: Sequence[BookLevel],
    *,
    side: str,
    max_slippage_pct: float,
) -> float:
    """
    Sum XRP size walkable on one book side within max_slippage_pct of touch.

    - bid side: selling XRP into bids (price may fall from best bid)
    - ask side: buying XRP from asks (price may rise from best ask)
    """
    if not levels or max_slippage_pct <= 0:
        return 0.0

    if side == "bid":
        ordered = _sorted_bids(levels)
        touch = ordered[0].price
        if touch <= 0:
            return 0.0
        floor_price = touch * (1.0 - max_slippage_pct / 100.0)
        total = 0.0
        for level in ordered:
            if level.price < floor_price:
                break
            total += max(0.0, level.size_xrp)
        return total

    if side == "ask":
        ordered = _sorted_asks(levels)
        touch = ordered[0].price
        if touch <= 0:
            return 0.0
        ceiling = touch * (1.0 + max_slippage_pct / 100.0)
        total = 0.0
        for level in ordered:
            if level.price > ceiling:
                break
            total += max(0.0, level.size_xrp)
        return total

    raise ValueError(f"Unsupported side: {side}")


def compute_liquidity_depth(
    book: OrderBookSnapshot,
    *,
    max_slippage_pct: float,
) -> LiquidityDepth:
    bid_depth = depth_within_slippage(book.bids, side="bid", max_slippage_pct=max_slippage_pct)
    ask_depth = depth_within_slippage(book.asks, side="ask", max_slippage_pct=max_slippage_pct)
    return LiquidityDepth(
        max_slippage_pct=max_slippage_pct,
        bid_depth_xrp=bid_depth,
        ask_depth_xrp=ask_depth,
        best_bid=book.best_bid,
        best_ask=book.best_ask,
        mid=book.mid,
        spread_pct=book.spread_pct,
    )


def levels_from_book_dict(
    book: dict[str, Iterable[dict[str, float]]],
) -> tuple[tuple[BookLevel, ...], tuple[BookLevel, ...]]:
    bids = tuple(
        BookLevel(price=float(level["price"]), size_xrp=float(level["size"]))
        for level in book.get("bids", [])
        if float(level.get("price", 0)) > 0 and float(level.get("size", 0)) > 0
    )
    asks = tuple(
        BookLevel(price=float(level["price"]), size_xrp=float(level["size"]))
        for level in book.get("asks", [])
        if float(level.get("price", 0)) > 0 and float(level.get("size", 0)) > 0
    )
    return bids, asks


def build_order_book_snapshot(
    book: dict[str, Iterable[dict[str, float]]],
    *,
    best_bid: Optional[float],
    best_ask: Optional[float],
    mid: Optional[float],
) -> OrderBookSnapshot:
    bids, asks = levels_from_book_dict(book)
    spread: Optional[float] = None
    spread_pct: Optional[float] = None
    if best_bid is not None and best_ask is not None and best_bid > 0 and best_ask > 0:
        spread = best_ask - best_bid
        if mid and mid > 0:
            spread_pct = (spread / mid) * 100.0
    return OrderBookSnapshot(
        bids=bids,
        asks=asks,
        best_bid=best_bid,
        best_ask=best_ask,
        mid=mid,
        spread=spread,
        spread_pct=spread_pct,
        fetched_utc=utc_now(),
    )
