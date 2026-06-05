#!/usr/bin/env python3
"""Print on-ledger balances for the configured bot account (compare to Xaman)."""
from __future__ import annotations

import asyncio
import sys

from config.settings import BotConfig
from connectors.xrpl_connector import XRPLConnector, XRPLNetworkConfig
from xrpl.models.requests import AccountInfo, AccountLines, AccountObjects
from xrpl.utils import drops_to_xrp

# Typical mainnet reserves (XRP) — approximate display check for "available".
BASE_RESERVE_XRP = 1.0
OWNER_RESERVE_XRP = 0.2


async def main() -> int:
    cfg = BotConfig.load()
    addr = cfg.bot_account_address.strip()
    issuer = cfg.resolved_rlusd_issuer()
    conn = XRPLConnector(
        account_address=addr,
        secret=None,
        rlusd_issuer=issuer,
        rlusd_currency=cfg.resolved_rlusd_currency_code(),
        network=XRPLNetworkConfig(json_rpc_url=cfg.resolved_rpc_url()),
    )

    print("=== XLedgerMate ledger verify ===")
    print(f"Account:  {addr}")
    print(f"RLUSD issuer: {issuer}")
    print(f"RPC:      {cfg.resolved_rpc_url()}")
    print()

    for idx in ("validated", "current"):
        ai = (await conn._request(AccountInfo(account=addr, ledger_index=idx))).result[
            "account_data"
        ]
        total_xrp = float(drops_to_xrp(ai["Balance"]))
        owner_count = int(ai.get("OwnerCount", 0))
        reserve = BASE_RESERVE_XRP + owner_count * OWNER_RESERVE_XRP
        approx_available = max(0.0, total_xrp - reserve)
        print(f"--- XRP (ledger_index={idx}) ---")
        print(f"  Total (AccountInfo Balance): {total_xrp:.6f}")
        print(f"  OwnerCount: {owner_count}")
        print(f"  Approx reserve locked:     {reserve:.2f} XRP")
        print(f"  Approx available (~):      {approx_available:.6f} XRP")
        print()

    trust = await conn.get_rlusd_trust_line()
    print("--- RLUSD trust line (peer filter) ---")
    print(f"  Exists: {trust.exists}")
    print(f"  Balance: {trust.balance:.8f} RLUSD")
    print(f"  Limit:   {trust.limit}")
    print()

    req = AccountLines(account=addr, ledger_index="validated")
    lines = (await conn._request(req)).result.get("lines", [])
    print(f"--- All trust lines ({len(lines)}) ---")
    for line in lines:
        bal = float(line.get("balance", 0))
        if abs(bal) < 0.0001:
            continue
        cur = line.get("currency", "")
        peer = line.get("account", "")
        print(f"  {cur} @ {peer}: {bal}")
    print()

    offers = await conn.get_open_offers()
    print(f"--- Open offers: {len(offers)} ---")
    for offer in offers:
        print(f"  {offer}")
    print()

    objs = (
        await conn._request(AccountObjects(account=addr, ledger_index="validated"))
    ).result.get("account_objects", [])
    print(f"--- Account objects: {len(objs)} ---")
    for obj in objs:
        print(f"  {obj.get('LedgerEntryType')} seq={obj.get('Sequence')}")

    xrp = await conn.get_xrp_balance()
    rlusd = trust.balance if trust.exists else 0.0
    mid = 1.126
    print()
    print("--- What the bot uses (same as GUI total balances) ---")
    print(f"  XRP:   {xrp:.6f}")
    print(f"  RLUSD: {rlusd:.8f}")
    print(f"  Portfolio @ mid {mid}: {xrp + rlusd / mid:.4f} XRP equiv")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
