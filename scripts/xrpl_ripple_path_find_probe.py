#!/usr/bin/env python3
"""ripple_path_find probes for RLUSD/USDC/XRP routes."""

from __future__ import annotations

import json

import requests

from config.settings import BotConfig

USDC_ISSUER = "rGm7WCVp9gb4jZHWTEtGUr4dd74z2XuWhE"
USDC_CURRENCY = "5553444300000000000000000000000000000000"


def main() -> None:
    cfg = BotConfig.load()
    rpc = cfg.resolved_rpc_url()
    acct = cfg.bot_account_address
    rl_cur = cfg.resolved_rlusd_currency_code()
    rl_iss = cfg.resolved_rlusd_issuer()
    rlusd = {"currency": rl_cur, "issuer": rl_iss}
    usdc = {"currency": USDC_CURRENCY, "issuer": USDC_ISSUER}

    probes = [
        ("1000 RLUSD -> RLUSD (loop sanity)", rlusd, {**rlusd, "value": "1000"}, {**rlusd, "value": "1000"}),
        ("1000 USDC -> RLUSD", usdc, {**usdc, "value": "1000"}, {**rlusd, "value": "1000"}),
        ("1000 RLUSD -> USDC", rlusd, {**rlusd, "value": "1000"}, {**usdc, "value": "1000"}),
        ("1000 RLUSD -> XRP", rlusd, {**rlusd, "value": "1000"}, "1000000000"),
    ]

    for label, src_cur, send_max, dest_amt in probes:
        payload = {
            "method": "ripple_path_find",
            "params": [
                {
                    "source_account": acct,
                    "destination_account": acct,
                    "destination_amount": dest_amt,
                    "send_max": send_max,
                    "source_currencies": [src_cur],
                }
            ],
        }
        r = requests.post(rpc, json=payload, timeout=20).json()
        print(f"\n=== {label} ===")
        if r.get("error"):
            print("error:", r["error"])
            continue
        alts = (r.get("result") or {}).get("alternatives") or []
        print(f"alternatives: {len(alts)}")
        for i, alt in enumerate(alts[:2]):
            print(f"  alt[{i}] source_amount={alt.get('source_amount')}")
            paths = alt.get("paths_computed") or []
            for j, p in enumerate(paths[:2]):
                print(f"    path[{j}]: {json.dumps(p)}")


if __name__ == "__main__":
    main()
