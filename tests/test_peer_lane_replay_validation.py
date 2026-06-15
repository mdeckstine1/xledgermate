"""Tests for G5 peer-lane replay validation."""

from experimental.ws_feed.peer_lane_replay_validation import (
    G5Criteria,
    accumulate_rows,
    build_g5_report,
    classify_peer_lane_row,
)


def test_classify_covered_peer_scrape() -> None:
    assert classify_peer_lane_row({"kind": "peer_scrape", "peer_lane_count": 2}) == "eligible_covered"


def test_classify_neutral_empty_lane() -> None:
    assert classify_peer_lane_row({"peer_lane_count": 0, "peer_lane_empty": True}) == "eligible_neutral"


def test_classify_legacy_sacred_row() -> None:
    assert classify_peer_lane_row({"cycle": 1, "would_quote": True}) == "legacy"


def test_accumulate_counts() -> None:
    rows = [
        {"peer_lane_count": 2, "peer_pressure_score": 0.4},
        {"peer_lane_count": 0, "peer_lane_empty": True},
        {"cycle": 9},
    ]
    counts = accumulate_rows(rows)
    assert counts.peer_lane_eligible == 2
    assert counts.peer_covered == 1
    assert counts.neutral_fallback == 1
    assert counts.legacy_no_peer_fields == 1
    assert counts.peer_coverage_pct == 50.0
    assert counts.neutral_fallback_pct == 50.0


def test_build_g5_report_passes_with_intel(tmp_path) -> None:
    intel = tmp_path / "intel.jsonl"
    intel.write_text(
        "\n".join(
            [
                '{"kind":"peer_scrape","peer_lane_count":2,"peer_pressure_score":0.3}',
                '{"kind":"peer_scrape","peer_lane_count":1,"peer_pressure_score":0.5}',
                '{"kind":"cycle","g4_peer_lane_count":0,"g4_grade":"empty_lane"}',
                '{"kind":"cycle","g4_peer_lane_count":3,"g4_grade":"neutral"}',
                '{"kind":"peer_scrape","peer_lane_count":0,"peer_lane_empty":true}',
                '{"kind":"peer_scrape","peer_lane_count":2}',
                '{"kind":"cycle","g4_peer_lane_count":1}',
                '{"kind":"peer_scrape","peer_lane_count":1}',
            ]
        ),
        encoding="utf-8",
    )
    report = build_g5_report(
        intel_path=intel,
        ws_runtime_path=tmp_path / "missing.json",
        sacred_decisions_path=tmp_path / "missing.jsonl",
        criteria=G5Criteria(min_ws_intel_rows=5, min_peer_coverage_pct=40.0, max_neutral_fallback_pct=60.0),
        strict=True,
    )
    assert report.passed is True
    assert report.intel_log["gate_counts"]["peer_lane_eligible"] >= 5
