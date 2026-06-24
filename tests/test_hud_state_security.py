"""HUD state redaction for browser-facing payloads."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from experimental.ws_feed import real_time_as_hud


def test_public_hud_state_redacts_intel_key() -> None:
    state = {
        "mid": 1.23,
        "intel_ai_provider": "grok",
        "intel_ai_key": "xai-secret-key",
        "intel_ai_model": "grok-3",
        "intel_ai_enabled": True,
    }

    public = real_time_as_hud._public_hud_state(state)

    assert "intel_ai_key" not in public
    assert public["intel_ai_key_set"] is True
    assert public["intel_ai_key_len"] == len("xai-secret-key")
    assert state["intel_ai_key"] == "xai-secret-key"


def test_state_endpoint_never_returns_intel_key() -> None:
    assert real_time_as_hud.app is not None
    original_state = dict(real_time_as_hud._current_state)
    try:
        real_time_as_hud._current_state.clear()
        real_time_as_hud._current_state.update(
            {
                "mid": 1.23,
                "intel_ai_provider": "grok",
                "intel_ai_key": "xai-secret-key",
                "intel_ai_model": "grok-3",
                "intel_ai_enabled": True,
            }
        )

        client = TestClient(real_time_as_hud.app)
        body = client.get("/state").json()

        assert "intel_ai_key" not in body
        assert body["intel_ai_key_set"] is True
        assert body["intel_ai_key_len"] == len("xai-secret-key")
        assert real_time_as_hud._current_state["intel_ai_key"] == "xai-secret-key"
    finally:
        real_time_as_hud._current_state.clear()
        real_time_as_hud._current_state.update(original_state)
