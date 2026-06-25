#!/usr/bin/env python3
"""Overnight P&L audit: MTM vs realized, XRP acquired, bracket exits."""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

SESSION_PATH = Path("logs/alpha_session.json")
TRADES_PATH = Path("logs/trades_2026-06.csv")
BRACKETS_PATH = Path("logs/alpha_brackets.json")
ACTIVITY_PATH = Path("logs/alpha_activity.jsonl")


def parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def main() -> None:
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=14)

    print("=== SESSION P&L (mark-to-market, not realized) ===")
    if SESSION_PATH.is_file():
        sess = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
        base = float(sess.get("baseline_portfolio_xrp") or 0)
        last = float(sess.get("last_portfolio_xrp") or 0)
        print(f"baseline_portfolio_xrp: {base:.4f} @ {sess.get('baseline_utc', '')}")
        print(f"last_portfolio_xrp:     {last:.4f} @ {sess.get('last_updated_utc', '')}")
        print(f"session_pnl_xrp (MTM):  {last - base:+.4f}")
        print("Note: session P&L = portfolio XRP-equiv change from baseline, includes mid moves.")

    print("\n=== TRADES CSV (last 14h, taxable rows) ===")
    buys_xrp = 0.0
    sells_xrp = 0.0
    realized_profit_xrp = 0.0
    sell_rows: list[dict] = []
    buy_rows: list[dict] = []

    if TRADES_PATH.is_file():
        with TRADES_PATH.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = parse_ts(row.get("timestamp_utc", ""))
                if ts is None or ts < since:
                    continue
                if row.get("taxable", "").upper() != "Y":
                    continue
                ev = (row.get("event_type") or row.get("side") or "").upper()
                xrp = float(row.get("xrp_amount") or 0)
                profit = float(row.get("profit_xrp_equiv") or 0)
                if ev == "BUY":
                    buys_xrp += xrp
                    buy_rows.append(row)
                elif ev == "SELL":
                    sells_xrp += xrp
                    realized_profit_xrp += profit
                    sell_rows.append(row)

        print(f"buys:  {len(buy_rows)} rows, +{buys_xrp:.4f} XRP acquired")
        print(f"sells: {len(sell_rows)} rows, -{sells_xrp:.4f} XRP disposed")
        print(f"net XRP from trades: {buys_xrp - sells_xrp:+.4f}")
        print(f"sum profit_xrp_equiv on SELLs: {realized_profit_xrp:+.4f} XRP (vs entry on those brackets)")

        if buy_rows:
            print("\nRecent BUYs:")
            for r in buy_rows[-8:]:
                print(
                    f"  {r.get('timestamp_utc','')[:19]} "
                    f"xrp={float(r.get('xrp_amount',0)):.4f} "
                    f"@ {float(r.get('price_rlusd_per_xrp',0)):.6f} "
                    f"{(r.get('notes') or '')[:50]}"
                )
        if sell_rows:
            print("\nRecent SELLs (TP/SL):")
            for r in sell_rows[-12:]:
                print(
                    f"  {r.get('timestamp_utc','')[:19]} "
                    f"xrp={float(r.get('xrp_amount',0)):.4f} "
                    f"@ {float(r.get('price_rlusd_per_xrp',0)):.6f} "
                    f"profit_xrp={float(r.get('profit_xrp_equiv',0)):+.4f} "
                    f"{(r.get('notes') or '')[:45]}"
                )

    print("\n=== BRACKET EXITS (last 14h) ===")
    if BRACKETS_PATH.is_file():
        data = json.loads(BRACKETS_PATH.read_text(encoding="utf-8"))
        records = data if isinstance(data, list) else data.get("records", [])
        recent = []
        for r in records:
            if not isinstance(r, dict):
                continue
            st = r.get("state", "")
            if st not in ("tp_filled", "sl_filled", "bracket_active", "pending_buy"):
                continue
            updated = parse_ts(r.get("updated_at") or r.get("created_at") or "")
            if updated and updated >= since:
                recent.append((updated, st, r))
        recent.sort(key=lambda x: x[0])
        counts = Counter(st for _, st, _ in recent if st in ("tp_filled", "sl_filled"))
        print(f"tp_filled: {counts.get('tp_filled', 0)} | sl_filled: {counts.get('sl_filled', 0)}")
        active = sum(1 for _, st, _ in recent if st == "bracket_active")
        print(f"brackets still active (touched in window): {active}")

    print("\n=== LIVE SNAPSHOT ===")
    try:
        import asyncio

        from alpha.dry_run import DryRunGuard
        from alpha.ledger.xrpl_adapter import XrplLedgerAdapter
        from alpha.operator.runtime import OperatorRuntimeStore, apply_overrides
        from config.settings import BotConfig
        from risk.inventory_limits import portfolio_xrp_equiv

        async def snap() -> None:
            cfg = apply_overrides(BotConfig.load(), OperatorRuntimeStore().load_overrides())
            ledger = XrplLedgerAdapter.from_config(cfg, dry_run_guard=DryRunGuard(dry_run=cfg.dry_run, network="mainnet"))
            await ledger.connect()
            try:
                bal = await ledger.get_balances()
                book = await ledger.get_order_book(limit=5)
                mid = float(book.mid or 0)
                xrp = float(bal.xrp)
                rlusd = float(bal.rlusd)
                port = portfolio_xrp_equiv(xrp, rlusd, mid) if mid > 0 else 0
                print(f"mid={mid:.6f} xrp={xrp:.4f} rlusd={rlusd:.2f} portfolio_xrp_equiv={port:.4f}")
                print(f"xrp_ratio≈{xrp / port * 100:.1f}% (of XRP-equiv book)" if port > 0 else "")
            finally:
                await ledger.close()

        asyncio.run(snap())
    except Exception as exc:
        print(f"(live snapshot skipped: {exc})")


if __name__ == "__main__":
    main()
