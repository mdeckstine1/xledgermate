"""Tests for Alpha HUD account config and send routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alpha.hud.account_config import (
    account_config_snapshot,
    apply_account_config_updates,
    read_recent_transfers,
)
from alpha.hud.server import app

pytest.importorskip("fastapi")


@pytest.fixture
def client(tmp_path, monkeypatch):
    overrides = tmp_path / "alpha_overrides.json"
    commands = tmp_path / "alpha_commands.json"
    controls = tmp_path / "alpha_controls.json"
    kill = tmp_path / "kill_switch.json"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_yaml = config_dir / "config.yaml"
    config_yaml.write_text("testnet: true\n", encoding="utf-8")
    transfers = tmp_path / "logs"
    transfers.mkdir()
    (transfers / "transfers.csv").write_text(
        "timestamp_utc,network,asset,amount,destination,tx_hash\n"
        "2026-06-23T12:00:00+00:00,mainnet,XRP,1.5,rDest123,ABC\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("alpha.hud.routes_operator._OVERRIDES", overrides)
    monkeypatch.setattr("alpha.hud.routes_operator._COMMANDS", commands)
    monkeypatch.setattr("alpha.hud.routes_operator._KILL", kill)
    monkeypatch.setattr("alpha.hud.routes_config._COMMANDS", commands)
    monkeypatch.setattr("alpha.hud.server._CONTROLS", controls)
    monkeypatch.setattr("config.settings.CONFIG_FILE", config_yaml)
    monkeypatch.chdir(tmp_path)

    return TestClient(app)


def test_account_config_snapshot_masks_secrets():
    from config.settings import BotConfig

    cfg = BotConfig(
        bot_account_address="rTest123456789012345678901234",
        bot_secret_key="sEd123456789012345678901234567890",
        telegram_token="123456:ABC-DEF",
    )
    snap = account_config_snapshot(cfg)
    assert snap["has_bot_secret"] is True
    assert "sE" in snap["bot_secret_masked"]
    assert snap["has_telegram_token"] is True


def test_apply_account_config_updates_address(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_yaml = config_dir / "config.yaml"
    config_yaml.write_text("testnet: true\n", encoding="utf-8")
    monkeypatch.setattr("config.settings.CONFIG_FILE", config_yaml)
    monkeypatch.chdir(tmp_path)

    snap, errors = apply_account_config_updates(
        {"bot_account_address": "rNewBot123456789012345678901234", "xrp_reserve": 10.0}
    )
    assert not errors
    assert snap["bot_account_address"] == "rNewBot123456789012345678901234"
    assert snap["xrp_reserve"] == 10.0


def test_read_recent_transfers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "transfers.csv").write_text(
        "timestamp_utc,network,asset,amount,destination,tx_hash\n"
        "2026-06-23T12:00:00+00:00,mainnet,XRP,2.0,rDest,HASH1\n",
        encoding="utf-8",
    )
    rows = read_recent_transfers()
    assert len(rows) == 1
    assert rows[0]["asset"] == "XRP"


def test_get_account_config(client):
    r = client.get("/operator/account-config")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "account_config" in r.json()


def test_get_transfers(client):
    r = client.get("/operator/transfers")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert isinstance(data["transfers"], list)


def test_send_funds_requires_send_confirm(client):
    r = client.post(
        "/operator/send-funds",
        json={"destination": "rDest123456789012345678901234", "amount": 1.0, "asset": "XRP"},
    )
    assert r.status_code == 400
    assert "SEND" in r.json()["message"]
