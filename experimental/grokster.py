#!/usr/bin/env python3
"""
Grokster: Validation harness for the committed WS + pure A-S direction.

We are committed. WS + pure Avellaneda-Stoikov (A-S) is the future of xledgermate.
No more alternate setups.

- WS architecture for fresh book state (BookFeed)
- Replicated long-run wiring (inventory, toxicity, momentum, dynamic policy, etc.)
- Pure A-S quoting engine using built-in protections only:
    reservation price (gamma) for inventory risk
    optimal spread (kappa + vol) for adverse selection

Hard gate + legacy heuristic guards (toxicity off-book, edge thin, etc.) are not part of the production path.

This script runs the pure path + comparison numbers against the sacred long-run data
(6226 cycles / 454 fills) solely to validate presence lift and safety before the wholesale
remote server replacement.

Economics extension (Cursor #1): capture sum, neg-fill %, balance-Δ proxy on the sacred
corpus via experimental.sacred_economics — same bar as doc 05 / Gate 2 Tier A.

All work on experimental branch. Sacred long-run (hard gate) remains untouched as data source.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from experimental.pure_as_quote_path import make_would_quote_fn, would_quote_pure
from experimental.sacred_economics import (
    format_economics_ab_report,
    format_economics_report,
    load_decision_lines,
    load_trades_rows,
    parse_decision_events,
    resolve_trades_path,
    run_economics_ab,
    compute_baseline_economics,
    compute_marginal_economics,
)
from strategy.avellaneda_strategy import AvellanedaStrategy


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Grokster: WS + pure A-S validation vs sacred long-run data")
    p.add_argument("--decisions", default="logs/decisions.jsonl", help="Path to decisions.jsonl")
    p.add_argument("--trades", default=None, help="Path to trades CSV (default: auto-resolve in logs/)")
    p.add_argument("--window", type=int, default=0, help="Last N decision lines (0 = full file)")
    p.add_argument("--lookahead", type=int, default=8, help="Cycles to look forward for marginal fill oracle")
    p.add_argument("--gamma", type=float, default=0.35)
    p.add_argument("--kappa", type=float, default=3.5)
    p.add_argument(
        "--ab",
        action="store_true",
        default=True,
        help="Run economics A/B: pure vs pure+pressure scenarios (default on)",
    )
    p.add_argument("--no-ab", action="store_false", dest="ab", help="Skip A/B table")
    p.add_argument(
        "--pressure-low",
        type=float,
        default=0.25,
        help="Pressure value for defensive/skim-harder A/B arm (0=defensive)",
    )
    p.add_argument(
        "--pressure-high",
        type=float,
        default=0.85,
        help="Pressure value for cautious A/B arm",
    )
    return p.parse_args()


def _reasons_from_line(line: str) -> str:
    _, reasons = parse_decision_events(line)
    return reasons


def _spread_inv_toxic(reasons: str) -> tuple[float, float, float]:
    spread_m = re.search(r"Book L1 spread ([\d.]+)%", reasons)
    spread = float(spread_m.group(1)) / 100.0 if spread_m else 0.001
    inv = 0.3 if "xrp_heavy" in reasons else (-0.3 if "rlusd_heavy" in reasons else 0.0)
    toxic = 0.2
    tm = re.search(r"toxic\s*~?\s*([\d.]+)", reasons, re.I)
    if tm:
        toxic = float(tm.group(1)) / 100.0
    return spread, inv, toxic


def _reservation_inside_book(as_strat: AvellanedaStrategy, spread: float, inv: float, mid: float = 1.09) -> bool:
    quote = as_strat.compute_avellaneda_quote(
        mid_price=mid,
        inventory_skew=inv,
        volatility_pct=0.0,
        book_spread_pct=spread,
    )
    half = max(spread / 2.0, 0.0001)
    dist = abs(quote.reservation_price - mid) / half
    return dist < 0.35


def _suggested_calibration(trades_path: Path, cycles: float = 6226.0) -> None:
    try:
        rows = load_trades_rows(trades_path)
        fills = [r for r in rows if (r.get("event_type") or "").upper() in ("BUY", "SELL")]
        fill_count = len(fills)
        if fill_count <= 0:
            return
        arrival_rate = fill_count / cycles
        suggested_kappa = max(2.0, min(5.0, 1.0 / max(arrival_rate, 0.01) * 0.8))
        suggested_gamma = 0.30 if fill_count > 300 else 0.40
        print(
            f"[CALIBRATION from run data] suggested_gamma={suggested_gamma:.2f} "
            f"suggested_kappa={suggested_kappa:.2f} (based on ~{fill_count} fills over ~{int(cycles)} cycles)"
        )
        print("Use these (or average with live pure A-S results) when updating AvellanedaStrategy defaults.")
    except OSError:
        pass


def main() -> None:
    args = _parse_args()
    dec = Path(args.decisions)
    tr = Path(args.trades) if args.trades else resolve_trades_path(dec.parent)
    max_lines = args.window if args.window > 0 else None
    lines = load_decision_lines(dec, max_lines)
    total = len(lines)

    print("=== GROKSTER: VALIDATION FOR COMMITTED WS + PURE A-S DIRECTION ===")
    print()
    print("WE ARE COMMITTED. WS + pure A-S (built-in protections) is the future of xledgermate.")
    print("No more alternate setups. This is the production path.")
    print()
    print("Long run scale (sacred testing ground data): decisions + trades CSV (validation only).")
    print(f"Decision window: {total} cycles" + (f" (last {args.window})" if args.window else " (full file)"))
    print("WS: simulated freshness (from real 30-min probes).")
    print("A-S: reservation price (gamma for inventory risk) + optimal spread (kappa/vol for adverse).")
    print("Pure path uses A-S math only (built-in protections). No hard gate. No legacy heuristic guards.")
    print("Economics: capture + neg-fill % + balance-delta proxy + marginal oracle (doc 05 style).")
    print()

    if tr:
        _suggested_calibration(tr)
        print()

    as_strat = AvellanedaStrategy(None, gamma=args.gamma, kappa=args.kappa)

    def pure_would_quote(line: str) -> bool:
        return would_quote_pure(as_strat, line)

    # --- Presence stats ---
    baseline_presence = 0
    zero_quote = 0
    hard_gate_blocks = 0
    ws_pure_presence = 0
    ws_pure_high_tox = 0

    for ln in lines:
        reasons = _reasons_from_line(ln)
        gen = 0
        m = re.search(r"Generated\s+(\d+)", reasons)
        if m:
            gen = int(m.group(1))
        if gen > 0:
            baseline_presence += 1
        else:
            zero_quote += 1
            if any(k in reasons.lower() for k in ("market_edge_met=false", "hard gate", "l1 too tight", "edge thin")):
                hard_gate_blocks += 1

        _, _, toxic = _spread_inv_toxic(reasons)
        if would_quote_pure(as_strat, ln):
            ws_pure_presence += 1
            if toxic > 0.25:
                ws_pure_high_tox += 1

    if total == 0:
        print(f"ERROR: no decision lines in {dec}")
        sys.exit(1)

    print("=== BASELINE (current heuristic + hard gate + all guards) ===")
    print(f"Presence in window: {baseline_presence} ({baseline_presence / total * 100:.1f}%)")
    print(f"0-quotes: {zero_quote} ({zero_quote / total * 100:.1f}%)")
    print(f"Hard-gate/edge-thin blocks: {hard_gate_blocks}")
    print()

    print("=== WS + PURE A-S (built-in protections ONLY) ===")
    print(f"Presence: {ws_pure_presence} ({ws_pure_presence / total * 100:.1f}%)")
    if ws_pure_presence:
        print(
            f"High-tox risk among presence: {ws_pure_high_tox} "
            f"({ws_pure_high_tox / ws_pure_presence * 100:.1f}%)"
        )
    print("Protection: A-S reservation + spread only. No hard gate, no legacy guards.")
    print()

    # --- Economics (Cursor queue #1) ---
    if tr and tr.exists():
        trades_rows = load_trades_rows(tr)
        baseline_eco = compute_baseline_economics(trades_rows, trades_path=str(tr))
        marginal_eco = compute_marginal_economics(
            lines,
            trades_rows,
            pure_would_quote,
            lookahead_cycles=args.lookahead,
            baseline_capture_xrp=baseline_eco.capture_xrp,
        )
        print(
            format_economics_report(
                baseline_eco,
                marginal_eco,
                presence_baseline_pct=baseline_presence / total * 100,
                presence_pure_pct=ws_pure_presence / total * 100,
            )
        )
        print()
        if args.ab:
            ab = run_economics_ab(
                lines,
                trades_rows,
                [
                    ("pure A-S", make_would_quote_fn(as_strat, "pure")),
                    (f"pure + pressure {args.pressure_low:.2f} (skim)", make_would_quote_fn(as_strat, "pressure", args.pressure_low)),
                    (f"pure + pressure 0.50 (neutral)", make_would_quote_fn(as_strat, "pressure", 0.50)),
                    (f"pure + pressure {args.pressure_high:.2f} (cautious)", make_would_quote_fn(as_strat, "pressure", args.pressure_high)),
                ],
                lookahead_cycles=args.lookahead,
                trades_path=str(tr),
            )
            print(format_economics_ab_report(ab))
    else:
        print("=== SACRED CORPUS ECONOMICS ===")
        print(f"SKIP: no trades CSV found (looked in {dec.parent})")
        print()

    print("=== SUMMARY (VALIDATION AGAINST SACRED LONG-RUN DATA) ===")
    print(f"Baseline (current hard-gate + heuristics): {baseline_presence / total * 100:.1f}% presence")
    print(
        f"WS + PURE A-S (committed direction):      {ws_pure_presence / total * 100:.1f}% presence "
        f"(+{(ws_pure_presence - baseline_presence) / total * 100:.1f}pp lift)"
    )
    print()
    print("COMMITTED: WS + pure A-S is the production strategy. Long-run hard-gate setup = data source only.")
    print("Economics oracle is upper-bound until live pure-path fills validate neg-fill % and balance delta.")
    print("Next: gamma/kappa calibration from full run + live pure A-S tester fills.")


if __name__ == "__main__":
    main()
