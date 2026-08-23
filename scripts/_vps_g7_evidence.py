#!/usr/bin/env python3
"""Evidence check: is G7 execution envelope active on VPS?"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path("/root/xledgermate")
RT = ROOT / "logs/runtime_state.json"
LOG = ROOT / "logs/xledgermate.log"
INTEL = ROOT / "logs/intel_decisions.jsonl"


def main() -> None:
    print("=== G7 active evidence ===\n")

    if RT.exists():
        d = json.loads(RT.read_text(encoding="utf-8"))
        ws = d.get("ws_as_version")
        g7 = d.get("g7_summary")
        bid_bps = d.get("bid_touch_backoff_bps")
        ask_bps = d.get("ask_touch_backoff_bps")
        print("[runtime_state.json]")
        print(f"  ws_as_version:     {ws}")
        print(f"  updated_utc:       {d.get('updated_utc')}")
        print(f"  cycle_count:       {d.get('cycle_count')}")
        print(f"  inventory_label:   {d.get('inventory_label')}")
        print(f"  g7_summary:        {g7!r}")
        print(f"  bid_backoff_bps:   {bid_bps}")
        print(f"  ask_backoff_bps:   {ask_bps}")
        print(f"  g2_grade:          {d.get('g2_grade')} spread_mult={d.get('g2_spread_mult')}")
        print(f"  worst_vs_touch:    {d.get('worst_vs_touch_bps')}")
        print(f"  visibility:        {d.get('quote_visibility_summary')}")
        bb, ba = d.get("best_bid_rlusd_per_xrp"), d.get("best_ask_rlusd_per_xrp")
        offers = d.get("open_offers") or []
        print(f"  touch bb/ba:         {bb} / {ba}")
        for o in offers[:4]:
            side = o.get("side")
            p = float(o.get("price") or 0)
            if side == "bid" and bb:
                bps = (p - bb) / bb * 10_000
            elif side == "ask" and ba:
                bps = (p - ba) / ba * 10_000
            else:
                bps = None
            print(f"  offer {side}: {p:.6f} size={o.get('size_xrp')} vs_touch={bps:+.1f}bps" if bps is not None else f"  offer {side}: {p}")
        intents = d.get("quote_intents") or []
        for qi in intents[:4]:
            if not qi.get("active", True) and isinstance(qi, dict):
                continue
            side = qi.get("side") if isinstance(qi, dict) else getattr(qi, "side", None)
            p = float((qi.get("price") if isinstance(qi, dict) else qi.price) or 0)
            if side == "bid" and bb:
                bps = (p - bb) / bb * 10_000
            elif side == "ask" and ba:
                bps = (p - ba) / ba * 10_000
            else:
                bps = None
            if bps is not None:
                print(f"  intent L1 {side}: {p:.6f} planned vs_touch={bps:+.1f}bps")
        g7_ok = ws == "2.1.16" and bool(g7) and bid_bps is not None and ask_bps is not None
        print(f"\n  G7 fields present: {g7_ok}")
        if g7 and bid_bps != ask_bps:
            print("  asymmetric backoff: YES (G7 inventory rule applied)")
        elif g7:
            print("  asymmetric backoff: no (balanced or G2 widened both equally)")
    else:
        print("runtime_state.json missing")

    if LOG.exists():
        text = LOG.read_text(encoding="utf-8", errors="replace")
        idx = text.rfind("WsPureTradingEngine v2.1.16")
        chunk = text[idx:] if idx >= 0 else ""
        g7_lines = [ln for ln in chunk.splitlines() if "G7 " in ln or "g7" in ln.lower()]
        summaries = [ln for ln in chunk.splitlines() if "G7 xrp_heavy" in ln or "G7 rlusd_heavy" in ln or "G7 balanced" in ln]
        print("\n[engine log since v2.1.16 start]")
        print(f"  v2.1.16 start found: {idx >= 0}")
        if summaries:
            print(f"  sample decision G7 refs: {len(summaries)}")
            print("   ", summaries[-1][-140:])
        # quote decision summaries in decisions - check recent placed prices
        places = re.findall(
            r"Placed (bid|ask) L1 offer \| size=([\d.]+) XRP price=([\d.]+)",
            chunk,
        )
        if places and RT.exists():
            d = json.loads(RT.read_text(encoding="utf-8"))
            bb = float(d.get("best_bid_rlusd_per_xrp") or 0)
            ba = float(d.get("best_ask_rlusd_per_xrp") or 0)
            print(f"\n  recent placements since 2.1.16: {len(places)}")
            for side, sz, price in places[-6:]:
                p = float(price)
                if side == "bid" and bb > 0:
                    bps = (p - bb) / bb * 10_000
                elif side == "ask" and ba > 0:
                    bps = (p - ba) / ba * 10_000
                else:
                    bps = 0
                print(f"    {side} {sz} XRP @ {p:.6f} (~{bps:+.1f} bps vs current touch)")

    if INTEL.exists():
        lines = INTEL.read_text(encoding="utf-8", errors="replace").splitlines()
        recent = [json.loads(ln) for ln in lines[-80:] if ln.strip()]
        g7_intel = [r for r in recent if "g7" in json.dumps(r).lower()]
        print(f"\n[intel_decisions.jsonl tail]")
        print(f"  rows with g7 in last 80: {len(g7_intel)} (engine_dec may carry g7 via cycle record)")


if __name__ == "__main__":
    main()
