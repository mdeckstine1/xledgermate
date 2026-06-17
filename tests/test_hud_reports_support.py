"""Tests for HUD Reports catalog."""

from pathlib import Path

from experimental.ws_feed.hud_reports_support import (
    generate_report_text,
    get_report_spec,
    list_reports,
    wrap_report_html,
)


def test_list_reports_has_soak_safe_entries() -> None:
    reports = list_reports()
    assert len(reports) >= 5
    ids = {r["id"] for r in reports}
    assert "hourly_telegram" in ids
    assert "fill_quote_age" in ids
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
