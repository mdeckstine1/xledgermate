"""Tests for Phase A2 ws_as_demo_runtime analysis."""

import json
from pathlib import Path

from experimental.ws_runtime_analysis import (
    SoakCriteria,
    analyze_samples,
    append_runtime_sample,
    classify_zero_quote_reason,
    collect_samples,
    compact_sample_from_runtime,
    compute_c1_metrics,
    compute_soak_metrics,
    evaluate_soak_gate,
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


def test_compute_c1_metrics_presence_and_breakdown() -> None:
    samples = [
        {
            "would_quote": True,
            "competitor_pressure": 0.2,
            "zero_quote_reason": "quoted",
        },
        {
            "would_quote": False,
            "competitor_pressure": 0.25,
            "zero_quote_reason": "optimal_spread_wider_than_book",
        },
        {
            "would_quote": True,
            "competitor_pressure": 0.8,
            "zero_quote_reason": "quoted",
        },
        {
            "would_quote": False,
            "competitor_pressure": 0.85,
            "zero_quote_reason": "reservation_outside_l1",
        },
    ]
    c1 = compute_c1_metrics(samples)
    assert c1["as_presence_pct"] == 50.0
    assert c1["presence_by_pressure"]["low (<0.30)"]["would_quote_pct"] == 50.0
    assert c1["presence_by_pressure"]["high (>0.70)"]["would_quote_pct"] == 50.0
    assert c1["zero_quote_breakdown"]["quoted"]["count"] == 2
    assert c1["zero_quote_breakdown"]["quoted"]["pct"] == 50.0
    assert c1["zero_quote_breakdown"]["reservation_outside_l1"]["count"] == 1


def test_append_runtime_sample_writes_c1_fields() -> None:
    runtime: dict = {"sample_history": []}
    append_runtime_sample(
        runtime,
        {"would_quote": True, "competitor_pressure": 0.1, "zero_quote_reason": "quoted"},
    )
    append_runtime_sample(
        runtime,
        {
            "would_quote": False,
            "competitor_pressure": 0.9,
            "zero_quote_reason": "optimal_spread_wider_than_book",
        },
    )
    assert runtime["sample_count"] == 2
    assert runtime["as_presence_pct"] == 50.0
    assert "presence_by_pressure" in runtime
    assert "zero_quote_breakdown" in runtime
    assert runtime["zero_quote_breakdown"]["quoted"]["count"] == 1


def test_analyze_samples_zero_quote_breakdown() -> None:
    samples = [
        {"would_quote": True, "competitor_pressure": 0.2, "zero_quote_reason": "quoted"},
        {"would_quote": False, "competitor_pressure": 0.2, "zero_quote_reason": "other"},
    ]
    a = analyze_samples(samples)
    assert a.zero_quote_breakdown["quoted"]["count"] == 1
    assert a.zero_quote_reasons["other"] == 1


def test_stale_cross_zero_quote_bucket() -> None:
    from experimental.ws_runtime_analysis import STALE_CROSS_ZERO_REASON, compute_c1_metrics

    samples = [
        {
            "would_quote": False,
            "reservation_crossed_after_ws_sample": True,
            "competitor_pressure": 0.4,
        },
        {"would_quote": True, "zero_quote_reason": "quoted", "competitor_pressure": 0.4},
    ]
    c1 = compute_c1_metrics(samples)
    assert c1["zero_quote_breakdown"][STALE_CROSS_ZERO_REASON]["count"] == 1


def test_soak_gate_fails_short_session() -> None:
    samples = [
        {
            "ts_utc": "2026-06-11T17:00:00+00:00",
            "would_quote": True,
            "ws_book_age_s": 5.0,
        },
        {
            "ts_utc": "2026-06-11T17:05:00+00:00",
            "would_quote": True,
            "ws_book_age_s": 6.0,
        },
    ]
    ev = evaluate_soak_gate(samples)
    assert ev.passed is False
    assert any("duration" in f for f in ev.failures)


def test_soak_gate_passes_30_min_session() -> None:
    base = "2026-06-11T17:00:00+00:00"
    samples = []
    for i in range(20):
        samples.append(
            {
                "ts_utc": f"2026-06-11T17:{i:02d}:00+00:00",
                "would_quote": True,
                "ws_book_age_s": 4.0 + (i % 3),
            }
        )
    samples[0]["ts_utc"] = base
    samples[-1]["ts_utc"] = "2026-06-11T17:35:00+00:00"
    crit = SoakCriteria(min_samples=15, min_duration_minutes=30.0)
    ev = evaluate_soak_gate(samples, crit)
    assert ev.passed is True
    metrics = compute_soak_metrics(samples)
    assert metrics["session_duration_minutes"] >= 30.0


def test_analyze_samples_includes_soak() -> None:
    samples = [
        {"ts_utc": "2026-06-11T17:00:00+00:00", "would_quote": True, "ws_book_age_s": 3.0},
        {"ts_utc": "2026-06-11T17:01:00+00:00", "would_quote": False, "ws_book_age_s": 8.0},
    ]
    a = analyze_samples(samples)
    assert a.soak is not None
    assert a.soak.metrics["flip_count"] == 1


def test_append_runtime_sample_writes_soak_evaluation() -> None:
    runtime: dict = {"sample_history": []}
    append_runtime_sample(
        runtime,
        {
            "ts_utc": "2026-06-11T17:00:00+00:00",
            "would_quote": True,
            "ws_book_age_s": 2.0,
            "zero_quote_reason": "quoted",
        },
    )
    assert "soak_evaluation" in runtime
    assert runtime["soak_evaluation"]["passed"] is False


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
    assert "C1" in report
    assert "zero_quote_reason breakdown" in report
    assert "would_quote" in report
