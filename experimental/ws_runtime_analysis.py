"""
Phase A2 + C1 + C2 — analyze live WS + pure A-S runtime exports.

Reads `logs/ws_as_demo_runtime.json` (and optional timestamped backups) for:
- pressure variance and bucketed presence (low / mid / high)
- zero_quote_reason breakdown (all samples, including quoted)
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
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SAMPLE_HISTORY_MAX = 2000
_WQ_RE = re.compile(r"Generated (\d+) quotes", re.I)

# C1 — competitor pressure buckets for presence tracking
PRESSURE_BUCKETS: Dict[str, Tuple[float, float]] = {
    "low (<0.30)": (0.0, 0.30),
    "mid (0.30-0.70)": (0.30, 0.70),
    "high (>0.70)": (0.70, 1.01),
}

# C2 — soak gate defaults (pre-D2); aligned with B3 stale threshold
DEFAULT_STALE_AGE_S = 12.0


@dataclass(frozen=True)
class SoakCriteria:
    """Minimum bar for a 30+ min WS + pure A-S soak before D2 dry-run."""

    min_duration_minutes: float = 30.0
    min_presence_pct: float = 50.0
    max_flip_rate: float = 0.20
    max_ws_age_mean_s: float = 12.0
    max_ws_age_p95_s: float = 20.0
    min_fresh_sample_pct: float = 80.0
    min_samples: int = 15
    stale_age_s: float = DEFAULT_STALE_AGE_S


@dataclass
class SoakEvaluation:
    passed: bool = False
    metrics: Dict[str, Any] = field(default_factory=dict)
    criteria: Dict[str, Any] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "metrics": self.metrics,
            "criteria": self.criteria,
            "failures": self.failures,
        }


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


def _sample_zero_quote_reason(sample: Dict[str, Any]) -> str:
    existing = sample.get("zero_quote_reason")
    if existing:
        return str(existing)
    would_quote = bool(sample.get("would_quote"))
    return classify_zero_quote_reason(
        would_quote=would_quote,
        best_bid=_f(sample.get("best_bid")),
        best_ask=_f(sample.get("best_ask")),
        reservation=_f(sample.get("as_reservation")),
        book_spread_pct=_f(sample.get("book_spread_pct")),
        optimal_spread_pct=_f(sample.get("as_optimal_spread_pct")),
    )


def compute_c1_metrics(samples: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """
    C1 aggregates: presence by pressure bucket + zero_quote_reason breakdown.
    Written to gui_runtime on each sample append and mirrored in RuntimeAnalysis.
    """
    n = len(samples)
    if n == 0:
        return {
            "sample_count": 0,
            "as_presence_pct": 0.0,
            "presence_by_pressure": {},
            "zero_quote_breakdown": {},
        }

    quoted = sum(1 for s in samples if s.get("would_quote"))
    presence_by_pressure: Dict[str, Dict[str, float]] = {}
    for label, (lo, hi) in PRESSURE_BUCKETS.items():
        bucket = [
            s
            for s in samples
            if (p := _f(s.get("competitor_pressure"))) is not None and lo <= p < hi
        ]
        if not bucket:
            continue
        b_wq = [bool(s.get("would_quote")) for s in bucket if s.get("would_quote") is not None]
        presence_by_pressure[label] = {
            "n": float(len(bucket)),
            "would_quote_pct": round(100.0 * sum(b_wq) / len(b_wq), 1) if b_wq else 0.0,
            "mean_pressure": round(
                statistics.mean(_f(s.get("competitor_pressure")) or 0.0 for s in bucket), 4
            ),
        }

    reason_counts: Dict[str, int] = {}
    for s in samples:
        reason = _sample_zero_quote_reason(s)
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    zero_quote_breakdown = {
        reason: {"count": count, "pct": round(100.0 * count / n, 1)}
        for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1])
    }

    return {
        "sample_count": n,
        "as_presence_pct": round(100.0 * quoted / n, 1),
        "presence_by_pressure": presence_by_pressure,
        "zero_quote_breakdown": zero_quote_breakdown,
    }


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
        "zero_quote_reason": runtime.get("zero_quote_reason")
        or classify_zero_quote_reason(
            would_quote=would_quote,
            best_bid=bb,
            best_ask=ba,
            reservation=reservation,
            book_spread_pct=book_spread,
            optimal_spread_pct=optimal,
            pause_bids=pause_bids,
            pause_asks=pause_asks,
        ),
        "inside_l1": runtime.get("inside_l1"),
        "reservation_to_bbo_delta_bps": runtime.get("reservation_to_bbo_delta_bps"),
    }


def append_runtime_sample(runtime: Dict[str, Any], sample: Dict[str, Any]) -> None:
    """Append a compact sample to gui_runtime sample_history (bounded)."""
    history: List[Dict[str, Any]] = list(runtime.get("sample_history") or [])
    if not sample.get("zero_quote_reason"):
        sample = dict(sample)
        sample["zero_quote_reason"] = _sample_zero_quote_reason(sample)
    history.append(sample)
    runtime["sample_history"] = history[-SAMPLE_HISTORY_MAX:]
    c1 = compute_c1_metrics(runtime["sample_history"])
    runtime["sample_count"] = c1["sample_count"]
    runtime["as_presence_pct"] = c1["as_presence_pct"]
    runtime["presence_by_pressure"] = c1["presence_by_pressure"]
    runtime["zero_quote_breakdown"] = c1["zero_quote_breakdown"]
    runtime["soak_evaluation"] = evaluate_soak_gate(runtime["sample_history"]).as_dict()


def _parse_ts_utc(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    try:
        text = str(ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def _percentile(vals: Sequence[float], pct: float) -> float:
    if not vals:
        return 0.0
    ordered = sorted(vals)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * (pct / 100.0)
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (k - lo) * (ordered[hi] - ordered[lo])


def compute_soak_metrics(samples: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """C2 session metrics: duration, presence, flips, WS book-age distribution."""
    n = len(samples)
    if n == 0:
        return {
            "sample_count": 0,
            "session_duration_minutes": 0.0,
            "presence_pct": 0.0,
            "flip_count": 0,
            "flip_rate": 0.0,
            "ws_age_mean_s": None,
            "ws_age_p50_s": None,
            "ws_age_p95_s": None,
            "ws_age_max_s": None,
            "fresh_sample_pct": 0.0,
        }

    timestamps = [_parse_ts_utc(s.get("ts_utc")) for s in samples]
    timestamps = [t for t in timestamps if t is not None]
    duration_min = 0.0
    if len(timestamps) >= 2:
        duration_min = (timestamps[-1] - timestamps[0]).total_seconds() / 60.0

    wq_flags = [bool(s.get("would_quote")) for s in samples if s.get("would_quote") is not None]
    presence_pct = 100.0 * sum(wq_flags) / len(wq_flags) if wq_flags else 0.0

    flip_count = 0
    prev: Optional[bool] = None
    for s in samples:
        wq = s.get("would_quote")
        if wq is None:
            continue
        if prev is not None and wq != prev:
            flip_count += 1
        prev = wq
    transitions = max(sum(1 for s in samples if s.get("would_quote") is not None) - 1, 0)
    flip_rate = flip_count / transitions if transitions else 0.0

    ages = [_f(s.get("ws_book_age_s")) for s in samples]
    ages = [x for x in ages if x is not None]
    fresh_n = sum(1 for x in ages if x < DEFAULT_STALE_AGE_S)
    fresh_pct = 100.0 * fresh_n / len(ages) if ages else 0.0

    return {
        "sample_count": n,
        "session_duration_minutes": round(duration_min, 2),
        "session_start_utc": timestamps[0].isoformat() if timestamps else None,
        "session_end_utc": timestamps[-1].isoformat() if timestamps else None,
        "presence_pct": round(presence_pct, 1),
        "flip_count": flip_count,
        "flip_rate": round(flip_rate, 3),
        "ws_age_mean_s": round(statistics.mean(ages), 2) if ages else None,
        "ws_age_p50_s": round(_percentile(ages, 50), 2) if ages else None,
        "ws_age_p95_s": round(_percentile(ages, 95), 2) if ages else None,
        "ws_age_max_s": round(max(ages), 2) if ages else None,
        "fresh_sample_pct": round(fresh_pct, 1),
    }


def evaluate_soak_gate(
    samples: Sequence[Dict[str, Any]],
    criteria: Optional[SoakCriteria] = None,
) -> SoakEvaluation:
    """C2 pass/fail gate for long-run soak before D2."""
    crit = criteria or SoakCriteria()
    metrics = compute_soak_metrics(samples)
    failures: List[str] = []

    if metrics["sample_count"] < crit.min_samples:
        failures.append(
            f"samples {metrics['sample_count']} < min {crit.min_samples}"
        )
    if metrics["session_duration_minutes"] < crit.min_duration_minutes:
        failures.append(
            f"duration {metrics['session_duration_minutes']:.1f}m < min {crit.min_duration_minutes:.0f}m"
        )
    if metrics["presence_pct"] < crit.min_presence_pct:
        failures.append(
            f"presence {metrics['presence_pct']:.1f}% < min {crit.min_presence_pct:.0f}%"
        )
    if metrics["flip_rate"] > crit.max_flip_rate:
        failures.append(
            f"flip_rate {metrics['flip_rate']:.3f} > max {crit.max_flip_rate:.2f}"
        )
    mean_age = metrics.get("ws_age_mean_s")
    if mean_age is not None and mean_age > crit.max_ws_age_mean_s:
        failures.append(
            f"ws_age mean {mean_age:.2f}s > max {crit.max_ws_age_mean_s:.0f}s"
        )
    p95_age = metrics.get("ws_age_p95_s")
    if p95_age is not None and p95_age > crit.max_ws_age_p95_s:
        failures.append(
            f"ws_age p95 {p95_age:.2f}s > max {crit.max_ws_age_p95_s:.0f}s"
        )
    if metrics["fresh_sample_pct"] < crit.min_fresh_sample_pct:
        failures.append(
            f"fresh samples {metrics['fresh_sample_pct']:.1f}% < min {crit.min_fresh_sample_pct:.0f}%"
        )

    return SoakEvaluation(
        passed=len(failures) == 0,
        metrics=metrics,
        criteria=asdict(crit),
        failures=failures,
    )


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
    zero_quote_breakdown: Dict[str, Dict[str, float]] = field(default_factory=dict)
    pressure: Dict[str, float] = field(default_factory=dict)
    pressure_buckets: Dict[str, Dict[str, float]] = field(default_factory=dict)
    corr_pressure_would_quote: Optional[float] = None
    corr_pressure_book_spread: Optional[float] = None
    corr_comp_spread_book_spread: Optional[float] = None
    ws_age: Dict[str, float] = field(default_factory=dict)
    soak: Optional[SoakEvaluation] = None

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
            "zero_quote_breakdown": self.zero_quote_breakdown,
            "pressure": self.pressure,
            "pressure_buckets": self.pressure_buckets,
            "corr_pressure_would_quote": self.corr_pressure_would_quote,
            "corr_pressure_book_spread": self.corr_pressure_book_spread,
            "corr_comp_spread_book_spread": self.corr_comp_spread_book_spread,
            "ws_age": self.ws_age,
            "soak": self.soak.as_dict() if self.soak else None,
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

    c1 = compute_c1_metrics(samples)
    result.zero_quote_breakdown = c1["zero_quote_breakdown"]
    result.pressure_buckets = c1["presence_by_pressure"]
    for reason, stats in c1["zero_quote_breakdown"].items():
        if reason != "quoted":
            result.zero_quote_reasons[reason] = int(stats["count"])

    pressures = [_f(s.get("competitor_pressure")) for s in samples]
    pressures_clean = [x for x in pressures if x is not None]
    result.pressure = _stats(pressures_clean)

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
    if ages:
        result.ws_age["p50"] = _percentile(ages, 50)
        result.ws_age["p95"] = _percentile(ages, 95)
    result.soak = evaluate_soak_gate(samples)

    return result


def format_runtime_analysis_report(
    analysis: RuntimeAnalysis,
    *,
    path_label: str = "logs/ws_as_demo_runtime.json",
) -> str:
    lines = [
        "=== WS RUNTIME ANALYSIS (Phase A2 + C1 + C2) ===",
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
    if analysis.zero_quote_breakdown:
        lines.append("")
        lines.append("zero_quote_reason breakdown (all samples):")
        for reason, stats in analysis.zero_quote_breakdown.items():
            lines.append(f"  {reason}: {int(stats['count'])} ({stats['pct']:.1f}%)")
    elif analysis.zero_quote_reasons:
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
        lines.append("Presence by pressure bucket (C1):")
        for label, stats in analysis.pressure_buckets.items():
            lines.append(
                f"  {label}: n={int(stats['n'])} presence={stats['would_quote_pct']:.1f}%"
            )
        low = analysis.pressure_buckets.get("low (<0.30)", {}).get("would_quote_pct")
        high = analysis.pressure_buckets.get("high (>0.70)", {}).get("would_quote_pct")
        if low is not None and high is not None:
            lines.append(f"  low vs high presence delta: {low - high:+.1f} pp")

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
                f"mean={analysis.ws_age.get('mean', 0):.2f} "
                f"p50={analysis.ws_age.get('p50', 0):.2f} "
                f"p95={analysis.ws_age.get('p95', 0):.2f} "
                f"max={analysis.ws_age.get('max', 0):.2f}",
            ]
        )

    if analysis.soak:
        s = analysis.soak
        m = s.metrics
        lines.extend(
            [
                "",
                "--- C2 soak gate (pre-D2) ---",
                f"Result: {'PASS' if s.passed else 'FAIL'}",
                f"Duration: {m.get('session_duration_minutes', 0):.1f} min "
                f"({m.get('sample_count', 0)} samples)",
                f"Presence: {m.get('presence_pct', 0):.1f}% | "
                f"Flips: {m.get('flip_count', 0)} (rate {m.get('flip_rate', 0):.3f})",
                f"WS age: mean={m.get('ws_age_mean_s')}s p95={m.get('ws_age_p95_s')}s "
                f"fresh<{DEFAULT_STALE_AGE_S:.0f}s: {m.get('fresh_sample_pct', 0):.1f}% of samples",
            ]
        )
        if s.failures:
            lines.append("Failures:")
            for fail in s.failures:
                lines.append(f"  - {fail}")

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
    parser.add_argument(
        "--soak-gate",
        action="store_true",
        help="Exit 1 if C2 soak criteria not met (for CI / pre-D2 check)",
    )
    args = parser.parse_args()

    path = args.path or Path("logs/ws_as_demo_runtime.json")
    analysis = run_runtime_analysis(path=path, include_backups=args.include_backups)

    if args.as_json:
        print(json.dumps(analysis.as_dict(), indent=2))
    else:
        print(format_runtime_analysis_report(analysis, path_label=str(path)))

    if args.soak_gate and (not analysis.soak or not analysis.soak.passed):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
