"""Tests for Alpha HUD operator API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alpha.hud.server import app

pytest.importorskip("fastapi")


@pytest.fixture
def client(tmp_path, monkeypatch):
    overrides = tmp_path / "alpha_overrides.json"
    commands = tmp_path / "alpha_commands.json"
    controls = tmp_path / "alpha_controls.json"
    kill = tmp_path / "kill_switch.json"

    monkeypatch.setattr("alpha.hud.routes_operator._OVERRIDES", overrides)
    monkeypatch.setattr("alpha.hud.routes_operator._COMMANDS", commands)
    monkeypatch.setattr("alpha.hud.routes_operator._KILL", kill)
    monkeypatch.setattr("alpha.hud.server._CONTROLS", controls)

    return TestClient(app)


def test_get_operator_config(client):
    r = client.get("/operator/config")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "config_effective" in data
    assert "slider_defaults" in data


def test_patch_operator_config(client):
    r = client.patch("/operator/config", json={"overrides": {"alpha_risk_per_trade_pct": 0.8}})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["operator_overrides"]["alpha_risk_per_trade_pct"] == 0.8


def test_patch_alpha_ta_enabled(client):
    r = client.patch("/operator/config", json={"overrides": {"alpha_ta_enabled": True}})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["operator_overrides"]["alpha_ta_enabled"] is True
    assert data["config_effective"]["alpha_ta_enabled"] is True
    r = client.patch("/operator/config", json={"overrides": {"alpha_ta_enabled": False}})
    assert r.status_code == 200
    assert r.json()["config_effective"]["alpha_ta_enabled"] is False


def test_patch_hud_tunables(client):
    r = client.patch(
        "/operator/config",
        json={
            "overrides": {
                "inventory_target_xrp_ratio": 0.78,
                "alpha_ta_weight": 0.6,
                "alpha_reentry_tp_min_ta_score": 2.0,
                "alpha_reentry_sl_min_ta_score": 3.0,
                "alpha_ta_min_buy_score": 1.8,
                "alpha_ta_rsi_enabled": False,
            }
        },
    )
    assert r.status_code == 200
    eff = r.json()["config_effective"]
    assert eff["inventory_target_xrp_ratio"] == 0.78
    assert eff["inventory_target_xrp_pct"] == 78.0
    assert eff["alpha_ta_weight"] == 0.6
    assert eff["alpha_reentry_tp_min_ta_score"] == 2.0
    assert eff["alpha_ta_min_buy_score"] == 1.8
    assert eff["alpha_ta_rsi_enabled"] is False


def test_patch_rejects_invalid_override(client):
    r = client.patch("/operator/config", json={"overrides": {"alpha_risk_per_trade_pct": 0}})
    assert r.status_code == 400


def test_dry_run_requires_confirm_live(client):
    r = client.post("/operator/dry-run", json={"dry_run": False, "confirm": "WRONG"})
    assert r.status_code == 400
    r = client.post("/operator/dry-run", json={"dry_run": False, "confirm": "ENABLE_LIVE"})
    assert r.status_code == 200
    assert r.json()["dry_run"] is False


def test_dry_run_enable_requires_confirm(client):
    r = client.post("/operator/dry-run", json={"dry_run": True, "confirm": "ENABLE_LIVE"})
    assert r.status_code == 400
    r = client.post("/operator/dry-run", json={"dry_run": True, "confirm": "ENABLE_DRY_RUN"})
    assert r.status_code == 200


def test_cancel_all_requires_confirm(client, mock_command_runner):
    r = client.post("/controls/cancel-all", json={"confirm": "NOPE"})
    assert r.status_code == 400
    r = client.post("/controls/cancel-all", json={"confirm": "CANCEL_ALL"})
    assert r.status_code == 200
    assert r.json()["queued"] == "cancel_all"


def test_kill_and_clear_kill(client):
    r = client.post("/controls/kill", json={"reason": "test"})
    assert r.status_code == 200
    assert r.json()["kill_switch_active"] is True
    r = client.post("/controls/clear-kill")
    assert r.status_code == 200
    assert r.json()["kill_switch_active"] is False


def test_config_reload_queues(client):
    r = client.post("/operator/config/reload")
    assert r.status_code == 200
    assert r.json()["queued"] == "config_reload"


def test_bracket_edge_cleanup_preset(client):
    r = client.post("/operator/bracket-edge-cleanup")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["config_effective"]["alpha_max_pending_buys"] == 1
    assert data["config_effective"]["take_profit_pct"] == 0.025


def test_long_build_preset(client):
    r = client.post("/operator/long-build")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["config_effective"]["alpha_operator_phase"] == "scale"
    assert data["config_effective"]["inventory_target_xrp_ratio"] == 0.80
    assert data["walkaway_comparison"]["different_operator_keys"]["alpha_operator_phase"]["long_build"] == "scale"


def test_operator_presets_catalog(client):
    r = client.get("/operator/presets")
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["presets"]]
    assert "walkaway" in ids
    assert "stack_growth" in ids
    assert "long_build" in ids
    assert "bracket_edge_cleanup" in ids


def test_stack_growth_preset_route(client):
    r = client.post("/operator/stack-growth")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["config_effective"]["inventory_target_xrp_ratio"] == 0.88
    assert data["config_effective"]["alpha_strength_deviation"] == 0.11
    assert data["config_effective"]["alpha_ta_min_sell_score"] == 4.0


@pytest.fixture
def mock_command_runner(monkeypatch):
    monkeypatch.setattr(
        "alpha.operator.command_runner.process_queued_commands_sync",
        lambda publish_hud=True: {"ok": True, "processed": 1, "message": "commands_processed"},
    )


def test_bracket_adjust_queues(client, mock_command_runner):
    r = client.post(
        "/brackets/abc12345/adjust",
        json={"leg": "tp", "price": 2.5},
    )
    assert r.status_code == 200
    assert r.json()["queued"] == "bracket_adjust"


def test_bracket_adjust_entry_queues(client, mock_command_runner):
    r = client.post(
        "/brackets/abc12345/adjust",
        json={"leg": "entry", "price": 1.05},
    )
    assert r.status_code == 200
    assert r.json()["leg"] == "entry"


def test_bracket_cancel_queues(client, mock_command_runner):
    r = client.post("/brackets/abc12345/cancel")
    assert r.status_code == 200
    assert r.json()["queued"] == "bracket_cancel"
    assert r.json()["message"] == "commands_processed"


def test_offer_cancel_queues(client, mock_command_runner):
    r = client.post("/offers/12345/cancel")
    assert r.status_code == 200
    assert r.json()["queued"] == "offer_cancel"


def test_offer_adjust_queues(client, mock_command_runner):
    r = client.post("/offers/12345/adjust", json={"price": 1.08})
    assert r.status_code == 200
    assert r.json()["queued"] == "offer_adjust"


def test_pause_resume_controls(client):
    r = client.post("/controls/pause")
    assert r.status_code == 200
    assert r.json()["paused"] is True
    r = client.post("/controls/resume")
    assert r.status_code == 200
    assert r.json()["paused"] is False


def test_adjust_bracket_leg_dry_run_no_ledger_cancel(tmp_path):
    from alpha.dry_run import DryRunGuard
    from alpha.orders.manager import OrderManager
    from alpha.orders.types import BracketLeg, BracketLegRole, BracketLifecycleState, BracketMode, BracketRecord
    from tests.test_alpha_order_manager import _BracketFakeLedger, _bracket_config

    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config()
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=True, network="mainnet"),
            cfg,
            state_dir=tmp_path,
        )
        record = BracketRecord(
            bracket_id="test-bracket-uuid-1234",
            state=BracketLifecycleState.BRACKET_ACTIVE,
            mode=BracketMode.BRACKET,
            buy_sequence=1,
            entry_price_rlusd_per_xrp=2.0,
            target_size_xrp=10.0,
            filled_xrp=10.0,
            tp_leg=BracketLeg(role=BracketLegRole.TAKE_PROFIT, sequence=2001, price_rlusd_per_xrp=2.1, size_xrp=10.0, remaining_xrp=10.0),
            sl_leg=BracketLeg(role=BracketLegRole.STOP_LOSS, sequence=2002, price_rlusd_per_xrp=1.9, size_xrp=10.0, remaining_xrp=10.0),
        )
        mgr.store.add(record)
        ledger._offers[2001] = {"sequence": 2001, "side": "ask", "price": 2.1, "size_xrp": 10.0}
        ledger._offers[2002] = {"sequence": 2002, "side": "ask", "price": 1.9, "size_xrp": 10.0}
        ok = await mgr.adjust_bracket_leg("test-bracket-uuid-1234", "tp", 2.15)
        assert ok is True
        assert ledger.cancelled == []
        assert record.tp_leg.price_rlusd_per_xrp == 2.15

    import asyncio
    asyncio.run(_run())
