#!/usr/bin/env python3
"""Live health check: powder, inventory, decisions, Maximize knobs."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    from alpha.operator.runtime import OperatorRuntimeStore, apply_overrides
    from config.settings import BotConfig

    rt_path = ROOT / "logs" / "alpha_runtime_state.json"
    act_path = ROOT / "logs" / "alpha_activity.jsonl"
    ov_path = ROOT / "logs" / "alpha_overrides.json"

    rt = json.loads(rt_path.read_text(encoding="utf-8")) if rt_path.is_file() else {}
    ov = json.loads(ov_path.read_text(encoding="utf-8")) if ov_path.is_file() else {}
    base = BotConfig.load()
    eff = apply_overrides(base, OperatorRuntimeStore().load_overrides())

    xrp = float(rt.get("xrp") or rt.get("balance_xrp") or 0)
    rlusd = float(rt.get("rlusd") or rt.get("balance_rlusd") or 0)
    mid = float(rt.get("mid") or rt.get("mid_price") or 0)
    port = float(rt.get("portfolio_xrp_equiv") or 0)
    if port <= 0 and mid > 0:
        port = xrp + (rlusd / mid if mid else 0)
    rlusd_xeq = (rlusd / mid) if mid > 0 else 0.0
    floor = float(getattr(eff, "alpha_reload_min_rlusd_deploy_xrp_equiv", 0) or 0)
    target = float(getattr(eff, "inventory_target_xrp_ratio", 0) or 0)
    xrp_ratio = (xrp / port) if port > 0 else 0.0
    dev = xrp_ratio - target

    print("=== LIVE BALANCES ===")
    print(f"xrp={xrp:.4f}")
    print(f"rlusd={rlusd:.4f}")
    print(f"mid={mid:.6f}")
    print(f"portfolio_xrp_eq={port:.4f}")
    print(f"rlusd_xrp_eq={rlusd_xeq:.4f}  floor={floor:.1f}  powder_ok={rlusd_xeq + 1e-9 >= floor}")
    print(f"xrp_ratio={xrp_ratio:.4f}  target={target:.2f}  dev={dev:+.4f}")
    print(f"clip_est_xrp={port * float(eff.alpha_risk_per_trade_pct) / 100.0:.2f}")

    print("\n=== MAXIMIZE KNOBS (effective) ===")
    for k in [
        "inventory_target_xrp_ratio",
        "alpha_strength_deviation",
        "alpha_risk_per_trade_pct",
        "alpha_reload_min_rlusd_deploy_xrp_equiv",
        "alpha_reload_block_accumulation_until_funded",
        "alpha_brackets_enabled",
        "bracket_trailing_enabled",
        "alpha_accumulation_harvest_move_24h_watch_pct",
        "alpha_accumulation_dip_move_24h_arm_pct",
        "alpha_max_pending_buys",
        "alpha_max_pending_sells",
        "trading_enabled",
        "dry_run",
    ]:
        print(f"  {k}={getattr(eff, k, None)}")
    print(f"  overrides_updated={ov.get('updated_utc')}")

    print("\n=== DECISION / REGIMES ===")
    for k in [
        "decision",
        "inventory",
        "reload_regime",
        "accumulation_regime",
        "drawdown_reload",
        "momentum_entry",
        "risk",
    ]:
        v = rt.get(k)
        if v is None:
            continue
        if isinstance(v, dict):
            slim = {
                kk: v[kk]
                for kk in list(v.keys())[:16]
                if not isinstance(v.get(kk), (dict, list))
            }
            print(f"{k}: {json.dumps(slim, default=str)[:500]}")
        else:
            print(f"{k}: {v}")

    offers = rt.get("open_offers") or []
    print(f"\nopen_offers_count={rt.get('open_offers_count')}  engine_cycle={rt.get('engine_cycle')}")
    if isinstance(offers, list):
        for o in offers[:8]:
            print(f"  offer {o}")

    print("\n=== LAST 40 ACTIVITY CYCLES ===")
    lines = act_path.read_text(encoding="utf-8", errors="replace").splitlines() if act_path.is_file() else []
    decisions = Counter()
    reasons = Counter()
    recent = []
    for line in lines[-80:]:
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("event") != "cycle" and "decision" not in o:
            if o.get("event") == "execution":
                recent.append(o)
            continue
        d = str(o.get("decision") or o.get("action") or "?")
        r = str(o.get("reason") or "")[:90]
        decisions[d] += 1
        reasons[r] += 1
        recent.append(o)
    print("decision counts (sample):", dict(decisions))
    print("top reasons:")
    for r, n in reasons.most_common(12):
        print(f"  {n:3d}  {r}")
    print("last 12 events:")
    for o in recent[-12:]:
        ts = str(o.get("ts") or "")[:19]
        if o.get("event") == "execution":
            print(f"  {ts} EXEC {o.get('action')} executed={o.get('executed')} {str(o.get('message') or o.get('reason') or '')[:100]}")
        else:
            print(f"  {ts} {o.get('decision')} | {str(o.get('reason') or '')[:100]}")

    # Verdict
    print("\n=== VERDICT ===")
    issues = []
    goods = []
    if not getattr(eff, "trading_enabled", True):
        issues.append("trading_enabled=False")
    if getattr(eff, "dry_run", False):
        issues.append("dry_run=True")
    if getattr(eff, "alpha_brackets_enabled", True):
        issues.append("brackets still ON (want OFF for Maximize)")
    else:
        goods.append("core-bag brackets OFF")
    if abs(float(getattr(eff, "inventory_target_xrp_ratio", 0)) - 0.85) > 0.001:
        issues.append(f"target not 0.85 ({getattr(eff, 'inventory_target_xrp_ratio', None)})")
    else:
        goods.append("target 85%")
    if float(getattr(eff, "alpha_reload_min_rlusd_deploy_xrp_equiv", 0)) < 35:
        issues.append("powder floor lower than Maximize 40")
    else:
        goods.append(f"powder floor {floor:.0f}")
    if rlusd_xeq + 1e-9 >= floor:
        goods.append(f"powder OK ({rlusd_xeq:.1f} >= {floor:.0f})")
    else:
        issues.append(f"powder still short ({rlusd_xeq:.1f} < {floor:.0f})")
    if xrp_ratio > target + 0.08:
        issues.append(f"still very XRP-heavy (ratio {xrp_ratio:.1%} vs target {target:.0%})")
    elif xrp_ratio > target + 0.03:
        goods.append(f"mildly heavy ({xrp_ratio:.1%}) — room to trim/harvest")
    else:
        goods.append(f"near target ratio ({xrp_ratio:.1%})")

    place_asks = decisions.get("place_ask", 0)
    place_bids = decisions.get("place_bid", 0)
    holds = decisions.get("hold", 0)
    if place_bids > 0:
        goods.append(f"bids firing ({place_bids} in sample)")
    elif rlusd_xeq >= floor and xrp_ratio < target - 0.02:
        issues.append("powder OK and under-target but no bids in recent sample — check tape/TA")
    elif rlusd_xeq >= floor:
        goods.append("powder up; waiting for dip/weakness/breakout to bid is OK")
    if place_asks > 0:
        goods.append(f"asks firing ({place_asks} in sample)")
    if holds > 30 and place_asks + place_bids == 0:
        issues.append("mostly hold-only in sample — may be max_pending or no edge")

    print("GOOD:")
    for g in goods:
        print(f"  + {g}")
    print("ISSUES:")
    if not issues:
        print("  (none critical)")
    for i in issues:
        print(f"  - {i}")

    if not issues:
        print("\nSTATUS: RUNNING CORRECTLY for Maximize posture")
    elif rlusd_xeq >= floor * 0.8 and not getattr(eff, "alpha_brackets_enabled", True):
        print("\nSTATUS: MOSTLY HEALTHY — powder recovering / loop armed")
    else:
        print("\nSTATUS: NEEDS ATTENTION")


if __name__ == "__main__":
    main()
