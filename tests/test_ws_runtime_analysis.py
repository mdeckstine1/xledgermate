"""Tests for Phase A2 ws_as_demo_runtime analysis."""

import json
from pathlib import Path

from experimental.ws_runtime_analysis import (
    analyze_samples,
    classify_zero_quote_reason,
    collect_samples,
    compact_sample_from_runtime,
    format_runtime_analysis_report,
    run_runtime_analysis,
)


def test_classify_reservation_outside_l1() -> None:
    reason = classify_zero_quote_reason(
        would_quote=False,
        best_bid=1.10,
        best_ask=1.11,
        reservation=1.12,
        book_spread_pct=0.05,
        optimal_spread_pct=0.04,
    )
    assert reason == "reservation_outside_l1"


def test_classify_optimal_wider_than_book() -> None:
    reason = classify_zero_quote_reason(
        would_quote=False,
        best_bid=1.099,
        best_ask=1.101,
        reservation=1.10,
        book_spread_pct=0.05,
        optimal_spread_pct=0.12,
    )
    assert reason == "optimal_spread_wider_than_book"


def test_analyze_samples_flips_and_pressure_buckets() -> None:
    samples = [
        {"would_quote": False, "competitor_pressure": 0.2, "book_spread_pct": 0.08, "as_optimal_spread_pct": 0.10},
        {"would_quote": True, "competitor_pressure": 0.25, "book_spread_pct": 0.09, "as_optimal_spread_pct": 0.08},
        {"would_quote": True, "competitor_pressure": 0.8, "book_spread_pct": 0.07, "as_optimal_spread_pct": 0.07},
        {"would_quote": False, "competitor_pressure": 0.85, "book_spread_pct": 0.06, "as_optimal_spread_pct": 0.09},
    ]
    a = analyze_samples(samples)
    assert a.sample_count == 4
    assert a.would_quote_pct == 50.0
    assert a.flip_count == 2
    assert a.pressure_buckets["low (<0.30)"]["would_quote_pct"] == 50.0
    assert a.corr_pressure_would_quote is not None


def test_compact_sample_from_runtime() -> None:
    runtime = {
        "mid_price": 1.1,
        "best_bid_rlusd_per_xrp": 1.099,
        "best_ask_rlusd_per_xrp": 1.101,
        "book_spread_pct": 0.18,
        "as_optimal_spread_pct": 0.12,
        "as_reservation": 1.1005,
        "market_edge_met": True,
        "competitor_pressure": 0.45,
        "recent_decisions": [{"ts_utc": "2026-06-10T12:00:00+00:00", "message": "x"}],
    }
    s = compact_sample_from_runtime(runtime)
    assert s["would_quote"] is True
    assert s["spread_gap_pct"] == 0.06
    assert s["competitor_pressure"] == 0.45


def test_collect_samples_from_file(tmp_path: Path) -> None:
    payload = {
        "sample_history": [
            {"would_quote": True, "competitor_pressure": 0.1, "book_spread_pct": 0.1, "as_optimal_spread_pct": 0.09},
            {"would_quote": False, "competitor_pressure": 0.9, "book_spread_pct": 0.1, "as_optimal_spread_pct": 0.11},
        ]
    }
    p = tmp_path / "ws_as_demo_runtime.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    samples, notes = collect_samples(primary=p, logs_dir=tmp_path)
    assert len(samples) == 2
    assert "sample_history" in notes[0]

    analysis = run_runtime_analysis(path=p)
    report = format_runtime_analysis_report(analysis, path_label=str(p))
    assert "Phase A2" in report
    assert "would_quote" in report
