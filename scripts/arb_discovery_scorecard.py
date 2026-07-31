#!/usr/bin/env python3
"""
Paper arb discovery scorecard — are we + or −?

Reads logs/arb_discovery.jsonl (new) and falls back to clob_amm soak fill replay.
No live trades — hypothetical P&L if you had taken paper opportunities.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _parse_ts(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _f(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_discovery_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def paper_pnl_rlusd(profit_bps: float, notional: float = 500.0) -> float:
    """Hypothetical P&L if you traded `notional` RLUSD at that fill edge."""
    return notional * (profit_bps / 10_000.0)


def score_discovery_window(rows: List[Dict[str, Any]], *, hours: Optional[float] = None) -> Dict[str, Any]:
    now = datetime.now(tz=timezone.utc)
    filtered = rows
    if hours is not None and hours > 0:
        since = now - timedelta(hours=hours)
        filtered = []
        for r in rows:
            ts = _parse_ts(str(r.get("ts_utc") or ""))
            if ts is None or ts >= since:
                filtered.append(r)

    n = len(filtered)
    if n == 0:
        return {"samples": 0}

    mid_pos = fill_pos = fill_ge3 = actionable = 0
    mid_vals: List[float] = []
    fill250: List[float] = []
    fill500: List[float] = []
    fill1000: List[float] = []
    maker500: List[float] = []
    flags = Counter()
    paper_if_all_fill_plus = 0.0
    paper_if_actionable_only = 0.0
    paper_if_all_polls_500 = 0.0  # take every poll at fill@500 (even losses)

    for r in filtered:
        flags[str(r.get("flag") or "ok")] += 1
        mid = _f(r.get("mid_net_bps"))
        f250 = _f(r.get("fill_profit_bps_250"))
        f500 = _f(r.get("fill_profit_bps_500"))
        f1000 = _f(r.get("fill_profit_bps_1000"))
        m500 = _f(r.get("maker_opt_bps_500"))
        if mid is not None:
            mid_vals.append(mid)
            if mid > 0:
                mid_pos += 1
        if f250 is not None:
            fill250.append(f250)
        if f500 is not None:
            fill500.append(f500)
            paper_if_all_polls_500 += paper_pnl_rlusd(f500, 500.0)
            if f500 > 0:
                fill_pos += 1
                paper_if_all_fill_plus += paper_pnl_rlusd(f500, 500.0)
            if f500 >= 3.0:
                fill_ge3 += 1
        if f1000 is not None:
            fill1000.append(f1000)
        if m500 is not None:
            maker500.append(m500)
        if r.get("actionable"):
            actionable += 1
            if f500 is not None:
                paper_if_actionable_only += paper_pnl_rlusd(f500, 500.0)

    def stats(xs: List[float]) -> Dict[str, Any]:
        if not xs:
            return {"n": 0}
        s = sorted(xs)
        return {
            "n": len(xs),
            "mean": round(sum(xs) / len(xs), 2),
            "med": round(s[len(s) // 2], 2),
            "min": round(s[0], 2),
            "max": round(s[-1], 2),
            "pos_pct": round(100.0 * sum(1 for x in xs if x > 0) / len(xs), 1),
        }

    # Verdict: primary = mean fill@500; secondary = paper sum if traded every poll at 500
    mean_fill = sum(fill500) / len(fill500) if fill500 else None
    paper_sum = paper_if_all_polls_500
    if mean_fill is None:
        verdict = "NO_DATA"
        sign = "?"
    elif mean_fill > 0.5 and paper_sum > 0:
        verdict = "PLUS"
        sign = "+"
    elif mean_fill > 0 and paper_sum > 0:
        verdict = "SLIGHT_PLUS"
        sign = "+"
    elif mean_fill > -1.0 and fill_pos / max(n, 1) >= 0.2:
        verdict = "MIXED"
        sign = "~"
    else:
        verdict = "MINUS"
        sign = "-"

    return {
        "samples": n,
        "hours": hours,
        "mid_pos_pct": round(100.0 * mid_pos / n, 1),
        "fill_pos_pct": round(100.0 * fill_pos / n, 1) if fill500 else None,
        "fill_ge3_pct": round(100.0 * fill_ge3 / n, 1) if fill500 else None,
        "actionable_pct": round(100.0 * actionable / n, 1),
        "actionable_count": actionable,
        "flags": dict(flags),
        "mid_net": stats(mid_vals),
        "fill_250": stats(fill250),
        "fill_500": stats(fill500),
        "fill_1000": stats(fill1000),
        "maker_500": stats(maker500),
        "paper_pnl_rlusd": {
            "if_trade_every_poll_at_500": round(paper_if_all_polls_500, 4),
            "if_trade_only_fill_plus_at_500": round(paper_if_all_fill_plus, 4),
            "if_trade_only_actionable_at_500": round(paper_if_actionable_only, 4),
            "note": "Hypothetical RLUSD P&L assuming one 500 RLUSD round-trip per poll at that fill edge. Not real money.",
        },
        "verdict": verdict,
        "sign": sign,
        "headline": (
            f"{sign} paper arb @ fill500 mean={mean_fill:.2f} bps, "
            f"sum if every poll={paper_if_all_polls_500:+.4f} RLUSD"
            if mean_fill is not None
            else "No fill samples yet"
        ),
    }


def print_block(title: str, block: Dict[str, Any]) -> None:
    print(f"\n=== {title} ===")
    if block.get("samples", 0) == 0:
        print("  (no samples)")
        return
    print(f"  samples: {block['samples']}")
    print(f"  VERDICT: {block['sign']}  {block['verdict']}")
    print(f"  {block['headline']}")
    print(
        f"  mid+ {block['mid_pos_pct']}% · fill+ {block.get('fill_pos_pct')}% · "
        f"fill≥3bps {block.get('fill_ge3_pct')}% · actionable {block['actionable_pct']}% "
        f"({block['actionable_count']})"
    )
    for label, key in [
        ("mid_net", "mid_net"),
        ("fill@250", "fill_250"),
        ("fill@500", "fill_500"),
        ("fill@1000", "fill_1000"),
        ("maker@500", "maker_500"),
    ]:
        s = block.get(key) or {}
        if s.get("n"):
            print(
                f"  {label}: mean={s['mean']} med={s['med']} "
                f"min={s['min']} max={s['max']} pos%={s['pos_pct']}"
            )
    pp = block.get("paper_pnl_rlusd") or {}
    print("  paper P&L (RLUSD, hypothetical @ 500 size):")
    print(f"    every poll:     {pp.get('if_trade_every_poll_at_500')}")
    print(f"    only FILL+ :    {pp.get('if_trade_only_fill_plus_at_500')}")
    print(f"    only ACTIONABLE:{pp.get('if_trade_only_actionable_at_500')}")
    print(f"  flags: {block.get('flags')}")


def main() -> None:
    logs = ROOT / "logs"
    path = logs / "arb_discovery.jsonl"
    rows = load_discovery_rows(path)
    print("=== ARB DISCOVERY SCORECARD ===")
    print(f"as_of_utc: {datetime.now(tz=timezone.utc).isoformat()}")
    print(f"log: {path}  rows={len(rows)}")

    state_path = logs / "arb_discovery_state.json"
    if state_path.is_file():
        try:
            st = json.loads(state_path.read_text(encoding="utf-8"))
            print(f"state_updated: {st.get('updated_utc')}")
            pairs = st.get("pairs") or {}
            for pid, pst in pairs.items():
                print(
                    f"  dwell[{pid}]: streak={pst.get('fill_pos_streak')} "
                    f"actionable={pst.get('actionable')} last_fill500={pst.get('last_fill_bps_500')}"
                )
        except (OSError, json.JSONDecodeError):
            pass

    all_b = score_discovery_window(rows, hours=None)
    d1 = score_discovery_window(rows, hours=24)
    d7 = score_discovery_window(rows, hours=24 * 7)

    print_block("ALL TIME (discovery log)", all_b)
    print_block("LAST 24h", d1)
    print_block("LAST 7d", d7)

    # How to read
    print("\n=== HOW TO READ ===")
    print("  +  mean fill@500 > 0 AND paper sum if every poll > 0")
    print("  -  mean fill@500 clearly negative (typical XRPL CLOB↔AMM after costs)")
    print("  ~  mixed / small sample")
    print("  Primary number: fill@500 mean (bps). Mid net is noise.")
    print("  Paper P&L is NOT real money — assumes you hit every poll at 500 RLUSD.")
    print("  ACTIONABLE count = only high-quality, persistent, fundable paper hits.")

    # Overall one-liner from all-time or 24h if enough samples
    primary = d1 if d1.get("samples", 0) >= 10 else all_b
    sign = primary.get("sign", "?")
    print(f"\n>>> BOTTOM LINE: {sign}  {primary.get('verdict')} — {primary.get('headline')}")


if __name__ == "__main__":
    main()
