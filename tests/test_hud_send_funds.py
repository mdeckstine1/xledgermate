"""HUD /send_funds validation (no live ledger)."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from experimental.ws_feed import real_time_as_hud


@pytest.fixture
def hud_client(monkeypatch):
    assert real_time_as_hud.app is not None
    monkeypatch.setattr(
        "gui.engine_control.is_engine_running",
        lambda: True,
    )

    class _Cfg:
        bot_account_address = "rBot123456789012345678901234"
        bot_secret_key = "sEdTEST"

    monkeypatch.setattr("config.settings.BotConfig.load", lambda: _Cfg())
    return TestClient(real_time_as_hud.app)


def test_send_funds_requires_send_confirm_text(hud_client: TestClient) -> None:
    r = hud_client.post(
        "/send_funds",
        json={
            "destination": "rDest123456789012345678901234",
            "amount": 1.0,
            "asset": "XRP",
            "confirm_text": "NOPE",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "SEND" in body["message"]


def test_send_funds_blocks_when_engine_running_without_confirm(hud_client: TestClient) -> None:
    r = hud_client.post(
        "/send_funds",
        json={
            "destination": "rDest123456789012345678901234",
            "amount": 1.0,
            "asset": "XRP",
            "confirm_text": "SEND",
            "confirm_engine_running": False,
        },
    )
    body = r.json()
    assert body["ok"] is False
    assert body.get("engine_running") is True
