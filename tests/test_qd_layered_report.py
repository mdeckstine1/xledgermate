"""Tests for layered QD operator report."""

from __future__ import annotations

import json
from pathlib import Path

from experimental.ws_feed.hud_reports_support import generate_report_text, get_report_spec, list_reports
from scripts.qd_layered_report import build_qd_layered_report, format_qd_layered_report


def test_hud_catalog_has_layered_qd_report() -> None:
    ids = {r["id"] for r in list_reports()}
    assert "qd_layered_decision" in ids
    spec = get_report_spec("qd_layered_decision")
    assert spec is not None
    assert spec.category == "Quote Decision"


def test_qd_layered_report_runtime_sections(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "runtime_state.json").write_text(
        json.dumps(
            {
                "ws_as_version": "2.3.1",
                "cycle_count": 10,
                "updated_utc": "2026-06-21T16:00:00Z",
                "qd_intent": "solo_accumulate_on_edge",
                "qd_book_mode": "solo",
                "solo_mode": True,
                "qd_drift_band": "heavy_xrp",
                "posture_reason": "confirmed_empty",
                "qd_intent_reason": "solo book + viable buy edge (drift ignored)",
                "qd_bid_allowed": True,
                "qd_ask_allowed": False,
                "qd_bid_edge_viable": True,
                "qd_ask_edge_viable": True,
                "qd_bid_implied_bps": 1.29,
                "qd_ask_implied_bps": 1.29,
                "qd_bid_pause_cause": "",
                "qd_ask_pause_cause": "intent",
                "qd_inventory_cb_mode": "skipped_solo",
                "qd_would_quote": True,
                "zero_quote_reason": "quoted",
            }
        ),
        encoding="utf-8",
    )
    (logs / "xledgermate.log").write_text("", encoding="utf-8")

    text = format_qd_layered_report(build_qd_layered_report(logs_dir=logs))
    assert "Layer 1 · Posture" in text
    assert "Layer 2 · Intent" in text
    assert "Layer 3 · Edge" in text
    assert "Layer 4 · Bleed" in text
    assert "Layer 5 · Final permissions" in text
    assert "solo_accumulate_on_edge" in text
    assert "skipped_solo" in text
    assert "solo_edge_mult: 0.65" in text


def test_generate_qd_layered_via_hud_support(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "runtime_state.json").write_text('{"qd_intent":"patient_solo"}', encoding="utf-8")
    text = generate_report_text("qd_layered_decision", logs_dir=logs)
    assert "Layered Quote Decision" in text
