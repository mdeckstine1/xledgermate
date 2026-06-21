"""Tests for QD_FINAL report parser and HUD catalog wiring."""

from __future__ import annotations

import json
from pathlib import Path

from experimental.ws_feed.hud_reports_support import generate_report_text, get_report_spec, list_reports
from scripts.qd_final_report import (
    build_qd_final_report,
    format_qd_final_report,
    parse_qd_final_line,
)


SAMPLE_LINE = (
    "2026-06-21 15:54:12 | INFO | strategy.quote_decision_layers.ops_log | "
    "QD_FINAL | intent=solo_accumulate_on_edge | solo_mode=true | book_mode=solo | "
    "drift_band=heavy_xrp | dev=+18% | bid_allowed=true | ask_allowed=false | "
    "ask_block=edge_gate | ask_cause=edge | bid_edge_viable=true | ask_edge_viable=false | "
    "bid_edge_pct=2.150 | ask_edge_pct=-0.500 | bid_pre_bleed=true | ask_pre_bleed=false | "
    "bid_bleed_override=none | ask_bleed_override=none | bid_bleed_blocked=false | "
    "ask_bleed_blocked=false | bid_cb_ok=true | ask_cb_ok=true | inventory_cb_mode=skipped_solo | "
    "path=ws"
)


def test_parse_qd_final_line() -> None:
    parsed = parse_qd_final_line(SAMPLE_LINE)
    assert parsed["intent"] == "solo_accumulate_on_edge"
    assert parsed["bid_allowed"] == "true"
    assert parsed["ask_allowed"] == "false"
    assert parsed["ask_cause"] == "edge"
    assert parsed["inventory_cb_mode"] == "skipped_solo"
    assert parsed["_ts"] == "2026-06-21 15:54:12"


def test_qd_final_report_from_log_and_runtime(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "xledgermate.log").write_text(SAMPLE_LINE + "\n", encoding="utf-8")
    (logs / "runtime_state.json").write_text(
        json.dumps(
            {
                "cycle_count": 42,
                "updated_utc": "2026-06-21T15:54:12Z",
                "qd_intent": "solo_accumulate_on_edge",
                "qd_book_mode": "solo",
                "solo_mode": True,
                "qd_bid_allowed": True,
                "qd_ask_allowed": False,
                "qd_bid_pause_cause": "",
                "qd_ask_pause_cause": "edge",
                "qd_bid_edge_viable": True,
                "qd_ask_edge_viable": False,
                "qd_inventory_cb_mode": "skipped_solo",
                "zero_quote_reason": "reservation_inside_l1",
            }
        ),
        encoding="utf-8",
    )

    report = build_qd_final_report(logs_dir=logs, limit=10)
    text = format_qd_final_report(report)

    assert report["record_count"] == 1
    assert "solo_accumulate_on_edge" in text
    assert "[BID] allowed: ON" in text
    assert "zero_quote_reason: reservation_inside_l1" in text
    assert report["summary"]["solo_accumulate_bid_on"] == 1


def test_hud_catalog_includes_qd_final_diagnostics() -> None:
    ids = {r["id"] for r in list_reports()}
    assert "qd_final_diagnostics" in ids
    spec = get_report_spec("qd_final_diagnostics")
    assert spec is not None
    assert spec.soak_safe is True


def test_generate_qd_final_diagnostics_report(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "xledgermate.log").write_text(SAMPLE_LINE + "\n", encoding="utf-8")
    text = generate_report_text("qd_final_diagnostics", logs_dir=logs)
    assert "L5 PERMISSION MONITOR" in text
    assert "solo_accumulate_on_edge" in text
