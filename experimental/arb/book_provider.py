"""Sync XRPL book_offers mid for token/XRP pairs (read-only)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

XRP_DROPS = 1_000_000.0


def _xrp_amount(field: Any) -> Optional[float]:
    if isinstance(field, str) and field.isdigit():
        return int(field) / XRP_DROPS
    if isinstance(field, dict):
        try:
            return float(field.get("value") or 0)
        except (TypeError, ValueError):
            return None
    return None


def _token_amount(field: Any) -> Optional[float]:
    if isinstance(field, dict):
        try:
            return float(field.get("value") or 0)
        except (TypeError, ValueError):
            return None
    return None


def _offer_price_stable_per_xrp(gets: Any, pays: Any) -> Optional[float]:
    """RLUSD/USDC/USD per XRP from offer legs."""
    if isinstance(gets, str) and isinstance(pays, dict):
        xrp = _xrp_amount(gets)
        tok = _token_amount(pays)
        if xrp and xrp > 0 and tok is not None:
            return tok / xrp
    if isinstance(gets, dict) and isinstance(pays, str):
        xrp = _xrp_amount(pays)
        tok = _token_amount(gets)
        if xrp and xrp > 0 and tok is not None:
            return tok / xrp
    return None


def _book_offers(rpc_url: str, *, taker_gets: dict, taker_pays: dict, limit: int = 10) -> List[dict]:
    try:
        import requests
    except ImportError:
        return []
    payload = {
        "method": "book_offers",
        "params": [
            {
                "taker_gets": taker_gets,
                "taker_pays": taker_pays,
                "limit": limit,
                "ledger_index": "validated",
            }
        ],
    }
    try:
        resp = requests.post(rpc_url, json=payload, timeout=15)
        resp.raise_for_status()
        body = resp.json()
    except Exception as exc:
        logger.debug("book_offers failed: %s", exc)
        return []
    if body.get("error"):
        return []
    return list((body.get("result") or {}).get("offers") or [])


def fetch_token_xrp_book_mid_sync(
    *,
    rpc_url: str,
    currency: str,
    issuer: str,
    limit: int = 10,
) -> Dict[str, Any]:
    """Best bid/ask/mid for stable (or IOU) per XRP."""
    token = {"currency": currency, "issuer": issuer}
    xrp = {"currency": "XRP"}
    asks_raw = _book_offers(rpc_url, taker_gets=xrp, taker_pays=token, limit=limit)
    bids_raw = _book_offers(rpc_url, taker_gets=token, taker_pays=xrp, limit=limit)

    ask_prices = []
    for o in asks_raw:
        p = _offer_price_stable_per_xrp(o.get("TakerGets"), o.get("TakerPays"))
        if p and p > 0:
            ask_prices.append(p)
    bid_prices = []
    for o in bids_raw:
        p = _offer_price_stable_per_xrp(o.get("TakerGets"), o.get("TakerPays"))
        if p and p > 0:
            bid_prices.append(p)

    best_ask = min(ask_prices) if ask_prices else None
    best_bid = max(bid_prices) if bid_prices else None
    mid = spread = spread_pct = None
    if best_bid and best_ask and best_bid > 0 and best_ask > 0 and best_bid <= best_ask:
        mid = (best_bid + best_ask) / 2.0
        spread = best_ask - best_bid
        spread_pct = spread / mid * 100.0 if mid else None
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid,
        "spread": spread,
        "spread_pct": spread_pct,
        "bid_depth": len(bid_prices),
        "ask_depth": len(ask_prices),
    }


def fetch_stable_cross_book_mid_sync(
    *,
    rpc_url: str,
    base_currency: str,
    base_issuer: str,
    quote_currency: str,
    quote_issuer: str,
    limit: int = 10,
) -> Dict[str, Any]:
    """Mid for base per quote (e.g. RLUSD per USDC) from direct offers."""
    base = {"currency": base_currency, "issuer": base_issuer}
    quote = {"currency": quote_currency, "issuer": quote_issuer}
    # taker gets base, pays quote -> buy base with quote -> ask side for base
    asks_raw = _book_offers(rpc_url, taker_gets=base, taker_pays=quote, limit=limit)
    bids_raw = _book_offers(rpc_url, taker_gets=quote, taker_pays=base, limit=limit)

    def base_per_quote(gets: Any, pays: Any) -> Optional[float]:
        b = _token_amount(gets) if isinstance(gets, dict) else None
        q = _token_amount(pays) if isinstance(pays, dict) else None
        if b and q and q > 0:
            return b / q
        b = _token_amount(pays) if isinstance(pays, dict) else None
        q = _token_amount(gets) if isinstance(gets, dict) else None
        if b and q and q > 0:
            return b / q
        return None

    ask_prices = [p for o in asks_raw if (p := base_per_quote(o.get("TakerGets"), o.get("TakerPays")))]
    bid_prices = [p for o in bids_raw if (p := base_per_quote(o.get("TakerGets"), o.get("TakerPays")))]
    best_ask = min(ask_prices) if ask_prices else None
    best_bid = max(bid_prices) if bid_prices else None
    mid = None
    if best_bid and best_ask and best_bid <= best_ask:
        mid = (best_bid + best_ask) / 2.0
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid,
        "bid_depth": len(bid_prices),
        "ask_depth": len(ask_prices),
    }
