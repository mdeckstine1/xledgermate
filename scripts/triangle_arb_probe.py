#!/usr/bin/env python3
"""One-shot probe: RLUSD/XRP, USDC/XRP AMM mids and implied stablecoin cross."""

from __future__ import annotations

import requests

from config.settings import BotConfig

USDC_ISSUER = "rGm7WCVp9gb4jZHWTEtGUr4dd74z2XuWhE"
USDC_CURRENCY = "5553444300000000000000000000000000000000"
XRP_DROPS = 1_000_000.0


def _amm_mid(rpc: str, currency: str, issuer: str) -> dict:
    payload = {
        "method": "amm_info",
        "params": [{"asset": {"currency": "XRP"}, "asset2": {"currency": currency, "issuer": issuer}}],
    }
    body = requests.post(rpc, json=payload, timeout=15).json()
    if body.get("error"):
        return {"error": body["error"]}
    amm = (body.get("result") or {}).get("amm") or {}
    a0, a1 = amm.get("amount"), amm.get("amount2")

    def xrp(v):
        if isinstance(v, str) and v.isdigit():
            return int(v) / XRP_DROPS
        if isinstance(v, dict) and "value" in v:
            return float(v["value"])
        return None

    def token(v):
        if isinstance(v, dict):
            return float(v.get("value") or 0)
        return None

    xrp_amt = xrp(a0) or xrp(a1)
    tok_amt = token(a1) or token(a0)
    mid = (tok_amt / xrp_amt) if xrp_amt and tok_amt and xrp_amt > 0 else None
    tf = amm.get("TradingFee")
    return {
        "stable_per_xrp": mid,
        "trading_fee": tf,
        "fee_bps": round(float(tf) / 100.0, 2) if tf is not None else None,
    }


def main() -> None:
    cfg = BotConfig.load()
    rpc = cfg.resolved_rpc_url()
    rlusd = _amm_mid(rpc, cfg.resolved_rlusd_currency_code(), cfg.resolved_rlusd_issuer())
    usdc = _amm_mid(rpc, USDC_CURRENCY, USDC_ISSUER)

    print("=== Triangular arb probe (AMM implied mids) ===")
    print(f"RLUSD/XRP: {rlusd}")
    print(f"USDC/XRP:  {usdc}")

    rl = rlusd.get("stable_per_xrp")
    us = usdc.get("stable_per_xrp")
    if rl and us and rl > 0 and us > 0:
        implied_rlusd_per_usdc = rl / us
        bps_off_par = (implied_rlusd_per_usdc - 1.0) * 10_000.0
        print()
        print(f"Implied RLUSD per USDC (via XRP): {implied_rlusd_per_usdc:.6f}")
        print(f"Deviation from 1:1 peg: {bps_off_par:+.2f} bps")
        # crude 3-leg cost: 2 AMM fees + 1 CLOB half (~3 bps) + slip 2
        fees = (rlusd.get("fee_bps") or 10) + (usdc.get("fee_bps") or 10) + 3 + 2
        print(f"Rough 3-leg cost (2x AMM + CLOB half + slip): ~{fees:.1f} bps")
        print(f"Gross triangle mispricing (peg deviation): {abs(bps_off_par):.2f} bps")
        print(f"Net after rough costs: {abs(bps_off_par) - fees:+.2f} bps (if executable at mids)")


if __name__ == "__main__":
    main()
