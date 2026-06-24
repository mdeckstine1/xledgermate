#!/usr/bin/env python3
"""Audit open brackets vs ledger asks and current mid."""
from __future__ import annotations

import asyncio
from pathlib import Path

from alpha.orders.bracket import compute_bracket_prices
from alpha.orders.state import BracketStateStore
from alpha.orders.types import BracketLifecycleState
from config.settings import BotConfig
from alpha.operator.runtime import OperatorRuntimeStore, apply_overrides


async def main() -> None:
    cfg = apply_overrides(BotConfig.load(), OperatorRuntimeStore().load_overrides())
    store = BracketStateStore(persist_path=Path("logs/alpha_brackets.json"))

    from alpha.ledger.xrpl_adapter import XrplLedgerAdapter
    from alpha.dry_run import DryRunGuard

    ledger = XrplLedgerAdapter(cfg)
    await ledger.connect()
    try:
        book = await ledger.get_order_book(limit=5)
        mid = float(book.mid or 0)
        bid = float(book.best_bid or 0)
        ask = float(book.best_ask or 0)
        offers = await ledger.get_open_offers()
    finally:
        await ledger.close()

    asks = [o for o in offers if o.get("side") == "ask"]
    bids = [o for o in offers if o.get("side") == "bid"]

    print(f"=== MARKET mid={mid:.6f} bid={bid:.6f} ask={ask:.6f} ===")
    print(f"open_asks={len(asks)} open_bids={len(bids)} total_offers={len(offers)}")
    print("\n=== LEDGER ASKS (sells) ===")
    for o in sorted(asks, key=lambda x: float(x.get("price", 0))):
        seq = o.get("sequence")
        print(f"  seq={seq} price={float(o['price']):.6f} size_xrp={float(o['size_xrp']):.4f}")

    print("\n=== ACTIVE BRACKETS (deferred SL status) ===")
    active = [r for r in store.iter_open() if r.state == BracketLifecycleState.BRACKET_ACTIVE]
    for r in sorted(active, key=lambda x: x.entry_price_rlusd_per_xrp, reverse=True):
        prices = compute_bracket_prices(r.entry_price_rlusd_per_xrp, cfg)
        sl_leg = r.sl_leg
        tp_leg = r.tp_leg
        sl_price = sl_leg.price_rlusd_per_xrp if sl_leg else prices.stop_loss_price
        tp_price = tp_leg.price_rlusd_per_xrp if tp_leg else prices.take_profit_price
        sl_seq = sl_leg.sequence if sl_leg else None
        tp_seq = tp_leg.sequence if tp_leg else None
        filled = r.filled_xrp or r.target_size_xrp
        below_stop = mid > 0 and mid <= sl_price
        print(
            f"  {r.bracket_id[:8]} entry={r.entry_price_rlusd_per_xrp:.6f} "
            f"sl={sl_price:.6f} tp={tp_price:.6f} xrp={filled:.2f} "
            f"sl_on_book={sl_seq is not None} tp_on_book={tp_seq is not None} "
            f"mid_below_sl={below_stop}"
        )


if __name__ == "__main__":
    asyncio.run(main())
