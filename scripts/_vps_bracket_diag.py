#!/usr/bin/env python3
"""One-shot bracket vs ledger diagnostic (run on VPS from repo root)."""
from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path

from alpha.dry_run import DryRunGuard
from alpha.ledger.xrpl_adapter import XrplLedgerAdapter
from alpha.orders.state import BracketStateStore
from config.settings import BotConfig


async def main() -> None:
    cfg = BotConfig.load()
    guard = DryRunGuard(dry_run=cfg.dry_run, network="mainnet" if not cfg.testnet else "testnet")
    adapter = XrplLedgerAdapter.from_config(cfg, dry_run_guard=guard)
    await adapter.connect()
    offers = await adapter.get_open_offers()
    store = BracketStateStore()
    open_recs = list(store.iter_open())
    pending_seqs = {r.buy_sequence for r in open_recs if r.state.value == "pending_buy" and r.buy_sequence}
    leg_seqs = set()
    for r in store.all_records():
        if r.tp_leg and r.tp_leg.sequence:
            leg_seqs.add(r.tp_leg.sequence)
        if r.sl_leg and r.sl_leg.sequence:
            leg_seqs.add(r.sl_leg.sequence)
        if r.buy_sequence:
            leg_seqs.add(r.buy_sequence)

    print("=== open ledger offers ===")
    for o in offers:
        seq = o.get("sequence") if isinstance(o, dict) else o.sequence
        side = o.get("side") if isinstance(o, dict) else o.side
        price = o.get("price") if isinstance(o, dict) else o.price
        size = o.get("size_xrp") if isinstance(o, dict) else o.size_xrp
        linked = "pending" if seq in pending_seqs else ("leg/bracket" if seq in leg_seqs else "ORPHAN")
        print(f"  seq={seq} {side} price={price:.6f} size={size:.4f} {linked}")

    print("\n=== open bracket records ===", len(open_recs))
    for r in open_recs[:12]:
        print(
            f"  {r.bracket_id[:8]} {r.state.value} buy_seq={r.buy_sequence} "
            f"entry={r.entry_price_rlusd_per_xrp:.4f} tp={r.tp_leg.sequence if r.tp_leg else None} "
            f"sl={r.sl_leg.sequence if r.sl_leg else None}"
        )

    hist = Counter(r.state.value for r in store.all_records())
    print("\n=== bracket state histogram ===", dict(hist))


if __name__ == "__main__":
    asyncio.run(main())
