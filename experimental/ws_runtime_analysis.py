"""
Phase A2 — analyze live WS + pure A-S runtime exports.

Reads `logs/ws_as_demo_runtime.json` (and optional timestamped backups) for:
- pressure variance and bucketed presence
- book spread vs A-S optimal spread (why 0 quotes)
- would_quote flip rate
- competitor pressure vs quoting / spread correlation

Grok/xAI fields may appear in the export for operator context; they do not affect
analysis logic (advisory only until post-swap).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SAMPLE_HISTORY_MAX = 2000
_WQ_RE = re.compile(r"Generated (\d+) quotes", re.I)


def classify_zero_quote_reason(
    *,
    would_quote: bool,
    best_bid: Optional[float],
    best_ask: Optional[float],
    reservation: Optional[float],
    book_spread_pct: Optional[float],
    optimal_spread_pct: Optional[float],
    pause_bids: bool = False,
    pause_asks: bool = False,
) -> str:
    if would_quote:
        return "quoted"
    if pause_bids and pause_asks:
        return "paused_both_sides"
    if pause_bids or pause_asks:
        return "paused_one_side"
    if (
        reservation is not None
        and best_bid is not None
        and best_ask is not None
        and best_bid > 0
        and best_ask > 0
        and not (best_bid < reservation < best_ask)
    ):
        return "reservation_outside_l1"
    if (
        book_spread_pct is not None
        and optimal_spread_pct is not None
        and optimal_spread_pct > book_spread_pct * 1.02
    ):
        return "optimal_spread_wider_than_book"
    return "other"


def compact_sample_from_runtime(runtime: Dict[str, Any]) -> Dict[str, Any]:
    """Extract one analysis row from a full gui_runtime snapshot."""
    bb = _f(runtime.get("best_bid_rlusd_per_xrp"))
    ba = _f(runtime.get("best_ask_rlusd_per_xrp"))
    mid = _f(runtime.get("mid_price"))
    book_spread = _f(runtime.get("book_spread_pct"))
    optimal = _f(runtime.get("as_optimal_spread_pct"))
    reservation = _f(runtime.get("as_reservation"))
    would_quote = bool(runtime.get("market_edge_met"))
    pause_bids = bool(runtime.get("pause_bids"))
    pause_asks = bool(runtime.get("pause_asks"))
    ts = None
    recent = runtime.get("recent_decisions") or []
    if recent:
        ts = recent[-1].get("ts_utc")
    return {
        "ts_utc": ts,
        "mid": mid,
        "best_bid": bb,
        "best_ask": ba,
        "book_spread_pct": book_spread,
        "as_optimal_spread_pct": optimal,
        "spread_gap_pct": (book_spread - optimal) if book_spread is not None and optimal is not None else None,
        "as_reservation": reservation,
        "would_quote": would_quote,
        "competitor_pressure": _f(runtime.get("competitor_pressure")),
        "competitor_observed_spread_pct": _f(runtime.get("competitor_observed_spread_pct")),
        "volatility_pct": _f(runtime.get("volatility_pct")),
        "ws_book_age_s": _f(runtime.get("ws_book_age_s")),
        "inventory_label": runtime.get("inventory_label"),
        "zero_quote_reason": classify_zero_quote_reason(
            would_quote=would_quote,
            best_bid=bb,
            best_ask=ba,
            reservation=reservation,
            book_spread_pct=book_spread,
            optimal_spread_pct=optimal,
            pause_bids=pause_bids,
            pause_asks=pause_asks,
        ),
    }


def append_runtime_sample(runtime: Dict[str, Any], sample: Dict[str, Any]) -> None:
    """Append a compact sample to gui_runtime sample_history (bounded)."""
    history: List[Dict[str, Any]] = list(runtime.get("sample_history") or [])
    history.append(sample)
    runtime["sample_history"] = history[-SAMPLE_HISTORY_MAX:]
    quoted = sum(1 for s in runtime["sample_history"] if s.get("would_quote"))
    runtime["as_presence_pct"] = round(100.0 * quoted / len(runtime["sample_history"]), 1)


def _f(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _would_quote_from_message(msg: str) -> Optional[bool]:
    m = _WQ_RE.search(msg or "")
    if not m:
        return None
    return int(m.group(1)) > 0


def samples_from_recent_decisions(runtime: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fallback: infer would_quote flips from recent_decisions messages only."""
    out: List[Dict[str, Any]] = []
    for ev in runtime.get("recent_decisions") or []:
        wq = _would_quote_from_message(ev.get("message", ""))
        if wq is None:
            continue
        out.append(
            {
                "ts_utc": ev.get("ts_utc"),
                "would_quote": wq,
                "book_spread_pct": None,
                "as_optimal_spread_pct": None,
                "competitor_pressure": None,
                "zero_quote_reason": "quoted" if wq else "unknown",
            }
        )
    return out


def load_runtime_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def collect_samples(
    *,
    primary: Optional[Path] = None,
    include_backups: bool = False,
    logs_dir: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Build ordered sample list from sample_history, backup snapshots, or recent_decisions.
    Returns (samples, source_notes).
    """
    logs = logs_dir or Path("logs")
    primary = primary or logs / "ws_as_demo_runtime.json"
    sources: List[str] = []
    samples: List[Dict[str, Any]] = []

    paths: List[Path] = []
    if primary.exists():
        paths.append(primary)
    if include_backups and logs.exists():
        backups = sorted(
            p for p in logs.glob("ws_as_demo_runtime_*.json") if p != primary
        )
        paths = backups + paths

    for p in paths:
        try:
            data = load_runtime_json(p)
        except (OSError, json.JSONDecodeError):
            continue
        hist = data.get("sample_history") or []
        if hist:
            samples.extend(hist)
            sources.append(f"{p.name}: sample_history ({len(hist)} rows)")
        else:
            samples.append(compact_sample_from_runtime(data))
            sources.append(f"{p.name}: snapshot")

    if not samples and primary.exists():
        data = load_runtime_json(primary)
        samples = samples_from_recent_decisions(data)
        if samples:
            sources.append(f"{primary.name}: recent_decisions ({len(samples)} rows)")

    return samples, sources


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def _stats(vals: Sequence[float]) -> Dict[str, float]:
    if not vals:
        return {}
    return {
        "n": float(len(vals)),
        "mean": statistics.mean(vals),
        "min": min(vals),
        "max": max(vals),
        "stdev": statistics.pstdev(vals) if len(vals) > 1 else 0.0,
    }


@dataclass
class RuntimeAnalysis:
    sample_count: int = 0
    source_notes: List[str] = field(default_factory=list)
    would_quote_pct: float = 0.0
    flip_count: int = 0
    flip_up: int = 0
    flip_down: int = 0
    book_spread: Dict[str, float] = field(default_factory=dict)
    optimal_spread: Dict[str, float] = field(default_factory=dict)
    spread_gap: Dict[str, float] = field(default_factory=dict)
    zero_quote_reasons: Dict[str, int] = field(default_factory=dict)
    pressure: Dict[str, float] = field(default_factory=dict)
    pressure_buckets: Dict[str, Dict[str, float]] = field(default_factory=dict)
    corr_pressure_would_quote: Optional[float] = None
    corr_pressure_book_spread: Optional[float] = None
    corr_comp_spread_book_spread: Optional[float] = None
    ws_age: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "source_notes": self.source_notes,
            "would_quote_pct": round(self.would_quote_pct, 1),
            "flip_count": self.flip_count,
            "flip_up": self.flip_up,
            "flip_down": self.flip_down,
            "book_spread": self.book_spread,
            "optimal_spread": self.optimal_spread,
            "spread_gap": self.spread_gap,
            "zero_quote_reasons": self.zero_quote_reasons,
            "pressure": self.pressure,
            "pressure_buckets": self.pressure_buckets,
            "corr_pressure_would_quote": self.corr_pressure_would_quote,
            "corr_pressure_book_spread": self.corr_pressure_book_spread,
            "corr_comp_spread_book_spread": self.corr_comp_spread_book_spread,
            "ws_age": self.ws_age,
        }


def analyze_samples(samples: Sequence[Dict[str, Any]]) -> RuntimeAnalysis:
    result = RuntimeAnalysis(sample_count=len(samples))
    if not samples:
        return result

    wq_flags = [bool(s.get("would_quote")) for s in samples if s.get("would_quote") is not None]
    if wq_flags:
        result.would_quote_pct = 100.0 * sum(wq_flags) / len(wq_flags)

    prev: Optional[bool] = None
    for s in samples:
        wq = s.get("would_quote")
        if wq is None:
            continue
        if prev is not None and wq != prev:
            result.flip_count += 1
            if wq:
                result.flip_up += 1
            else:
                result.flip_down += 1
        prev = wq

    book = [_f(s.get("book_spread_pct")) for s in samples]
    book = [x for x in book if x is not None]
    opt = [_f(s.get("as_optimal_spread_pct")) for s in samples]
    opt = [x for x in opt if x is not None]
    gap = [_f(s.get("spread_gap_pct")) for s in samples]
    gap = [x for x in gap if x is not None]
    result.book_spread = _stats(book)
    result.optimal_spread = _stats(opt)
    result.spread_gap = _stats(gap)

    for s in samples:
        if s.get("would_quote"):
            continue
        reason = s.get("zero_quote_reason") or "unknown"
        result.zero_quote_reasons[reason] = result.zero_quote_reasons.get(reason, 0) + 1

    pressures = [_f(s.get("competitor_pressure")) for s in samples]
    pressures_clean = [x for x in pressures if x is not None]
    result.pressure = _stats(pressures_clean)

    buckets = {
        "low (<0.30)": (0.0, 0.30),
        "mid (0.30-0.70)": (0.30, 0.70),
        "high (>0.70)": (0.70, 1.01),
    }
    for label, (lo, hi) in buckets.items():
        bucket_samples = [
            s
            for s in samples
            if (p := _f(s.get("competitor_pressure"))) is not None and lo <= p < hi
        ]
        if not bucket_samples:
            continue
        b_wq = [bool(s.get("would_quote")) for s in bucket_samples if s.get("would_quote") is not None]
        result.pressure_buckets[label] = {
            "n": float(len(bucket_samples)),
            "would_quote_pct": 100.0 * sum(b_wq) / len(b_wq) if b_wq else 0.0,
            "mean_pressure": statistics.mean(_f(s.get("competitor_pressure")) or 0.0 for s in bucket_samples),
        }

    # Correlations (numeric samples only)
    paired_p_wq: List[Tuple[float, float]] = []
    paired_p_book: List[Tuple[float, float]] = []
    paired_comp_book: List[Tuple[float, float]] = []
    for s in samples:
        p = _f(s.get("competitor_pressure"))
        b = _f(s.get("book_spread_pct"))
        csp = _f(s.get("competitor_observed_spread_pct"))
        wq = s.get("would_quote")
        if p is not None and wq is not None:
            paired_p_wq.append((p, 1.0 if wq else 0.0))
        if p is not None and b is not None:
            paired_p_book.append((p, b))
        if csp is not None and b is not None:
            paired_comp_book.append((csp, b))

    if paired_p_wq:
        result.corr_pressure_would_quote = _pearson([a for a, _ in paired_p_wq], [b for _, b in paired_p_wq])
    if paired_p_book:
        result.corr_pressure_book_spread = _pearson([a for a, _ in paired_p_book], [b for _, b in paired_p_book])
    if paired_comp_book:
        result.corr_comp_spread_book_spread = _pearson(
            [a for a, _ in paired_comp_book], [b for _, b in paired_comp_book]
        )

    ages = [_f(s.get("ws_book_age_s")) for s in samples]
    ages = [x for x in ages if x is not None]
    result.ws_age = _stats(ages)

    return result


def format_runtime_analysis_report(
    analysis: RuntimeAnalysis,
    *,
    path_label: str = "logs/ws_as_demo_runtime.json",
) -> str:
    lines = [
        "=== WS RUNTIME ANALYSIS (Phase A2) ===",
        "",
        f"Primary artifact: {path_label}",
        f"Samples analyzed: {analysis.sample_count}",
    ]
    if analysis.source_notes:
        lines.append("Sources:")
        for note in analysis.source_notes:
            lines.append(f"  - {note}")
    lines.extend(
        [
            "",
            "--- would_quote ---",
            f"Presence: {analysis.would_quote_pct:.1f}%",
            f"Flips (0<->1): {analysis.flip_count} (up={analysis.flip_up}, down={analysis.flip_down})",
            "",
            "--- spread vs optimal (book L1 vs A-S optimal_spread_pct) ---",
        ]
    )
    if analysis.book_spread:
        lines.append(
            f"Book spread %: mean={analysis.book_spread.get('mean', 0):.4f} "
            f"min={analysis.book_spread.get('min', 0):.4f} max={analysis.book_spread.get('max', 0):.4f}"
        )
    if analysis.optimal_spread:
        lines.append(
            f"Optimal spread %: mean={analysis.optimal_spread.get('mean', 0):.4f} "
            f"min={analysis.optimal_spread.get('min', 0):.4f} max={analysis.optimal_spread.get('max', 0):.4f}"
        )
    if analysis.spread_gap:
        lines.append(
            f"Gap (book - optimal) %: mean={analysis.spread_gap.get('mean', 0):+.4f} "
            f"(negative => optimal wider than book)"
        )
    if analysis.zero_quote_reasons:
        lines.append("")
        lines.append("Zero-quote reasons (non-quoted samples):")
        for reason, count in sorted(analysis.zero_quote_reasons.items(), key=lambda x: -x[1]):
            lines.append(f"  {reason}: {count}")

    lines.extend(["", "--- competitor pressure ---"])
    if analysis.pressure:
        lines.append(
            f"Pressure: mean={analysis.pressure.get('mean', 0):.3f} "
            f"stdev={analysis.pressure.get('stdev', 0):.3f} "
            f"min={analysis.pressure.get('min', 0):.3f} max={analysis.pressure.get('max', 0):.3f}"
        )
    else:
        lines.append("No competitor_pressure in samples (run live tester with CompetitorIntelProvider).")

    if analysis.pressure_buckets:
        lines.append("Presence by pressure bucket:")
        for label, stats in analysis.pressure_buckets.items():
            lines.append(
                f"  {label}: n={int(stats['n'])} presence={stats['would_quote_pct']:.1f}%"
            )

    lines.extend(["", "--- correlations (Pearson) ---"])
    lines.append(
        f"pressure vs would_quote: {_fmt_corr(analysis.corr_pressure_would_quote)}"
    )
    lines.append(
        f"pressure vs book_spread: {_fmt_corr(analysis.corr_pressure_book_spread)}"
    )
    lines.append(
        f"competitor_observed_spread vs book_spread: {_fmt_corr(analysis.corr_comp_spread_book_spread)}"
    )

    if analysis.ws_age:
        lines.extend(
            [
                "",
                "--- WS book age (seconds) ---",
                f"mean={analysis.ws_age.get('mean', 0):.2f} max={analysis.ws_age.get('max', 0):.2f}",
            ]
        )

    lines.extend(
        [
            "",
            "Note: Grok/xAI is advisory only - not used in this analysis.",
            "Run live tester with --serve-hud to populate sample_history; use --include-backups for prior sessions.",
        ]
    )
    return "\n".join(lines)


def _fmt_corr(v: Optional[float]) -> str:
    if v is None:
        return "n/a (insufficient paired samples)"
    return f"{v:+.3f}"


def run_runtime_analysis(
    *,
    path: Optional[Path] = None,
    include_backups: bool = False,
    logs_dir: Optional[Path] = None,
) -> RuntimeAnalysis:
    samples, sources = collect_samples(
        primary=path,
        include_backups=include_backups,
        logs_dir=logs_dir,
    )
    analysis = analyze_samples(samples)
    analysis.source_notes = sources
    return analysis


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze logs/ws_as_demo_runtime.json (Phase A2: pressure, spread, flips, competitor correlation)"
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Runtime JSON path (default: logs/ws_as_demo_runtime.json)",
    )
    parser.add_argument(
        "--include-backups",
        action="store_true",
        help="Also load ws_as_demo_runtime_*.json backups from logs/",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit machine-readable JSON")
    args = parser.parse_args()

    path = args.path or Path("logs/ws_as_demo_runtime.json")
    analysis = run_runtime_analysis(path=path, include_backups=args.include_backups)

    if args.as_json:
        print(json.dumps(analysis.as_dict(), indent=2))
    else:
        print(format_runtime_analysis_report(analysis, path_label=str(path)))


if __name__ == "__main__":
    main()
