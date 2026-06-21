"""Tests for HUD Reports catalog."""

import json
from pathlib import Path

from experimental.ws_feed.hud_reports_support import (
    generate_report_text,
    get_report_spec,
    list_reports,
    wrap_report_html,
)


def test_list_reports_has_soak_safe_entries() -> None:
    reports = list_reports()
    assert len(reports) >= 11
    ids = {r["id"] for r in reports}
    assert "hourly_telegram" in ids
    assert "fill_quote_age" in ids
    assert "grok_suggestions" in ids
    assert "clob_amm_monitor" in ids
    assert "soak_dashboard" in ids
    assert "soak_dashboard_narrative" in ids
    assert "qd_final_diagnostics" in ids
    assert all(r["soak_safe"] for r in reports)


def test_unknown_report_raises() -> None:
    try:
        generate_report_text("not_a_real_report_id")
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_reservation_snapshot_empty_logs(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    text = generate_report_text("reservation_snapshot", logs_dir=logs)
    assert "runtime_state.json" in text


def test_soak_dashboard_facts_only(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    rt = {
        "version": "2.1.17",
        "fills_session": 5,
        "g7_summary": "balanced",
        "inventory_label": "balanced",
    }
    (logs / "runtime_state.json").write_text(json.dumps(rt), encoding="utf-8")
    text = generate_report_text("soak_dashboard", logs_dir=logs)
    assert "SOAK DASHBOARD — facts" in text
    assert "Grok soak narrative" not in text


def test_soak_dashboard_narrative_no_key(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "runtime_state.json").write_text('{"fills_session": 1}', encoding="utf-8")
    text = generate_report_text(
        "soak_dashboard_narrative",
        logs_dir=logs,
        grok_config={"intel_ai_key": "", "grok_enabled": True},
    )
    assert "Grok soak narrative" in text
    assert "No Grok API key configured" in text


def test_wrap_report_html_includes_id() -> None:
    spec = get_report_spec("hourly_telegram")
    assert spec is not None
    page = wrap_report_html(
        report_id="hourly_telegram",
        title=spec.title,
        subtitle=spec.subtitle,
        body_text="line one",
        spec=spec,
    )
    assert "hourly_telegram" in page
    assert "Soak-safe" in page
    assert "line one" in page
