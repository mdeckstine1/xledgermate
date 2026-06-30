#!/usr/bin/env python3
"""Probe XRPL routes: books, AMMs, path_find for RLUSD/XRP/USDC triangle."""

from __future__ import annotations

import json

import requests

from config.settings import BotConfig

USDC_ISSUER = "rGm7WCVp9gb4jZHWTEtGUr4dd74z2XuWhE"
USDC_CURRENCY = "5553444300000000000000000000000000000000"
XRP_DROPS = 1_000_000.0


def rpc_call(rpc: str, method: str, params: list) -> dict:
    body = requests.post(rpc, json={"method": method, "params": params}, timeout=20).json()
    return body


def amm_exists(rpc: str, cur: str, iss: str) -> dict:
    r = rpc_call(rpc, "amm_info", [{"asset": {"currency": "XRP"}, "asset2": {"currency": cur, "issuer": iss}}])
    if r.get("error"):
        return {"exists": False, "error": r["error"]}
    amm = (r.get("result") or {}).get("amm") or {}
    return {"exists": bool(amm), "trading_fee": amm.get("TradingFee"), "account": amm.get("account")}


def book_depth(rpc: str, gets: dict, pays: dict) -> int:
    r = rpc_call(rpc, "book_offers", [{"taker_gets": gets, "taker_pays": pays, "limit": 20}])
    return len((r.get("result") or {}).get("offers") or [])


def path_find(rpc: str, source: dict, dest: dict, send_max: str | dict, dest_acct: str) -> dict:
    r = rpc_call(
        rpc,
        "path_find",
        [
            {
                "subcommand": "create",
                "source_account": dest_acct,
                "destination_account": dest_acct,
                "destination_amount": dest,
                "send_max": send_max,
                "source_currencies": [source],
            }
        ],
    )
    return r


def main() -> None:
    cfg = BotConfig.load()
    rpc = cfg.resolved_rpc_url()
    rl_cur = cfg.resolved_rlusd_currency_code()
    rl_iss = cfg.resolved_rlusd_issuer()
    acct = cfg.bot_account_address or "rLNaPoNo8taGmx7w3g3yRj1j4c6qJ1pX1"

    rlusd = {"currency": rl_cur, "issuer": rl_iss}
    usdc = {"currency": USDC_CURRENCY, "issuer": USDC_ISSUER}
    xrp_send = "1000000000"  # 1000 XRP in drops for path probe scale

    print("=== XRPL triangular route inventory ===\n")

    for name, cur, iss in [("RLUSD/XRP", rl_cur, rl_iss), ("USDC/XRP", USDC_CURRENCY, USDC_ISSUER)]:
        amm = amm_exists(rpc, cur, iss)
        print(f"{name} AMM: {amm}")

    print()
    direct_pairs = [
        ("RLUSD book: get RLUSD pay XRP", {"currency": "XRP"}, rlusd),
        ("RLUSD book: get XRP pay RLUSD", rlusd, {"currency": "XRP"}),
        ("USDC book: get USDC pay XRP", {"currency": "XRP"}, usdc),
        ("USDC book: get XRP pay USDC", usdc, {"currency": "XRP"}),
        ("RLUSD/USDC direct: get RLUSD pay USDC", usdc, rlusd),
        ("RLUSD/USDC direct: get USDC pay RLUSD", rlusd, usdc),
    ]
    for label, gets, pays in direct_pairs:
        n = book_depth(rpc, gets, pays)
        print(f"{label}: {n} offers (top 20)")

    print("\n=== path_find: RLUSD -> RLUSD via ledger (1000 RLUSD send_max) ===")
    pf = path_find(
        rpc,
        source=rlusd,
        dest={"currency": rl_cur, "issuer": rl_iss, "value": "1000"},
        send_max={**rlusd, "value": "1000"},
        dest_acct=acct,
    )
    if pf.get("error"):
        print("error:", pf["error"])
    else:
        alts = (pf.get("result") or {}).get("alternatives") or []
        print(f"alternatives: {len(alts)}")
        for i, alt in enumerate(alts[:3]):
            paths = alt.get("paths_computed") or alt.get("paths") or []
            print(f"  [{i}] source_amount={alt.get('source_amount')} paths={json.dumps(paths)[:200]}")

    print("\n=== path_find: USDC -> RLUSD (1000 USDC) ===")
    pf2 = path_find(
        rpc,
        source=usdc,
        dest={"currency": rl_cur, "issuer": rl_iss, "value": "1000"},
        send_max={**usdc, "value": "1000"},
        dest_acct=acct,
    )
    if pf2.get("error"):
        print("error:", pf2["error"])
    else:
        alts = (pf2.get("result") or {}).get("alternatives") or []
        print(f"alternatives: {len(alts)}")
        for i, alt in enumerate(alts[:3]):
            paths = alt.get("paths_computed") or alt.get("paths") or []
            print(f"  [{i}] source_amount={alt.get('source_amount')} paths={json.dumps(paths)[:300]}")


if __name__ == "__main__":
    main()
