#!/usr/bin/env python3
"""Scan XRPL mainnet for AMM + book depth on common arb candidate pairs."""

from __future__ import annotations

import requests

from config.settings import BotConfig

# Well-known mainnet issuers / currency codes (hex where needed)
CANDIDATES = [
    ("RLUSD", None, "resolved"),  # from config
    ("USDC", "5553444300000000000000000000000000000000", "rGm7WCVp9gb4jZHWTEtGUr4dd74z2XuWhE"),
    ("EUR", "EUR", "rchGBxcD1A1C2tdxF6papQYZacUEfaS5YE"),  # Bitstamp EUR legacy
    ("USD", "USD", "rvYAfWj5gh67oV6fW32ZzP3Aw4Eubs59B"),  # Bitstamp USD
    ("BTC", "BTC", "rchGBxcD1A1C2tdxF6papQYZacUEfaS5YE"),
    ("ETH", "ETH", "rchGBxcD1A1C2tdxF6papQYZacUEfaS5YE"),
    ("SOLO", "534F4C4F00000000000000000000000000000000", "rsoLo2J1RY8s8trnZRg8fouZMPQScAGs2B"),
    ("CSC", "CSC", "rCSCManTZ8ME9EoLrSHHYKW8PPwWMgkwr"),
    ("XLM", "XLM", "rKiCet8SdvWxPXnagY2C2H6zZrFto1YQy1"),
]


def rpc(rpc_url: str, method: str, params: list) -> dict:
    return requests.post(rpc_url, json={"method": method, "params": params}, timeout=15).json()


def book_count(rpc_url: str, gets: dict, pays: dict) -> int:
    r = rpc(rpc_url, "book_offers", [{"taker_gets": gets, "taker_pays": pays, "limit": 20}])
    return len((r.get("result") or {}).get("offers") or [])


def amm_ok(rpc_url: str, cur: str, iss: str) -> tuple[bool, str | None]:
    r = rpc(
        rpc_url,
        "amm_info",
        [{"asset": {"currency": "XRP"}, "asset2": {"currency": cur, "issuer": iss}}],
    )
    if r.get("error"):
        return False, str(r["error"])
    amm = (r.get("result") or {}).get("amm") or {}
    return bool(amm), amm.get("account")


def main() -> None:
    cfg = BotConfig.load()
    rpc_url = cfg.resolved_rpc_url()
    rl_cur = cfg.resolved_rlusd_currency_code()
    rl_iss = cfg.resolved_rlusd_issuer()

    print("asset | AMM | book_bid | book_ask | notes")
    print("-" * 70)
    for name, cur, iss in CANDIDATES:
        if iss == "resolved":
            cur, iss = rl_cur, rl_iss
        token = {"currency": cur, "issuer": iss}
        xrp = {"currency": "XRP"}
        has_amm, amm_acct = amm_ok(rpc_url, cur, iss)
        bid = book_count(rpc_url, xrp, token)  # taker gets XRP pays token = bid side
        ask = book_count(rpc_url, token, xrp)
        note = ""
        if name in ("USD", "EUR") and (bid or ask):
            note = "legacy gateway IOU"
        if name == "USDC":
            note = "Circle native 2025"
        if name == "RLUSD":
            note = "Ripple RLUSD"
        print(f"{name:5} | {'Y' if has_amm else 'N':3} | {bid:8} | {ask:8} | {note}")


if __name__ == "__main__":
    main()
