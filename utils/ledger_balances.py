"""Read bot wallet balances directly from XRPL (align GUI with Xaman on the same r-address)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from config.settings import BotConfig
from connectors.xrpl_connector import XRPLConnector, XRPLNetworkConfig
from connectors.xrpl_connector import is_trustworthy_rlusd_mid
from core.market_conditions import compute_book_spread_pct
from utils.book_visibility import enrich_open_offers
from utils.gui_errors import format_ledger_sync_error
from utils.gui_runtime_sync import patch_runtime_state_file
from utils.xrpl_currency import RLUSD_CURRENCY_HEX, resolve_rlusd_currency_code

logger = logging.getLogger(__name__)


async def fetch_ledger_wallet_snapshot(
    config: BotConfig | None = None,
) -> Dict[str, Any]:
    """Validated-ledger XRP + RLUSD for the configured bot account."""
    cfg = config or BotConfig.load()
    address = cfg.bot_account_address.strip()
    if not address:
        raise ValueError("Set bot_account_address in config.")

    currency_code = resolve_rlusd_currency_code(cfg.rlusd_currency)
    if currency_code.upper() == "RLUSD":
        currency_code = RLUSD_CURRENCY_HEX

    connector = XRPLConnector(
        account_address=address,
        secret=None,
        rlusd_issuer=cfg.resolved_rlusd_issuer(),
        rlusd_currency=currency_code,
        network=XRPLNetworkConfig(json_rpc_url=cfg.resolved_rpc_url()),
    )

    xrp = await connector.get_xrp_balance()
    trust = await connector.get_rlusd_trust_line()
    rlusd = float(trust.balance) if trust.exists else 0.0

    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    mid: Optional[float] = None
    book_spread_pct: Optional[float] = None
    book_note: Optional[str] = None

    try:
        order_book = await connector.fetch_xrp_rlusd_order_book()
        best_bid, best_ask = connector.compute_best_prices(order_book)
        mid_raw = connector.compute_mid_price(order_book)
        if mid_raw is not None and is_trustworthy_rlusd_mid(
            mid_raw, best_bid=best_bid, best_ask=best_ask
        ):
            mid = float(mid_raw)
            book_spread_pct = compute_book_spread_pct(best_bid, best_ask)
        elif mid_raw is not None:
            book_note = "book mid crossed or unreliable — balances only"
    except Exception as exc:
        book_note = format_ledger_sync_error(exc)
        logger.warning("Ledger book fetch skipped: %s", book_note)

    portfolio_xrp = xrp + (rlusd / mid if mid and mid > 0 else 0.0)

    open_offers = await connector.get_open_offers()
    enriched_offers = enrich_open_offers(
        open_offers, best_bid=best_bid, best_ask=best_ask
    )

    out: Dict[str, Any] = {
        "balance_xrp": xrp,
        "balance_rlusd": rlusd,
        "mid_price": mid,
        "portfolio_value_xrp": portfolio_xrp if mid else None,
        "best_bid_rlusd_per_xrp": best_bid,
        "best_ask_rlusd_per_xrp": best_ask,
        "book_spread_pct": book_spread_pct,
        "open_offers": enriched_offers,
        "open_offers_count": len(enriched_offers),
        "rlusd_issuer": cfg.resolved_rlusd_issuer(),
        "bot_account_address": address,
    }
    if book_note:
        out["ledger_sync_note"] = book_note
    return out


async def sync_ledger_balances_to_runtime(
    config: BotConfig | None = None,
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Fetch ledger balances and patch runtime_state.json for the GUI.

    Returns (ok, snapshot, message). Balances are written even if the book fetch fails.
    """
    cfg = config or BotConfig.load()
    snap = await fetch_ledger_wallet_snapshot(cfg)
    patch: Dict[str, Any] = {
        "balance_xrp": snap["balance_xrp"],
        "balance_rlusd": snap["balance_rlusd"],
        "open_offers": snap.get("open_offers") or [],
        "open_offers_count": int(snap.get("open_offers_count") or 0),
    }
    if snap.get("mid_price"):
        patch["mid_price"] = snap["mid_price"]
        patch["portfolio_value_xrp"] = snap["portfolio_value_xrp"]
        patch["best_bid_rlusd_per_xrp"] = snap.get("best_bid_rlusd_per_xrp")
        patch["best_ask_rlusd_per_xrp"] = snap.get("best_ask_rlusd_per_xrp")
        patch["book_spread_pct"] = snap.get("book_spread_pct")
    ok = patch_runtime_state_file(patch)
    xrp = float(snap["balance_xrp"])
    rlusd = float(snap["balance_rlusd"])
    msg = f"Ledger: {xrp:.6f} XRP, {rlusd:.6f} RLUSD on {snap['bot_account_address'][:12]}…"
    note = snap.get("ledger_sync_note")
    if note:
        if "Invalid currency" in note:
            msg += " (balances updated; book mid skipped — restart GUI if this persists)"
        else:
            msg += f" ({note})"
    if not ok:
        msg += " (runtime_state.json not updated — file missing?)"
    return ok, snap, msg


def sync_ledger_balances_to_runtime_sync(
    config: BotConfig | None = None,
) -> Tuple[bool, Dict[str, Any], str]:
    import asyncio

    return asyncio.run(sync_ledger_balances_to_runtime(config))
