"""Audit open offers vs brackets/strength-sells (VPS: PYTHONPATH=. .venv/bin/python scripts/_offers_audit_quick.py)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from alpha.dry_run import DryRunGuard
from alpha.ledger.xrpl_adapter import XrplLedgerAdapter
from config.settings import BotConfig


async def main() -> None:
    cfg = BotConfig.load()
    ledger = XrplLedgerAdapter.from_config(
        cfg, dry_run_guard=DryRunGuard(dry_run=cfg.dry_run, network="mainnet" if not cfg.testnet else "testnet")
    )
    await ledger.connect()
    try:
        offers = await ledger.get_open_offers()
        mid = 0.0
        try:
            book = await ledger.get_order_book()
            mid = float(book.mid or 0)
        except Exception:
            pass
    finally:
        await ledger.close()

    br_path = Path("logs/alpha_brackets.json")
    strength_path = Path("logs/alpha_strength_sells.json")
    br = json.loads(br_path.read_text()) if br_path.is_file() else {}
    recs = br if isinstance(br, list) else br.get("records", br.get("brackets", []))
    strength = json.loads(strength_path.read_text()) if strength_path.is_file() else {}

    by_seq: dict[int, dict] = {}
    for r in recs:
        bid = str(r.get("bracket_id", ""))[:8]
        for key in ("buy_leg", "sl_leg", "tp_leg"):
            leg = r.get(key)
            if not leg or not leg.get("sequence"):
                continue
            seq = int(leg["sequence"])
            by_seq[seq] = {
                "source": "bracket",
                "bracket": bid,
                "state": r.get("state"),
                "entry": r.get("entry_price_rlusd_per_xrp"),
                "role": leg.get("role"),
                "stored_price": leg.get("price_rlusd_per_xrp"),
            }

    for seq_s, rec in (strength.get("records") or strength.get("sells") or {}).items():
        if isinstance(rec, dict):
            seq = int(rec.get("sequence") or seq_s)
            by_seq[seq] = {
                "source": "strength_sell",
                "bracket": "",
                "state": "strength",
                "entry": None,
                "role": "ask",
                "stored_price": rec.get("price_rlusd_per_xrp"),
            }

    print(f"mid={mid:.6f}  open_offers={len(offers)}\n")
    print(f"{'seq':>12}  {'side':4}  {'ledger':>10}  {'stored':>10}  {'drift%':>7}  source")
    print("-" * 72)
    weird = []
    for o in sorted(offers, key=lambda x: float(x.get("price") or 0)):
        seq = int(o.get("sequence") or 0)
        side = str(o.get("side", ""))
        price = float(o.get("price") or 0)
        size = float(o.get("size_xrp") or o.get("taker_gets") or 0)
        meta = by_seq.get(seq)
        stored = float(meta["stored_price"]) if meta and meta.get("stored_price") else None
        drift = ((price - mid) / mid * 100) if mid > 0 else 0.0
        src = "ORPHAN/UNTRACKED"
        if meta:
            src = f"{meta['source']} {meta.get('bracket','')} {meta.get('role','')} state={meta.get('state')}"
            if meta.get("entry"):
                src += f" entry={meta['entry']:.6f}"
        line = f"{seq:>12}  {side:4}  {price:10.6f}  "
        line += f"{stored:10.6f}  " if stored else f"{'—':>10}  "
        line += f"{drift:+6.2f}%  {src}  size={size:.4f}"
        print(line)
        if mid > 0 and abs(drift) > 3.0:
            weird.append((seq, price, drift, src))

    if weird:
        print("\n=== FAR FROM MID (>3%) ===")
        for seq, price, drift, src in weird:
            print(f"  seq {seq} @ {price:.6f} ({drift:+.1f}%) — {src}")


if __name__ == "__main__":
    asyncio.run(main())
