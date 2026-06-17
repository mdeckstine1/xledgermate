"""Tests for Grok suggestions report."""

import json
from pathlib import Path

from scripts.grok_suggestions_report import (
    build_grok_suggestions_report,
    format_grok_suggestions_report,
)


def test_grok_suggestions_report(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    intel = logs / "intel_decisions.jsonl"
    intel.write_text(
        json.dumps(
            {
                "kind": "grok_suggestion",
                "address": "rTest123",
                "in_peer_lane": False,
                "outcome_status": "pending",
                "result_excerpt": "Skim harder on wide passive book.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report = build_grok_suggestions_report(logs_dir=logs)
    text = format_grok_suggestions_report(report)
    assert report["total"] == 1
    assert "rTest123" in text
    assert "Skim harder" in text
