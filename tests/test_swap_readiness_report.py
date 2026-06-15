"""Tests for D4 swap readiness report."""

import json
from pathlib import Path

from experimental.swap_readiness_report import (
    WIRING_PARITY_REQUIRED_KEYS,
    SwapReadinessCriteria,
    build_swap_readiness_report,
    check_wiring_parity,
    find_best_soak_pass,
    format_swap_readiness_report,
)


def test_check_wiring_parity_complete() -> None:
    runtime = {k: "x" for k in WIRING_PARITY_REQUIRED_KEYS}
    runtime["quote_intents"] = [{"level": 1, "active": True, "side": "bid"}]
    runtime["dry_run"] = True
    out = check_wiring_parity(runtime)
    assert out["passed"] is True
    assert out["missing_keys"] == []


def test_check_wiring_parity_missing() -> None:
    out = check_wiring_parity({"as_mode": "pure"})
    assert out["passed"] is False
    assert "dry_run_execution" in out["missing_keys"]


def test_find_best_soak_pass_picks_longest(tmp_path: Path) -> None:
    soak_hist = [
        {
            "would_quote": True,
            "ws_book_age_s": 8.0,
            "ts_utc": f"2026-06-12T10:{i // 2:02d}:{(i * 4) % 60:02d}+00:00",
        }
        for i in range(500)
    ]
    soak_hist[0]["ts_utc"] = "2026-06-12T10:00:00+00:00"
    soak_hist[-1]["ts_utc"] = "2026-06-12T10:35:00+00:00"
    (tmp_path / "ws_as_demo_runtime_20260612.json").write_text(
        json.dumps({"sample_history": soak_hist}), encoding="utf-8"
    )
    result, source = find_best_soak_pass(tmp_path)
    assert result is not None
    assert source == "ws_as_demo_runtime_20260612.json"
    assert result["passed"] is True


def test_format_report_includes_gate() -> None:
    from experimental.swap_readiness_report import SwapReadinessReport

    r = SwapReadinessReport(passed=False, failures=["test failure"])
    text = format_swap_readiness_report(r)
    assert "FAIL" in text
    assert "test failure" in text


def test_build_report_gate_fails_without_decisions(tmp_path: Path) -> None:
    report = build_swap_readiness_report(
        decisions_path=tmp_path / "missing.jsonl",
        ws_runtime_path=tmp_path / "missing_ws.json",
        logs_dir=tmp_path,
        criteria=SwapReadinessCriteria(require_soak_pass=False),
        include_economics_ab=False,
    )
    assert report.passed is False
    assert any("decisions" in f for f in report.failures)
