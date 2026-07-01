#!/usr/bin/env python3
"""Replay soak JSONL with book+AMM fill simulation at realistic notional sizes."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from experimental.arb.clob_amm_monitor import augment_clob_amm_row
from experimental.arb.fill_simulator import (
    AmmPool,
    best_roundtrip,
    mid_edge_bps,
    row_has_fill_snapshot,
    simulate_from_soak_row,
    summarize_fill_results,
)
from experimental.arb.book_provider import (
    TokenXrpBookDepth,
    book_depth_from_json,
    book_depth_to_json,
    fetch_token_xrp_book_depth_sync,
)
from experimental.liquidity.amm_provider import fetch_amm_info_sync


def _parse_ts(raw: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_jsonl_rows(path: Path) -> List[Tuple[datetime, Dict[str, Any]]]:
    out: List[Tuple[datetime, Dict[str, Any]]] = []
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("status") != "ok":
            continue
        ts = row.get("ts_utc")
        if not ts:
            continue
        dt = _parse_ts(str(ts))
        if dt is None:
            continue
        out.append((dt, row))
    out.sort(key=lambda item: item[0])
    return out


def _filter_window(
    rows: List[Tuple[datetime, Dict[str, Any]]],
    *,
    hours: Optional[float],
    use_all: bool,
) -> List[Tuple[datetime, Dict[str, Any]]]:
    if use_all or not rows:
        return rows
    end = rows[-1][0]
    start = end - timedelta(hours=float(hours or 24.0))
    return [(dt, row) for dt, row in rows if dt >= start]


def _live_snapshot(
    *,
    rpc_url: str,
    rlusd_issuer: str,
    rlusd_currency: str,
    book_limit: int,
) -> Dict[str, Any]:
    depth = fetch_token_xrp_book_depth_sync(
        rpc_url=rpc_url,
        currency=rlusd_currency,
        issuer=rlusd_issuer,
        limit=book_limit,
    )
    amm = fetch_amm_info_sync(
        rpc_url=rpc_url,
        rlusd_issuer=rlusd_issuer,
        rlusd_currency=rlusd_currency,
    ) or {}
    clob_mid = depth.mid
    amm_mid = amm.get("mid")
    row: Dict[str, Any] = {
        "kind": "clob_amm",
        "status": "ok",
        "ts_utc": datetime.now(tz=timezone.utc).isoformat(),
        "clob_mid_rlusd_per_xrp": clob_mid,
        "amm_mid_rlusd_per_xrp": amm_mid,
        "clob_spread_pct": depth.spread_pct,
        "book_depth": book_depth_to_json(depth),
        "amm_fee_bps": amm.get("trading_fee_bps"),
        "amm_xrp_reserve": amm.get("xrp_reserve"),
        "amm_rlusd_reserve": amm.get("rlusd_reserve"),
    }
    if clob_mid and amm_mid:
        from experimental.arb.clob_amm_monitor import spread_bps

        row["spread_bps"] = spread_bps(float(clob_mid), float(amm_mid))
    return augment_clob_amm_row(row)


def _simulate_row_at_notionals(
    row: Dict[str, Any],
    notionals: List[float],
) -> List[Dict[str, Any]]:
    mid = mid_edge_bps(row)
    out: List[Dict[str, Any]] = []
    for notional in notionals:
        sim = simulate_from_soak_row(row, notional_rlusd=notional)
        if sim is None:
            continue
        payload = sim.to_dict()
        payload["mid_edge_bps"] = mid
        payload["ts_utc"] = row.get("ts_utc")
        payload["net_positive_mid"] = bool(mid is not None and mid > 0)
        out.append(payload)
    return out


def _print_live_table(row: Dict[str, Any], notionals: List[float]) -> None:
    book = book_depth_from_json(row["book_depth"])
    pool = AmmPool(
        xrp_reserve=float(row["amm_xrp_reserve"]),
        rlusd_reserve=float(row["amm_rlusd_reserve"]),
        fee_bps=float(row.get("amm_fee_bps") or 10.0),
    )
    print("--- Live fill simulation (best direction per size) ---")
    print(
        f"clob mid={row.get('clob_mid_rlusd_per_xrp')} "
        f"amm mid={row.get('amm_mid_rlusd_per_xrp')} "
        f"mid net={row.get('net_edge_bps')} bps"
    )
    print(f"book levels: {len(book.bids)} bids / {len(book.asks)} asks")
    print(
        f"amm pool: {pool.xrp_reserve:.2f} XRP · {pool.rlusd_reserve:.2f} RLUSD "
        f"(fee {pool.fee_bps:.1f} bps)"
    )
    print()
    for notional in notionals:
        sim = best_roundtrip(notional_rlusd=notional, book=book, pool=pool)
        flag = "PROFIT" if sim.profit_bps > 0 else "loss"
        print(
            f"  {notional:>7.0f} RLUSD | {sim.direction:12} | "
            f"fill {sim.profit_bps:+.2f} bps | {sim.profit_rlusd:+.4f} RLUSD | "
            f"{flag} | {sim.note}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs-dir", type=Path, default=Path("logs"))
    parser.add_argument(
        "--notional",
        type=float,
        nargs="+",
        default=[500.0, 1000.0, 2000.0],
        help="RLUSD roundtrip sizes",
    )
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--all", action="store_true", help="Use entire JSONL window")
    parser.add_argument(
        "--net-plus-only",
        action="store_true",
        help="Only rows where mid-based net_edge_bps > 0",
    )
    parser.add_argument(
        "--with-depth-only",
        action="store_true",
        help="Only rows that captured book_depth + AMM reserves",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Fetch current book+AMM and simulate now (no JSONL required)",
    )
    parser.add_argument("--book-limit", type=int, default=20)
    args = parser.parse_args()

    notionals = [float(n) for n in args.notional if float(n) > 0]
    if not notionals:
        notionals = [500.0, 1000.0, 2000.0]

    if args.live:
        from config.settings import BotConfig

        cfg = BotConfig.load()
        row = _live_snapshot(
            rpc_url=cfg.resolved_rpc_url(),
            rlusd_issuer=cfg.resolved_rlusd_issuer(),
            rlusd_currency=cfg.resolved_rlusd_currency_code(),
            book_limit=args.book_limit,
        )
        print("=== ARB FILL SIMULATION (live) ===")
        print(f"generated_utc: {datetime.now(tz=timezone.utc).isoformat()}")
        _print_live_table(row, notionals)
        return

    path = args.logs_dir / "clob_amm_spread.jsonl"
    rows = _load_jsonl_rows(path)
    if not rows:
        print(f"No ok samples in {path}")
        print("Tip: depth capture ships with newer HUD polls — use --live for instant check.")
        return

    window = _filter_window(rows, hours=args.hours, use_all=args.all)
    end = window[-1][0]
    start = window[0][0]
    span_h = max((end - start).total_seconds() / 3600.0, 0.01)

    depth_rows = [(dt, row) for dt, row in window if row_has_fill_snapshot(row)]
    candidates = depth_rows if args.with_depth_only else window
    if args.net_plus_only:
        candidates = [
            (dt, row)
            for dt, row in candidates
            if (mid := mid_edge_bps(row)) is not None and mid > 0
        ]

    print("=== ARB FILL SIMULATION (soak replay) ===")
    print(f"generated_utc: {datetime.now(tz=timezone.utc).isoformat()}")
    print(f"path: {path}")
    print(
        f"window: {start.isoformat()} -> {end.isoformat()} ({span_h:.2f}h) | "
        f"ok_samples={len(window)} depth_samples={len(depth_rows)}"
    )
    if not depth_rows:
        print()
        print("No depth snapshots in JSONL yet — soak collector will add them on next polls.")
        print("Run with --live for current book walk, or wait ~1h and re-run.")
        return

    replay_rows = depth_rows if not args.with_depth_only else candidates
    if args.net_plus_only:
        replay_rows = [
            (dt, row)
            for dt, row in replay_rows
            if (mid := mid_edge_bps(row)) is not None and mid > 0
        ]

    for notional in notionals:
        results: List[Dict[str, Any]] = []
        for _dt, row in replay_rows:
            for item in _simulate_row_at_notionals(row, [notional]):
                results.append(item)
        summary = summarize_fill_results(results)
        print()
        print(f"--- Notional {notional:.0f} RLUSD ---")
        if summary.get("samples", 0) == 0:
            print("  no replay samples")
            continue
        print(
            f"  samples={summary['samples']} feasible={summary.get('feasible')} "
            f"({summary.get('feasible_pct')}%)"
        )
        print(
            f"  fill PROFIT: {summary.get('profitable')} ({summary.get('profitable_pct')}%)"
        )
        print(f"  avg mid edge:  {summary.get('avg_mid_edge_bps')} bps")
        print(f"  avg fill edge: {summary.get('avg_fill_edge_bps')} bps (feasible only)")
        print(
            f"  fill range:    {summary.get('min_profit_bps')} .. {summary.get('max_profit_bps')} bps "
            f"(median {summary.get('median_profit_bps')})"
        )
        if summary.get("avg_mid_edge_bps") is not None and summary.get("avg_fill_edge_bps") is not None:
            haircut = summary["avg_mid_edge_bps"] - summary["avg_fill_edge_bps"]
            print(f"  mid→fill haircut: {haircut:+.2f} bps")

        scale = 24.0 / span_h
        feasible_profit = [
            float(r["profit_rlusd"])
            for r in results
            if r.get("feasible") and float(r.get("profit_bps", 0)) > 0
        ]
        if feasible_profit:
            raw = sum(feasible_profit)
            print(
                f"  scaled 24h (every NET+ w/ depth, all profitable fills): "
                f"{raw * scale:+.2f} RLUSD"
            )

    if args.net_plus_only and not replay_rows:
        print()
        print("No NET+ rows with depth in window.")


if __name__ == "__main__":
    main()
