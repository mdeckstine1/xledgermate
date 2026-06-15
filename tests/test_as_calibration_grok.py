"""Tests for Grok advisory A-S calibration (Phase A3)."""

import json
from pathlib import Path

from experimental.as_calibration_grok import (
    build_calibration_brief,
    build_calibration_prompt,
    format_calibration_report,
    parse_calibration_response,
    run_calibration_session,
    sacred_presence_snapshot,
    validation_commands,
)


def test_parse_calibration_response() -> None:
    data = {
        "market_regime": "tight",
        "competitor_read": "One-sided bidder on ask.",
        "primary_blocker": "optimal_spread_wider_than_book",
        "suggested_gamma": 0.28,
        "suggested_kappa": 4.0,
        "suggested_volatility_pct_hint": 0.4,
        "pressure_interpretation": "Mid pressure — neutral.",
        "implementation_notes": ["kappa not in spread yet"],
        "hypothesis": "Lower gamma may help reservation sit inside L1.",
        "confidence": 0.72,
        "what_to_measure_next": "would_quote_pct over 300s",
        "rationale": "Book is tight; competitors inside 0.10%.",
    }
    rec = parse_calibration_response(data)
    assert rec.suggested_gamma == 0.28
    assert rec.market_regime == "tight"
    assert len(rec.implementation_notes) == 1
    cmds = validation_commands(rec, seconds=300)
    assert "--gamma 0.28" in cmds[0]
    assert "grokster.py" in cmds[2]


def test_build_calibration_brief_from_fixture(tmp_path: Path) -> None:
    runtime = {
        "mid_price": 1.1,
        "best_bid_rlusd_per_xrp": 1.099,
        "best_ask_rlusd_per_xrp": 1.101,
        "book_spread_pct": 0.18,
        "as_optimal_spread_pct": 0.22,
        "as_reservation": 1.1005,
        "market_edge_met": False,
        "as_presence_pct": 12.5,
        "competitor_pressure": 0.45,
        "competitor_observed_spread_pct": 0.15,
        "sample_history": [
            {"would_quote": False, "book_spread_pct": 0.18, "as_optimal_spread_pct": 0.22, "competitor_pressure": 0.45},
            {"would_quote": True, "book_spread_pct": 0.20, "as_optimal_spread_pct": 0.18, "competitor_pressure": 0.3},
        ],
        "top_competitors": [{"account": "rABC...", "account_full": "rABCDEF", "last_spread": 0.12, "activity": 5}],
    }
    p = tmp_path / "ws_as_demo_runtime.json"
    p.write_text(json.dumps(runtime), encoding="utf-8")

    decisions = tmp_path / "decisions.jsonl"
    decisions.write_text(
        '{"cycle": 1, "events": [{"message": "Generated 0 quotes market_edge_met=false Book L1 spread 0.10%"}]}\n'
        '{"cycle": 2, "events": [{"message": "Generated 2 quotes Book L1 spread 0.12% (bid 1.09 ask 1.11)"}]}\n',
        encoding="utf-8",
    )

    brief = build_calibration_brief(
        runtime_path=p,
        gamma=0.35,
        kappa=3.5,
        decisions_path=decisions,
        sacred_window=0,
    )
    assert brief["live_snapshot"]["book_spread_pct"] == 0.18
    assert brief["a2_analysis"]["sample_count"] == 2
    assert "implementation_truth" in brief
    prompt = build_calibration_prompt(brief)
    assert "ADVISORY ONLY" in prompt
    assert "reservation" in prompt


def test_dry_run_session(tmp_path: Path) -> None:
    p = tmp_path / "ws_as_demo_runtime.json"
    p.write_text(json.dumps({"book_spread_pct": 0.1, "sample_history": []}), encoding="utf-8")
    rec, brief = run_calibration_session(runtime_path=p, dry_run=True)
    report = format_calibration_report(rec, brief=brief, dry_run=True)
    assert "DRY RUN" in report
    assert "validation_commands" not in report.lower() or "python -m" in report
