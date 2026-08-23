#!/usr/bin/env python3
"""Quote queue / touch / refresh visibility snapshot."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/root/xledgermate")


def main() -> None:
    rt = json.loads((ROOT / "logs/runtime_state.json").read_text(encoding="utf-8"))
    bb = float(rt.get("best_bid_rlusd_per_xrp") or 0)
    ba = float(rt.get("best_ask_rlusd_per_xrp") or 0)
    mid = float(rt.get("mid_price") or 0)

    print("=== touch / book ===")
    print(f"updated_utc: {rt.get('updated_utc')}")
    print(f"best_bid: {bb:.6f}  best_ask: {ba:.6f}  mid: {mid:.6f}")
    print(f"book_spread_pct: {rt.get('book_spread_pct')}")
    print(f"ws_book_age_s: {rt.get('ws_book_age_s')}")
    print(f"market_edge_met: {rt.get('market_edge_met')}")
    print(f"as_reservation: {rt.get('as_reservation')}")
    print(f"inside_l1: {rt.get('inside_l1')}  res_delta_bps: {rt.get('reservation_to_bbo_delta_bps')}")

    print("\n=== quote intents (planned) vs touch ===")
    for qi in rt.get("quote_intents") or []:
        side = str(qi.get("side", "")).lower()
        price = float(qi.get("price") or 0)
        size = float(qi.get("size_xrp") or 0)
        lvl = qi.get("level")
        if side == "bid" and bb > 0:
            bps = (price - bb) / bb * 10_000
        elif side == "ask" and ba > 0:
            bps = (price - ba) / ba * 10_000
        else:
            bps = 0.0
        print(f"  L{lvl} {side.upper()} {size:.2f} @ {price:.6f}  ({bps:+.1f} bps vs touch)")

    offers = rt.get("open_offers") or []
    for o in offers:
        side = str(o.get("side", "")).lower()
        price = float(o.get("price") or 0)
        size = float(o.get("size_xrp") or 0)
        if side == "bid" and bb > 0:
            bps = (price - bb) / bb * 10_000
            touch = "AT/IMPROVE" if price >= bb - 1e-9 else f"BEHIND {bps:.1f} bps"
        elif side == "ask" and ba > 0:
            bps = (price - ba) / ba * 10_000
            touch = "AT/IMPROVE" if price <= ba + 1e-9 else f"BEHIND {bps:.1f} bps"
        else:
            touch = "?"
            bps = 0.0
        print(f"  {side.upper():3} {size:.2f} XRP @ {price:.6f}  vs touch -> {touch}")

    print("\n=== refresh / queue stats (session) ===")
    fills = int(rt.get("fills_session") or 0)
    cancelled = int(rt.get("offers_cancelled_session") or 0)
    kept = int(rt.get("offers_kept_session") or 0)
    cpf = float(rt.get("cancel_per_fill") or 0)
    cycle = int(rt.get("cycle_count") or 0)
    placed_last = int(rt.get("offers_placed_last_cycle") or 0)
    print(f"cycle_count: {cycle}")
    print(f"fills_session: {fills}")
    print(f"offers_cancelled_session: {cancelled}")
    print(f"offers_kept_session: {kept}")
    print(f"cancel_per_fill: {cpf:.1f}")
    print(f"offers_placed_last_cycle: {placed_last}")
    print(f"last_execution: {rt.get('last_execution_summary')}")
    print(f"quote_visibility_summary: {rt.get('quote_visibility_summary') or '(not set on ws path)'}")
    print(f"worst_vs_touch_bps: {rt.get('worst_vs_touch_bps')}")
    print(f"quotes_at_touch: {rt.get('quotes_at_touch')}")
    print(f"join_touch_active: {rt.get('join_touch_active')}")

    # Recent offer refreshes from trades CSV
    trades = ROOT / "logs/trades_2026-06.csv"
    if trades.exists():
        lines = trades.read_text(encoding="utf-8", errors="replace").splitlines()
        refreshes = [ln for ln in lines if "OFFER_REFRESH" in ln]
        session_refreshes = [ln for ln in refreshes if "2026-06-18T10:4" in ln or "2026-06-18T10:5" in ln]
        print(f"\n=== offer refreshes since 10:41 UTC restart ===")
        print(f"count: {len(session_refreshes)}")
        for ln in session_refreshes[-8:]:
            parts = ln.split(",")
            if len(parts) >= 12:
                print(f"  {parts[0][11:19]} cycle={parts[10]} {parts[11]}")

    # Decision log refresh mode lines
    log = ROOT / "logs/xledgermate.log"
    if log.exists():
        text = log.read_text(encoding="utf-8", errors="replace")
        # since restart
        idx = text.rfind("WsPureTradingEngine v2.1.15")
        chunk = text[idx:] if idx >= 0 else text[-80_000:]
        sync_lines = [
            ln for ln in chunk.splitlines()
            if "WS pure sync:" in ln or "WS refresh mode:" in ln
        ]
        print("\n=== recent sync decisions (v2.1.15 session) ===")
        for ln in sync_lines[-10:]:
            print(" ", ln.split("|")[-1].strip()[:120])

        preserve_off = sum(1 for ln in sync_lines if "preserve_touch=False" in ln)
        preserve_on = sum(1 for ln in sync_lines if "preserve_touch=True" in ln)
        print(f"\npreserve_touch=True cycles logged: {preserve_on}")
        print(f"preserve_touch=False cycles logged: {preserve_off}")

    # Book offers snapshot via connector (top of book + our account offers)
    print("\n=== on-chain book top (RPC) ===")
    py = ROOT / ".venv/bin/python"
    script = '''
import asyncio, json, sys
sys.path.insert(0, "/root/xledgermate")
from config.settings import BotConfig
from connectors.xrpl_connector import XRPLConnector, XRPLNetworkConfig

async def run():
    c = BotConfig.load()
    conn = XRPLConnector(
        account_address=c.bot_account_address.strip(),
        secret=c.bot_secret_key or None,
        rlusd_issuer=c.resolved_rlusd_issuer(),
        rlusd_currency=c.resolved_rlusd_currency_code(),
        network=XRPLNetworkConfig(json_rpc_url=c.resolved_rpc_url()),
    )
    offers = await conn.get_open_offers()
    # best bid/ask from book_offers taker gets
    bids = await conn.get_order_book(side="buy", limit=8)
    asks = await conn.get_order_book(side="sell", limit=8)
    print("TOP BIDS:")
    for i, r in enumerate(bids[:5]):
        print(f"  {i+1}. {r.get('price'):.6f}  {r.get('size_xrp'):.2f} XRP")
    print("TOP ASKS:")
    for i, r in enumerate(asks[:5]):
        print(f"  {i+1}. {r.get('price'):.6f}  {r.get('size_xrp'):.2f} XRP")
    print("OUR OFFERS:")
    for o in offers:
        print(f"  {o.side} {o.size_xrp:.2f} @ {o.price:.6f} seq={o.sequence}")

asyncio.run(run())
'''
    r = subprocess.run([str(py), "-c", script], capture_output=True, text=True, timeout=45)
    if r.returncode == 0:
        print(r.stdout)
    else:
        print("book probe failed:", (r.stderr or r.stdout)[:300])


if __name__ == "__main__":
    main()
