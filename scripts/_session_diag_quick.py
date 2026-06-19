#!/usr/bin/env python3
"""Quick session economics diag (VPS-safe, no xrpl import chain)."""
from __future__ import annotations

import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"


def _ts(s: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def main() -> int:
    rt_path = LOGS / "runtime_state.json"
    rt = json.loads(rt_path.read_text(encoding="utf-8"))
    boot = _ts(str(rt.get("session_boot_utc") or ""))
    if not boot:
        print("no session_boot_utc")
        return 1

    fills: list[dict] = []
    for p in sorted(LOGS.glob("trades_*.csv")):
        with p.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if "WS pure fill" not in (row.get("notes") or ""):
                    continue
                ts = _ts(row.get("timestamp_utc") or "")
                if ts and ts >= boot:
                    try:
                        cap = float(row.get("profit_xrp_equiv") or 0)
                    except (TypeError, ValueError):
                        cap = 0.0
                    try:
                        xrp = float(row.get("xrp_amount") or 0)
                    except (TypeError, ValueError):
                        xrp = 0.0
                    fills.append(
                        {
                            "ts": ts,
                            "side": (row.get("side") or row.get("event_type") or "?").upper(),
                            "xrp": xrp,
                            "cap": cap,
                        }
                    )

    print(f"boot: {boot.isoformat()}")
    print(f"fills_session (runtime): {rt.get('fills_session')}")
    print(f"session_spread_capture_xrp: {rt.get('session_spread_capture_xrp')}")
    print(f"toxic@30s: {rt.get('toxic_fill_ratio_30s')}")
    print()

    for k in (
        "wealth_rlusd",
        "wealth_delta_session_rlusd",
        "skim_delta_rlusd",
        "spot_delta_rlusd",
        "rebalance_delta_rlusd",
        "session_baseline_xrp",
        "session_baseline_rlusd",
        "session_baseline_mid",
        "balance_xrp",
        "balance_rlusd",
        "mid_price",
        "portfolio_value_xrp",
    ):
        if k in rt:
            print(f"{k}: {rt[k]}")

    print()
    print(f"CSV session fills: {len(fills)}")
    caps = [f["cap"] for f in fills]
    total = sum(caps)
    pos = sum(1 for c in caps if c > 0)
    neg = sum(1 for c in caps if c < 0)
    print(f"capture total: {total:+.6f} XRP | pos/neg: {pos}/{neg}")
    if fills:
        bps = [f["cap"] / f["xrp"] * 10_000 for f in fills if f["xrp"] > 0 and f["cap"] != 0]
        if bps:
            print(f"bps (nonzero): mean={statistics.mean(bps):.2f} median={statistics.median(bps):.2f}")

    by_side: dict[str, dict[str, float]] = {}
    for f in fills:
        s = f["side"]
        by_side.setdefault(s, {"n": 0, "cap": 0.0, "xrp": 0.0})
        by_side[s]["n"] += 1
        by_side[s]["cap"] += f["cap"]
        by_side[s]["xrp"] += f["xrp"]
    print("by side:")
    for s, v in sorted(by_side.items()):
        print(f"  {s}: n={int(v['n'])} cap={v['cap']:+.6f} xrp_vol={v['xrp']:.2f}")

    print("\nworst 8:")
    for f in sorted(fills, key=lambda x: x["cap"])[:8]:
        print(f"  {f['ts'].strftime('%H:%M:%S')} {f['side']} xrp={f['xrp']:.2f} cap={f['cap']:+.6f}")

    print("\nlast 10:")
    for f in fills[-10:]:
        print(f"  {f['ts'].strftime('%H:%M:%S')} {f['side']} xrp={f['xrp']:.2f} cap={f['cap']:+.6f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
