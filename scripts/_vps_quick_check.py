#!/usr/bin/env python3
"""Quick VPS soak health snapshot."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/root/xledgermate")
LOG = ROOT / "logs/xledgermate.log"
HUD_LOG = ROOT / "logs/ws_hud.log"
RT = ROOT / "logs/runtime_state.json"
CSV_DIR = ROOT / "logs"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _tail_errors(path: Path, n: int = 400) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    out = []
    for line in lines:
        if re.search(r"ERROR|CRITICAL|Traceback|Exception|failed", line, re.I):
            if "HTTP/1.1 200" in line:
                continue
            out.append(line)
    return out[-15:]


def _count_csv_fills() -> dict:
    """Session-ish fills from current month CSV."""
    from datetime import datetime as dt

    month = dt.now(timezone.utc).strftime("%Y-%m")
    buys = CSV_DIR / f"buys_{month}.csv"
    sells = CSV_DIR / f"sells_{month}.csv"
    counts = {"buys_csv_month": 0, "sells_csv_month": 0}
    for key, path in (("buys_csv_month", buys), ("sells_csv_month", sells)):
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        counts[key] = max(0, len(lines) - 1)
    counts["csv_total_month"] = counts["buys_csv_month"] + counts["sells_csv_month"]
    return counts


def main() -> None:
    print("=== services ===")
    for svc in ("xledgermate", "xledgermate-ws-hud"):
        try:
            r = subprocess.run(
                ["systemctl", "is-active", svc],
                capture_output=True,
                text=True,
                check=False,
            )
            print(f"{svc}: {r.stdout.strip() or r.stderr.strip()}")
        except Exception as exc:
            print(f"{svc}: check failed ({exc})")

    rt = _load_json(RT)
    now = datetime.now(timezone.utc).isoformat()
    print("\n=== runtime (engine) ===")
    print(f"checked_utc: {now}")
    print(f"updated_utc: {rt.get('updated_utc')}")
    print(f"ws_as_version: {rt.get('ws_as_version')}")
    print(f"engine_pid: {rt.get('engine_pid')}")
    print(f"cycle_count: {rt.get('cycle_count')}")
    print(f"sample_count: {rt.get('sample_count')}")
    print(f"fills_session: {rt.get('fills_session')}")
    print(f"session_spread_capture_xrp: {rt.get('session_spread_capture_xrp')}")
    print(f"session_pnl_balance_xrp: {rt.get('session_pnl_balance_xrp')}")
    print(f"as_presence_pct: {rt.get('as_presence_pct')}")
    print(f"toxic_fill_ratio_30s: {rt.get('toxic_fill_ratio_30s')}")
    print(f"mean_markout_30s_pct: {rt.get('mean_markout_30s_pct')}")
    print(f"g2_grade: {rt.get('g2_grade')} g2_active={rt.get('g2_active')}")
    print(f"kill_switch_active: {rt.get('kill_switch_active')} reason={rt.get('kill_switch_reason')!r}")
    print(f"open_offers_count: {rt.get('open_offers_count')}")
    print(f"market_edge_met: {rt.get('market_edge_met')}")
    print(f"inventory_label: {rt.get('inventory_label')}")
    print(f"pause_bids/asks: {rt.get('pause_bids')}/{rt.get('pause_asks')}")
    print(f"effective_quote_age_at_fill_seconds: {rt.get('effective_quote_age_at_fill_seconds')}")
    print(f"reservation_crossed_after_ws_sample: {rt.get('reservation_crossed_after_ws_sample')}")
    hist = rt.get("sample_history") or []
    print(f"sample_history_len: {len(hist)}")
    if hist:
        last = hist[-1]
        print(
            f"last_sample: would_quote={last.get('would_quote')} "
            f"zero_reason={last.get('zero_quote_reason')} ws_age={last.get('ws_book_age_s')}"
        )

    csv = _count_csv_fills()
    print("\n=== fills (CSV month) ===")
    for k, v in csv.items():
        print(f"{k}: {v}")

    trades = CSV_DIR / "trades_2026-06.csv"
    if trades.exists():
        import csv as csvmod

        rows = list(csvmod.DictReader(trades.open(encoding="utf-8")))
        post_restart = [
            r
            for r in rows
            if (r.get("timestamp") or "").startswith("2026-06-18 10:4")
            or (r.get("timestamp") or "").startswith("2026-06-18 10:5")
        ]
        print(f"trades_since_1041_utc: {len(post_restart)}")
        for r in post_restart[-5:]:
            print(
                " ",
                r.get("timestamp"),
                r.get("side"),
                f"xrp={r.get('xrp_amount')}",
                f"profit={r.get('profit_xrp_equiv')}",
                (r.get("notes") or "")[:70],
            )

    offers = rt.get("open_offers") or []
    if offers:
        print("\n=== open offers ===")
        for o in offers[:4]:
            print(f"  {o.get('side')} @ {o.get('price')} size={o.get('size_xrp')}")

    # Engine start line
    if LOG.exists():
        starts = [
            ln
            for ln in LOG.read_text(encoding="utf-8", errors="replace").splitlines()
            if "WsPureTradingEngine v" in ln
        ]
        if starts:
            print(f"\nengine_start: {starts[-1][-160:]}")

    print("\n=== recent engine errors ===")
    errs = _tail_errors(LOG)
    if errs:
        for e in errs:
            print(e)
    else:
        print("(none in last 400 log lines)")

    print("\n=== recent HUD errors ===")
    herrs = _tail_errors(HUD_LOG)
    if herrs:
        for e in herrs:
            print(e)
    else:
        print("(none in last 400 log lines or no hud log)")


if __name__ == "__main__":
    main()
