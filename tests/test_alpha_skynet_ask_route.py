"""Integration tests for SKYNET HUD routes."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alpha.hud.server import app

pytest.importorskip("fastapi")


@pytest.fixture
def skynet_client(tmp_path, monkeypatch):
    runtime = tmp_path / "alpha_runtime_state.json"
    overrides = tmp_path / "alpha_overrides.json"
    commands = tmp_path / "alpha_commands.json"
    controls = tmp_path / "alpha_controls.json"

    state = {
        "network": "mainnet",
        "dry_run": False,
        "mid": 1.14,
        "inventory": {"deviation": 0.02, "label": "balanced", "xrp_ratio": 0.6},
        "decision": {"action": "hold", "reason": "balanced dev=+0.02"},
        "accumulation_regime": {"phase": "watching", "armed": False, "headline": "WATCHING"},
        "reload_regime": {"phase": "watching", "blocks_accumulation": True},
        "opportunity_watch": {"state": "watching"},
        "brackets": {"records": []},
        "risk": {"trading_allowed": True},
        "recent_activity": [],
    }
    runtime.write_text(json.dumps(state), encoding="utf-8")

    monkeypatch.setattr("alpha.hud.routes_skynet._RUNTIME", runtime)
    monkeypatch.setattr("alpha.hud.routes_skynet._OVERRIDES", overrides)
    monkeypatch.setattr("alpha.hud.routes_skynet._COMMANDS", commands)
    monkeypatch.setattr("alpha.hud.server._CONTROLS", controls)

    return TestClient(app)


def test_skynet_status_context_ready(skynet_client: TestClient):
    r = skynet_client.get("/operator/skynet/status")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data.get("context_ready") is True


def test_skynet_analysis_prompt_endpoint(skynet_client: TestClient):
    r = skynet_client.get("/operator/skynet/analysis-prompt")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "Regime preset fit" in data["prompt"]
    assert "Walk-away" in data["prompt"]
    assert "Long build" in data["prompt"]


def test_skynet_ask_with_accumulation_context(skynet_client: TestClient):
    parsed = {
        "reasoning": "Tape is chop.",
        "summary": "Hold.",
        "suggested_changes": [],
        "warnings": [],
    }
    with patch("utils.env_secrets.resolve_grok_key", return_value="test-key"):
        with patch(
            "alpha.hud.routes_skynet.skynet_mod.call_skynet_advisor",
            return_value=(json.dumps(parsed), parsed),
        ):
            r = skynet_client.post("/operator/skynet/ask", json={"prompt": "Neutral analysis"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data.get("display")


def test_skynet_ask_passes_history_for_follow_up(skynet_client: TestClient):
    parsed = {
        "reasoning": "Still heavy; trim toward target.",
        "summary": "Trim.",
        "suggested_changes": [],
        "warnings": [],
    }
    captured = {}

    def _fake_advisor(**kwargs):
        captured.update(kwargs)
        return json.dumps(parsed), parsed

    history = [
        {"user": "Why are we holding?", "assistant": "Waiting on powder."},
        {"user": "And now?", "assistant": "Powder is up."},
    ]
    with patch("utils.env_secrets.resolve_grok_key", return_value="test-key"):
        with patch(
            "alpha.hud.routes_skynet.skynet_mod.call_skynet_advisor",
            side_effect=_fake_advisor,
        ):
            r = skynet_client.post(
                "/operator/skynet/ask",
                json={"prompt": "Should we trim?", "history": history},
            )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data.get("follow_up") is True
    assert data.get("history_turns_used") == 2
    assert captured.get("history") == history


def test_normalize_skynet_history_sanitizes():
    from alpha.hud.skynet import normalize_skynet_history

    raw = [
        {"user": "a", "assistant": "b"},
        {"prompt": "only prompt"},
        {"user": "c", "assistant": "d"},
        "junk",
    ]
    turns = normalize_skynet_history(raw, max_turns=6)
    assert turns == [
        {"user": "a", "assistant": "b"},
        {"user": "c", "assistant": "d"},
    ]
