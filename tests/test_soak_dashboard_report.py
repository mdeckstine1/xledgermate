"""Tests for soak dashboard report (facts + optional Grok narrative)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from scripts.soak_dashboard_report import (
    build_soak_dashboard_facts,
    build_soak_dashboard_report,
    fetch_grok_soak_narrative,
)


def _write_min_runtime(logs: Path) -> None:
    rt = {
        "version": "2.1.17",
        "ws_as_version": "2.1.17",
        "fills_session": 12,
        "session_spread_capture_xrp": 0.05,
        "portfolio_value_xrp": 100.5,
        "g7_summary": "xrp_heavy 9.2/3.5 × G2 1.15",
        "g2_grade": "B",
        "g2_spread_mult": 1.15,
        "inventory_label": "xrp_heavy",
        "g6_activation_tier": "pilot_watch",
        "dry_run": False,
        "trading_enabled": True,
        "cycle_count": 500,
    }
    (logs / "runtime_state.json").write_text(json.dumps(rt), encoding="utf-8")


def test_facts_missing_runtime(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    text = build_soak_dashboard_facts(logs_dir=logs)
    assert "MISSING logs/runtime_state.json" in text


def test_facts_bundle_with_runtime(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_min_runtime(logs)
    text = build_soak_dashboard_facts(logs_dir=logs)
    assert "SOAK DASHBOARD — facts" in text
    assert "g7_summary" in text
    assert "Discipline note" in text
    assert "G6 gate:" in text


def test_narrative_without_key_shows_help(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_min_runtime(logs)
    text = build_soak_dashboard_report(logs_dir=logs, narrative=True, grok_key="")
    assert "Grok soak narrative" in text
    assert "No Grok API key configured" in text


def test_narrative_grok_disabled(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_min_runtime(logs)
    text = build_soak_dashboard_report(
        logs_dir=logs,
        narrative=True,
        grok_key="secret",
        grok_enabled=False,
    )
    assert "Grok disabled" in text


def test_narrative_with_mock_grok(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_min_runtime(logs)
    with patch(
        "scripts.soak_dashboard_report.fetch_grok_soak_narrative",
        return_value="Soak is stable; watch toxic@30s.",
    ) as mock_fetch:
        text = build_soak_dashboard_report(
            logs_dir=logs,
            narrative=True,
            grok_key="test-key",
        )
    mock_fetch.assert_called_once()
    assert "Soak is stable" in text


def test_fetch_grok_soak_narrative_calls_api() -> None:
    from unittest.mock import MagicMock

    class FakeResp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "Phase: stable."}}]}

    mock_requests = MagicMock()
    mock_requests.post.return_value = FakeResp()
    with patch.dict("sys.modules", {"requests": mock_requests}):
        out = fetch_grok_soak_narrative("FACT BUNDLE HERE", api_key="k", model="grok-3")
    assert out == "Phase: stable."
    mock_requests.post.assert_called_once()
    payload = mock_requests.post.call_args.kwargs["json"]
    assert payload["max_tokens"] == 500
    assert "FACT BUNDLE HERE" in payload["messages"][0]["content"]
