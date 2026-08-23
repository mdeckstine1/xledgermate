#!/usr/bin/env python3
"""One-shot performance audit from mirrored VPS logs (ignore deposits)."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOGS = Path(__file__).resolve().parent.parent / "logs" / "vps_audit"


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def mid_from(x: float, r: float, p: float) -> float | None:
    denom = p - x
    if abs(denom) < 1e-9:
        return None
    return r / denom


def main() -> None:
    sess = json.loads((LOGS / "alpha_session.json").read_text(encoding="utf-8"))
    week = json.loads((LOGS / "alpha_bag_week.json").read_text(encoding="utf-8"))
    deps = json.loads((LOGS / "operator_deposits.json").read_text(encoding="utf-8"))
    rt = json.loads((LOGS / "alpha_runtime_state.json").read_text(encoding="utf-8"))

    print("=" * 70)
    print("LIVE RUNTIME (alpha_runtime_state)")
    print("=" * 70)
    keys = [
        "version",
        "network",
        "dry_run",
        "trading_enabled",
        "kill_switch_active",
        "balance_xrp",
        "balance_rlusd",
        "mid_price",
        "portfolio_value_xrp",
        "session_baseline_xrp",
        "session_baseline_rlusd",
        "session_baseline_mid",
        "session_pnl_mtm_xrp",
        "session_pnl_balance_xrp",
        "session_spread_capture_xrp",
        "session_pnl_xrp_estimate",
        "cycle_count",
        "open_offers_count",
        "active_profile",
        "session_boot_utc",
        "last_execution_summary",
        "ws_as_version",
    ]
    for k in keys:
        if k in rt:
            print(f"  {k}: {rt.get(k)}")

    for block in (
        "inventory",
        "decision",
        "bag_growth",
        "acquisition_metrics",
        "realized_pnl_24h",
    ):
        if block in rt:
            s = json.dumps(rt[block], default=str)
            print(f"\n--- {block} ---")
            print(s[:3000])

    print("\nScalar runtime highlights:")
    for k in sorted(rt.keys()):
        kl = k.lower()
        if not any(
            x in kl
            for x in (
                "pnl",
                "bag",
                "invent",
                "fill",
                "spread",
                "baseline",
                "accum",
                "harvest",
                "bracket",
                "deposit",
                "balance",
                "mid",
                "portfolio",
                "cycle",
                "offer",
                "edge",
                "stack",
                "xrp",
                "rlusd",
            )
        ):
            continue
        v = rt[k]
        if isinstance(v, (dict, list)):
            continue
        print(f"  {k}={v}")

    print("\n" + "=" * 70)
    print("SESSION BASELINE vs NOW (alpha_session.json)")
    print("=" * 70)
    base_p = float(sess["baseline_portfolio_xrp"])
    last_p = float(sess["last_portfolio_xrp"])
    base_x = float(sess["baseline_xrp"])
    last_x = float(sess["last_xrp"])
    base_r = float(sess["baseline_rlusd"])
    last_r = float(sess["last_rlusd"])
    print(f"baseline_utc: {sess['baseline_utc']}")
    print(f"last_updated: {sess['last_updated_utc']}")
    print(f"portfolio XRP-eq: {base_p:.2f} -> {last_p:.2f}  raw Δ={last_p - base_p:+.2f}")
    print(f"XRP coins:        {base_x:.2f} -> {last_x:.2f}  raw Δ={last_x - base_x:+.2f}")
    print(f"RLUSD:            {base_r:.2f} -> {last_r:.2f}  raw Δ={last_r - base_r:+.2f}")

    dep_x = sum(float(d.get("xrp") or 0) for d in deps["deposits"])
    dep_r = sum(float(d.get("rlusd") or 0) for d in deps["deposits"])
    dep_eq = sum(float(d.get("xrp_equiv") or 0) for d in deps["deposits"])
    print("\nOperator deposits (excluded from bot edge):")
    for d in deps["deposits"]:
        print(
            f"  {d['recorded_utc'][:10]}  XRP={float(d['xrp']):+.2f}  "
            f"RLUSD={float(d['rlusd']):+.2f}  eq={float(d['xrp_equiv']):+.2f}  "
            f"note={d.get('note')!r}"
        )
    print(f"  TOTAL: {dep_x:.2f} XRP + {dep_r:.2f} RLUSD = {dep_eq:.2f} XRP-eq")

    bot_port = (last_p - base_p) - dep_eq
    bot_xrp = (last_x - base_x) - dep_x
    bot_rlusd = (last_r - base_r) - dep_r
    print("\n*** BOT-ADJUSTED (raw - deposits) ***")
    print(f"  portfolio XRP-eq Δ: {bot_port:+.2f}  ({100 * bot_port / base_p:+.2f}% of baseline)")
    print(f"  XRP stack coins Δ:  {bot_xrp:+.2f}")
    print(f"  RLUSD Δ:            {bot_rlusd:+.2f}")

    print("\n" + "=" * 70)
    print("THIS WEEK (Mon UTC)")
    print("=" * 70)
    print(f"week_start: {week['week_start_utc']}")
    print(
        f"portfolio: {week['week_start_portfolio_xrp']:.2f} -> "
        f"{week['last_portfolio_xrp']:.2f}  "
        f"Δ={week['last_portfolio_xrp'] - week['week_start_portfolio_xrp']:+.2f}"
    )
    print(
        f"XRP:       {week['week_start_xrp']:.2f} -> {week['last_xrp']:.2f}  "
        f"Δ={week['last_xrp'] - week['week_start_xrp']:+.2f}"
    )
    print(
        f"RLUSD:     {week['week_start_rlusd']:.2f} -> {week['last_rlusd']:.2f}  "
        f"Δ={week['last_rlusd'] - week['week_start_rlusd']:+.2f}"
    )

    print("\n" + "=" * 70)
    print("TAXABLE TRADES")
    print("=" * 70)
    rows: list[dict] = []
    for p in sorted(LOGS.glob("trades_*.csv")):
        with p.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                r["_file"] = p.name
                rows.append(r)
    print(f"total CSV rows: {len(rows)}")
    tax = [r for r in rows if str(r.get("taxable", "")).upper() == "Y"]
    print(f"taxable rows: {len(tax)}")

    by_month: Counter = Counter()
    buys_xrp = sells_xrp = 0.0
    realized = 0.0
    buy_n = sell_n = 0
    profit_pos = profit_neg = 0.0
    pos_n = neg_n = zero_n = 0
    notes_c: Counter = Counter()
    daily: dict = defaultdict(
        lambda: {
            "buy_xrp": 0.0,
            "sell_xrp": 0.0,
            "buy_n": 0,
            "sell_n": 0,
            "realized": 0.0,
        }
    )
    price_buy: list[float] = []
    price_sell: list[float] = []

    for r in tax:
        ts = parse_ts(r.get("timestamp_utc"))
        side = (r.get("side") or r.get("event_type") or "").upper()
        try:
            xrp = float(r.get("xrp_amount") or 0)
            rlusd = float(r.get("rlusd_amount") or 0)
            px = float(r.get("price_rlusd_per_xrp") or 0)
            profit = float(r.get("profit_xrp_equiv") or 0)
        except Exception:
            continue
        month = ts.strftime("%Y-%m") if ts else "?"
        day = ts.strftime("%Y-%m-%d") if ts else "?"
        by_month[(month, side)] += 1
        notes = (r.get("notes") or "")[:80]
        note_key = notes.split(" seq=")[0] if notes else "(empty)"
        notes_c[note_key] += 1
        if side == "BUY":
            buys_xrp += xrp
            buy_n += 1
            daily[day]["buy_xrp"] += xrp
            daily[day]["buy_n"] += 1
            if px:
                price_buy.append(px)
        elif side == "SELL":
            sells_xrp += xrp
            sell_n += 1
            realized += profit
            daily[day]["sell_xrp"] += xrp
            daily[day]["sell_n"] += 1
            daily[day]["realized"] += profit
            if px:
                price_sell.append(px)
            if profit > 1e-9:
                profit_pos += profit
                pos_n += 1
            elif profit < -1e-9:
                profit_neg += profit
                neg_n += 1
            else:
                zero_n += 1
        _ = rlusd

    print(f"BUY:  n={buy_n}  +{buys_xrp:.2f} XRP")
    print(f"SELL: n={sell_n}  -{sells_xrp:.2f} XRP")
    print(f"Net XRP from taxable trades: {buys_xrp - sells_xrp:+.2f}")
    print(f"Sum profit_xrp_equiv on SELLs: {realized:+.4f} XRP")
    print(f"  winning exits: n={pos_n} sum={profit_pos:+.4f}")
    print(f"  losing exits:  n={neg_n} sum={profit_neg:+.4f}")
    print(f"  zero/unattrib: n={zero_n}")
    if price_buy:
        print(f"avg buy px:  {sum(price_buy) / len(price_buy):.6f}")
    if price_sell:
        print(f"avg sell px: {sum(price_sell) / len(price_sell):.6f}")

    print("\nBy month/side:")
    for k, v in sorted(by_month.items()):
        print(f"  {k}: {v}")

    print("\nTop note types:")
    for k, v in notes_c.most_common(20):
        print(f"  {v:4d}  {k}")

    now = parse_ts(sess["last_updated_utc"]) or datetime.now(timezone.utc)
    for label, hours in [
        ("24h", 24),
        ("7d", 24 * 7),
        ("14d", 24 * 14),
        ("30d", 24 * 30),
        ("since_baseline", None),
    ]:
        if hours is None:
            since = parse_ts(sess["baseline_utc"])
        else:
            since = now - timedelta(hours=hours)
        b = s = 0.0
        bn = sn = 0
        real = 0.0
        tp = sl = other = 0
        for r in tax:
            ts = parse_ts(r.get("timestamp_utc"))
            if ts is None or (since and ts < since):
                continue
            side = (r.get("side") or "").upper()
            xrp = float(r.get("xrp_amount") or 0)
            profit = float(r.get("profit_xrp_equiv") or 0)
            notes = (r.get("notes") or "").lower()
            if side == "BUY":
                b += xrp
                bn += 1
            elif side == "SELL":
                s += xrp
                sn += 1
                real += profit
                if "take-profit" in notes or "take_profit" in notes:
                    tp += 1
                elif "stop-loss" in notes or "stop_loss" in notes:
                    sl += 1
                else:
                    other += 1
        print(
            f"\nWindow {label}: buys={bn} (+{b:.2f} XRP) sells={sn} (-{s:.2f} XRP) "
            f"net={b - s:+.2f} realized={real:+.4f} TP={tp} SL={sl} other_sell={other}"
        )

    print("\nDaily taxable activity (recent days with trades):")
    for d in sorted(daily.keys())[-30:]:
        x = daily[d]
        print(
            f"  {d}  buys={x['buy_n']:3d} +{x['buy_xrp']:8.2f}  "
            f"sells={x['sell_n']:3d} -{x['sell_xrp']:8.2f}  "
            f"net={x['buy_xrp'] - x['sell_xrp']:+8.2f}  realized={x['realized']:+.4f}"
        )

    print("\n" + "=" * 70)
    print("BRACKETS")
    print("=" * 70)
    br = json.loads((LOGS / "alpha_brackets.json").read_text(encoding="utf-8"))
    if isinstance(br, dict):
        print("top keys:", list(br.keys())[:25])
        records = br.get("records") or br.get("brackets") or br.get("items") or []
        if not records:
            for k, v in br.items():
                if isinstance(v, list):
                    records = v
                    print("using list under", k)
                    break
                if isinstance(v, dict) and v and all(isinstance(x, dict) for x in list(v.values())[:5]):
                    records = list(v.values())
                    print("using dict values under", k)
                    break
    else:
        records = br
    print(f"bracket records: {len(records)}")
    states: Counter = Counter()
    for r in records:
        if not isinstance(r, dict):
            continue
        st = str(r.get("state") or r.get("status") or "?")
        states[st] += 1
    print("states:", dict(states))
    if records and isinstance(records[0], dict):
        print("sample keys:", sorted(records[0].keys()))
        # summarize profit if present
        profit_keys = [
            k
            for k in records[0].keys()
            if any(x in k.lower() for x in ("profit", "pnl", "edge", "capture"))
        ]
        print("profit-ish keys:", profit_keys)
        # open vs closed counts with sizes
        openish = []
        closedish = []
        for r in records:
            if not isinstance(r, dict):
                continue
            st = str(r.get("state") or "").lower()
            if st in ("open", "active", "pending", "live"):
                openish.append(r)
            elif st in ("closed", "filled", "exited", "complete", "completed", "done", "cancelled", "canceled"):
                closedish.append(r)
        print(f"openish={len(openish)} closedish={len(closedish)}")
        # print a few samples
        for label, sample in (("open", openish[:3]), ("closed", closedish[:3]), ("any", records[:3])):
            if not sample:
                continue
            print(f"\n{label} samples:")
            for r in sample:
                slim = {
                    k: r.get(k)
                    for k in list(r.keys())[:18]
                }
                print(" ", {k: slim[k] for k in slim if slim[k] not in (None, "", [], {})})

    for name in (
        "accumulation_session.json",
        "harvest_session.json",
        "drawdown_reload_session.json",
        "alpha_strength_sells.json",
    ):
        p = LOGS / name
        print(f"\n=== {name} ===")
        print(p.read_text(encoding="utf-8")[:2000])

    print("\n" + "=" * 70)
    print("HOLD BENCHMARK (baseline + deposits @ current mid)")
    print("=" * 70)
    m0 = mid_from(base_x, base_r, base_p)
    m1 = mid_from(last_x, last_r, last_p)
    rt_mid = rt.get("mid_price")
    print(f"implied mid baseline: {m0}")
    print(f"implied mid now:      {m1}")
    print(f"runtime mid_price:    {rt_mid}")
    use_mid = float(rt_mid or m1 or 0) or None
    if use_mid and use_mid > 0:
        baseline_at_now = base_x + base_r / use_mid
        deposits_at_now = dep_x + dep_r / use_mid
        expected_if_hold = baseline_at_now + deposits_at_now
        print(f"using mid={use_mid:.6f}")
        print(f"baseline bag @ now mid: {baseline_at_now:.2f}")
        print(f"deposits @ now mid:     {deposits_at_now:.2f}")
        print(f"expected if hold only:  {expected_if_hold:.2f}")
        print(f"actual portfolio now:   {last_p:.2f}")
        print(f"trading edge vs hold:   {last_p - expected_if_hold:+.2f} XRP-eq")
        print("(positive = beat buy-and-hold of baseline+deposits at current mid)")

    # Fee/activity churn estimate from activity log tail
    act = LOGS / "alpha_activity.jsonl"
    if act.is_file():
        print("\n" + "=" * 70)
        print("ACTIVITY LOG (tail stats)")
        print("=" * 70)
        # sample last ~2000 lines for categories
        lines = act.read_text(encoding="utf-8", errors="replace").splitlines()
        print(f"total activity lines: {len(lines)}")
        cats: Counter = Counter()
        msgs: Counter = Counter()
        recent = lines[-3000:]
        for line in recent:
            try:
                o = json.loads(line)
            except Exception:
                continue
            cat = str(o.get("category") or o.get("kind") or o.get("type") or "?")
            cats[cat] += 1
            msg = str(o.get("message") or o.get("msg") or "")[:70]
            if msg:
                # normalize numbers a bit
                msgs[msg.split("|")[0][:50]] += 1
        print("categories (last 3000 lines):")
        for k, v in cats.most_common(20):
            print(f"  {v:5d}  {k}")
        print("message prefixes:")
        for k, v in msgs.most_common(15):
            print(f"  {v:5d}  {k}")

    print("\nDONE")


if __name__ == "__main__":
    main()
