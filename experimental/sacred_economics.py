"""
Sacred corpus economics — capture, neg-fill %, balance-delta proxy (doc 05 style).

Used by grokster and replay_long_run to score baseline vs pure-A-S marginal cycles
on the same labeled long-run data (decisions + trades CSV). Marginal attribution uses
forward-window fill oracle: fills on cycles after a baseline-block / pure-would-quote
decision — an upper-bound proxy, not a proven counterfactual.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


def resolve_trades_path(logs_dir: Path, explicit: Optional[Path] = None) -> Optional[Path]:
    if explicit and explicit.exists():
        return explicit
    for name in ("vps_trades_2026-06.csv", "trades_2026-06.csv", "trades_2026-05.csv"):
        p = logs_dir / name
        if p.exists():
            return p
    candidates = sorted(logs_dir.glob("trades_*.csv"), reverse=True)
    return candidates[0] if candidates else None


def load_trades_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _is_taxable_fill(row: Dict[str, str]) -> bool:
    et = (row.get("event_type") or "").upper()
    side = (row.get("side") or et).upper()
    if side not in ("BUY", "SELL"):
        return False
    return (row.get("taxable") or "Y").upper() == "Y"


def _float(row: Dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key) or default)
    except (TypeError, ValueError):
        return default


def _portfolio_xrp_equiv(xrp: float, rlusd: float, mid: float) -> float:
    if mid <= 0:
        return xrp
    return xrp + rlusd / mid


@dataclass
class BaselineEconomics:
    fill_count: int = 0
    capture_xrp: float = 0.0
    neg_fill_count: int = 0
    volume_xrp: float = 0.0
    capture_bps: float = 0.0
    capture_per_fill: float = 0.0
    neg_fill_pct: float = 0.0
    balance_delta_xrp_proxy: float = 0.0
    first_portfolio_xrp: Optional[float] = None
    last_portfolio_xrp: Optional[float] = None
    trades_path: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "fill_count": self.fill_count,
            "capture_xrp": round(self.capture_xrp, 6),
            "neg_fill_count": self.neg_fill_count,
            "neg_fill_pct": round(self.neg_fill_pct, 2),
            "volume_xrp": round(self.volume_xrp, 4),
            "capture_bps": round(self.capture_bps, 3),
            "capture_per_fill": round(self.capture_per_fill, 6),
            "balance_delta_xrp_proxy": round(self.balance_delta_xrp_proxy, 6),
            "first_portfolio_xrp": self.first_portfolio_xrp,
            "last_portfolio_xrp": self.last_portfolio_xrp,
            "trades_path": self.trades_path,
        }


def compute_baseline_economics(trades_rows: Sequence[Dict[str, str]], trades_path: str = "") -> BaselineEconomics:
    fills = [r for r in trades_rows if _is_taxable_fill(r)]
    out = BaselineEconomics(trades_path=trades_path)
    out.fill_count = len(fills)
    if not fills:
        return out

    captures: List[float] = []
    for row in fills:
        cap = _float(row, "profit_xrp_equiv")
        captures.append(cap)
        out.capture_xrp += cap
        out.volume_xrp += _float(row, "xrp_amount")
        if cap < 0:
            out.neg_fill_count += 1

    out.neg_fill_pct = 100.0 * out.neg_fill_count / out.fill_count
    out.capture_per_fill = out.capture_xrp / out.fill_count
    out.capture_bps = (out.capture_xrp / out.volume_xrp * 10000.0) if out.volume_xrp > 0 else 0.0

    first, last = fills[0], fills[-1]
    mid_first = _float(first, "price_rlusd_per_xrp") or 1.09
    mid_last = _float(last, "price_rlusd_per_xrp") or mid_first
    x0 = _float(first, "balance_xrp_after")
    r0 = _float(first, "balance_rlusd_after")
    x1 = _float(last, "balance_xrp_after")
    r1 = _float(last, "balance_rlusd_after")
    if x0 or r0:
        out.first_portfolio_xrp = _portfolio_xrp_equiv(x0, r0, mid_first)
    if x1 or r1:
        out.last_portfolio_xrp = _portfolio_xrp_equiv(x1, r1, mid_last)
    if out.first_portfolio_xrp is not None and out.last_portfolio_xrp is not None:
        out.balance_delta_xrp_proxy = out.last_portfolio_xrp - out.first_portfolio_xrp

    return out


def load_decision_lines(path: Path, max_lines: Optional[int] = None) -> List[str]:
    if not path.exists():
        return []
    lines = [ln for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
    if max_lines is not None and max_lines > 0:
        lines = lines[-max_lines:]
    return lines


def parse_decision_events(line: str) -> Tuple[int, str]:
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        return 0, ""
    cycle = int(d.get("cycle") or 0)
    reasons = " ".join(e.get("message", "") for e in d.get("events", []))
    return cycle, reasons


def baseline_blocked(reasons: str) -> bool:
    lower = reasons.lower()
    gen = 0
    m = re.search(r"Generated\s+(\d+)", reasons, re.I)
    if m:
        gen = int(m.group(1))
    if gen > 0:
        return False
    return any(
        k in lower
        for k in ("market_edge_met=false", "hard gate", "l1 too tight", "edge thin", "generated 0 quotes")
    )


def build_trades_by_cycle(trades_rows: Sequence[Dict[str, str]]) -> Dict[int, List[Dict[str, str]]]:
    by_cycle: Dict[int, List[Dict[str, str]]] = {}
    for row in trades_rows:
        if not _is_taxable_fill(row):
            continue
        try:
            cycle = int(row.get("cycle") or 0)
        except (TypeError, ValueError):
            continue
        if cycle > 0:
            by_cycle.setdefault(cycle, []).append(row)
    return by_cycle


@dataclass
class MarginalEconomics:
    decision_cycles: int = 0
    baseline_blocked_cycles: int = 0
    pure_would_quote_cycles: int = 0
    marginal_cycles: int = 0
    marginal_with_fill_in_window: int = 0
    marginal_capture_xrp: float = 0.0
    marginal_neg_fills: int = 0
    marginal_fill_count: int = 0
    marginal_neg_fill_pct: float = 0.0
    marginal_capture_per_fill: float = 0.0
    projected_capture_upper_bound: float = 0.0
    lookahead_cycles: int = 8
    attribution_note: str = field(
        default=(
            "Marginal capture sums fills in [cycle+1 .. cycle+lookahead] after baseline-block "
            "cycles where pure would quote. Oracle proxy only - not proven counterfactual."
        )
    )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "decision_cycles": self.decision_cycles,
            "baseline_blocked_cycles": self.baseline_blocked_cycles,
            "pure_would_quote_cycles": self.pure_would_quote_cycles,
            "marginal_cycles": self.marginal_cycles,
            "marginal_with_fill_in_window": self.marginal_with_fill_in_window,
            "marginal_capture_xrp": round(self.marginal_capture_xrp, 6),
            "marginal_fill_count": self.marginal_fill_count,
            "marginal_neg_fills": self.marginal_neg_fills,
            "marginal_neg_fill_pct": round(self.marginal_neg_fill_pct, 2),
            "marginal_capture_per_fill": round(self.marginal_capture_per_fill, 6),
            "projected_capture_upper_bound": round(self.projected_capture_upper_bound, 6),
            "lookahead_cycles": self.lookahead_cycles,
            "attribution_note": self.attribution_note,
        }


def compute_marginal_economics(
    decision_lines: Sequence[str],
    trades_rows: Sequence[Dict[str, str]],
    pure_would_quote: Callable[[str], bool],
    *,
    lookahead_cycles: int = 8,
    baseline_capture_xrp: float = 0.0,
) -> MarginalEconomics:
    by_cycle = build_trades_by_cycle(trades_rows)
    out = MarginalEconomics(lookahead_cycles=lookahead_cycles)
    seen_fill_keys: set[Tuple[int, str]] = set()

    for line in decision_lines:
        cycle, reasons = parse_decision_events(line)
        if cycle <= 0:
            continue
        out.decision_cycles += 1

        blocked = baseline_blocked(reasons)
        if blocked:
            out.baseline_blocked_cycles += 1

        if not pure_would_quote(line):
            continue
        out.pure_would_quote_cycles += 1
        if not blocked:
            continue

        out.marginal_cycles += 1
        window_capture = 0.0
        window_fills = 0
        window_neg = 0

        for offset in range(1, lookahead_cycles + 1):
            for row in by_cycle.get(cycle + offset, []):
                key = (cycle + offset, row.get("tx_hash") or row.get("timestamp_utc") or str(window_fills))
                if key in seen_fill_keys:
                    continue
                seen_fill_keys.add(key)
                cap = _float(row, "profit_xrp_equiv")
                window_capture += cap
                window_fills += 1
                if cap < 0:
                    window_neg += 1

        if window_fills:
            out.marginal_with_fill_in_window += 1
            out.marginal_capture_xrp += window_capture
            out.marginal_fill_count += window_fills
            out.marginal_neg_fills += window_neg

    if out.marginal_fill_count:
        out.marginal_neg_fill_pct = 100.0 * out.marginal_neg_fills / out.marginal_fill_count
        out.marginal_capture_per_fill = out.marginal_capture_xrp / out.marginal_fill_count

    out.projected_capture_upper_bound = baseline_capture_xrp + out.marginal_capture_xrp
    return out


def format_economics_report(
    baseline: BaselineEconomics,
    marginal: MarginalEconomics,
    *,
    presence_baseline_pct: Optional[float] = None,
    presence_pure_pct: Optional[float] = None,
) -> str:
    lines = [
        "=== SACRED CORPUS ECONOMICS (doc 05 / Tier A style) ===",
        "",
        "--- Baseline (actual fills in trades CSV) ---",
        f"Fills: {baseline.fill_count}",
        f"Spread capture: {baseline.capture_xrp:+.6f} XRP",
        f"Capture / fill: {baseline.capture_per_fill:+.6f} XRP | ~{baseline.capture_bps:.2f} bps vs filled volume",
        f"Negative capture fills: {baseline.neg_fill_count}/{baseline.fill_count} ({baseline.neg_fill_pct:.1f}%)",
    ]
    if baseline.first_portfolio_xrp is not None and baseline.last_portfolio_xrp is not None:
        lines.append(
            f"Balance-delta proxy (portfolio XRP-equiv first->last fill): "
            f"{baseline.balance_delta_xrp_proxy:+.6f} XRP "
            f"({baseline.first_portfolio_xrp:.4f} -> {baseline.last_portfolio_xrp:.4f})"
        )
    if baseline.trades_path:
        lines.append(f"Source: {baseline.trades_path}")
    lines.extend(
        [
            "",
            "--- Marginal (baseline blocked + pure would quote -> forward-window fill oracle) ---",
            f"Decision cycles in window: {marginal.decision_cycles}",
            f"Baseline blocked (0-quote / edge / hard gate): {marginal.baseline_blocked_cycles}",
            f"Pure would quote: {marginal.pure_would_quote_cycles}",
            f"Marginal (blocked AND pure would quote): {marginal.marginal_cycles}",
            f"Marginal cycles with >=1 fill in next {marginal.lookahead_cycles} cycles: "
            f"{marginal.marginal_with_fill_in_window}",
            f"Marginal attributed capture: {marginal.marginal_capture_xrp:+.6f} XRP "
            f"({marginal.marginal_fill_count} fills, {marginal.marginal_neg_fill_pct:.1f}% neg)",
            f"Marginal capture / attributed fill: {marginal.marginal_capture_per_fill:+.6f} XRP",
            f"Projected capture upper bound (baseline + marginal oracle): "
            f"{marginal.projected_capture_upper_bound:+.6f} XRP",
            f"Note: {marginal.attribution_note}",
        ]
    )
    if presence_baseline_pct is not None and presence_pure_pct is not None:
        lines.extend(
            [
                "",
                "--- Presence context (decision window; not economics by itself) ---",
                f"Baseline presence: {presence_baseline_pct:.1f}%",
                f"Pure A-S presence: {presence_pure_pct:.1f}% (+{presence_pure_pct - presence_baseline_pct:.1f} pp)",
            ]
        )
    lines.append("")
    lines.append(
        "Interpretation: presence lift is necessary but not sufficient. "
        "Marginal oracle capture is an upper-bound hypothesis until live pure-path fills validate neg-fill % and balance delta."
    )
    return "\n".join(lines)


@dataclass
class EconomicsABRow:
    label: str
    marginal: MarginalEconomics
    would_quote_cycles: int = 0
    decision_cycles: int = 0

    @property
    def presence_pct(self) -> float:
        if self.decision_cycles <= 0:
            return 0.0
        return 100.0 * self.would_quote_cycles / self.decision_cycles


@dataclass
class EconomicsABComparison:
    baseline: BaselineEconomics
    rows: List[EconomicsABRow]
    lookahead_cycles: int = 8
    grok_note: str = (
        "Grok/xAI excluded from economics A/B — advisory and competition research only "
        "until post-swap sign-off (PURE_AS_CRITICAL_PATH)."
    )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "baseline": self.baseline.as_dict(),
            "lookahead_cycles": self.lookahead_cycles,
            "grok_note": self.grok_note,
            "variants": [
                {
                    "label": r.label,
                    "presence_pct": round(r.presence_pct, 1),
                    "would_quote_cycles": r.would_quote_cycles,
                    "marginal": r.marginal.as_dict(),
                }
                for r in self.rows
            ],
        }


def run_economics_ab(
    decision_lines: Sequence[str],
    trades_rows: Sequence[Dict[str, str]],
    variants: Sequence[Tuple[str, Callable[[str], bool]]],
    *,
    lookahead_cycles: int = 8,
    trades_path: str = "",
) -> EconomicsABComparison:
    baseline = compute_baseline_economics(trades_rows, trades_path=trades_path)
    rows: List[EconomicsABRow] = []
    for label, would_fn in variants:
        marginal = compute_marginal_economics(
            decision_lines,
            trades_rows,
            would_fn,
            lookahead_cycles=lookahead_cycles,
            baseline_capture_xrp=baseline.capture_xrp,
        )
        wq = sum(1 for ln in decision_lines if would_fn(ln))
        dc = sum(1 for ln in decision_lines if parse_decision_events(ln)[0] > 0)
        rows.append(
            EconomicsABRow(
                label=label,
                marginal=marginal,
                would_quote_cycles=wq,
                decision_cycles=dc,
            )
        )
    return EconomicsABComparison(
        baseline=baseline,
        rows=list(rows),
        lookahead_cycles=lookahead_cycles,
    )


def format_economics_ab_report(comparison: EconomicsABComparison) -> str:
    b = comparison.baseline
    lines = [
        "=== SACRED CORPUS ECONOMICS A/B (Phase A1) ===",
        "",
        f"Note: {comparison.grok_note}",
        "",
        "--- Baseline (actual fills in trades CSV) ---",
        f"Fills: {b.fill_count} | Capture: {b.capture_xrp:+.6f} XRP | Neg: {b.neg_fill_pct:.1f}%",
        f"Balance-delta proxy: {b.balance_delta_xrp_proxy:+.6f} XRP",
        "",
        f"{'Variant':<28} {'Presence':>9} {'Marginal':>9} {'Marg cap':>12} {'Neg%':>7} {'Upper bnd':>12}",
        f"{'':28} {'':>9} {'cycles':>9} {'XRP':>12} {'fills':>7} {'XRP':>12}",
        "-" * 82,
    ]
    for row in comparison.rows:
        m = row.marginal
        lines.append(
            f"{row.label:<28} {row.presence_pct:>8.1f}% {m.marginal_cycles:>9} "
            f"{m.marginal_capture_xrp:>+12.6f} {m.marginal_neg_fill_pct:>6.1f}% "
            f"{m.projected_capture_upper_bound:>+12.6f}"
        )
    lines.extend(
        [
            "",
            "Marginal = baseline-blocked cycles where variant would quote; capture from fills in next "
            f"{comparison.lookahead_cycles} cycles (oracle upper bound, not counterfactual).",
            "Compare pure vs +pressure: does defensive pressure change would-quote or attributed capture?",
        ]
    )
    if len(comparison.rows) >= 2:
        p0, p1 = comparison.rows[0], comparison.rows[1]
        d_cap = p1.marginal.marginal_capture_xrp - p0.marginal.marginal_capture_xrp
        d_pres = p1.presence_pct - p0.presence_pct
        lines.append(
            f"Delta ({p1.label} vs {p0.label}): presence {d_pres:+.1f} pp, "
            f"marginal capture {d_cap:+.6f} XRP (oracle)."
        )
    lines.append("")
    lines.append(
        "Interpretation: presence lift alone is not profit. Validate on live pure-path fills before scale claims."
    )
    return "\n".join(lines)


def run_sacred_economics(
    decisions_path: Path,
    *,
    trades_path: Optional[Path] = None,
    max_decision_lines: Optional[int] = None,
    pure_would_quote: Callable[[str], bool],
    lookahead_cycles: int = 8,
) -> Tuple[BaselineEconomics, MarginalEconomics, str]:
    logs_dir = decisions_path.parent
    trades_file = resolve_trades_path(logs_dir, trades_path)
    if not trades_file:
        raise FileNotFoundError(f"No trades CSV found under {logs_dir}")

    trades_rows = load_trades_rows(trades_file)
    baseline = compute_baseline_economics(trades_rows, trades_path=str(trades_file))
    decision_lines = load_decision_lines(decisions_path, max_decision_lines)
    marginal = compute_marginal_economics(
        decision_lines,
        trades_rows,
        pure_would_quote,
        lookahead_cycles=lookahead_cycles,
        baseline_capture_xrp=baseline.capture_xrp,
    )
    return baseline, marginal, format_economics_report(baseline, marginal)
