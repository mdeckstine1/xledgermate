"""Tests for Alpha PRO defensive circuit breaker."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone

import pytest

from alpha.operator.runtime import OperatorRuntimeStore
from alpha.pro.circuit_breaker import DefensiveCircuit, defensive_status_snapshot
from config.settings import BotConfig


def _write_sl_csv(path, count: int, *, now: datetime) -> None:
    fields = [
        "timestamp_utc",
        "taxable",
        "side",
        "xrp_amount",
        "profit_xrp_equiv",
        "price_rlusd_per_xrp",
        "notes",
    ]
    ts = (now - timedelta(hours=1)).isoformat()
    with path.open("w", encoding="utf-8", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=fields)
        w.writeheader()
        for _ in range(count):
            w.writerow(
                {
                    "timestamp_utc": ts,
                    "taxable": "Y",
                    "side": "SELL",
                    "xrp_amount": "5",
                    "profit_xrp_equiv": "-0.04",
                    "price_rlusd_per_xrp": "1.02",
                    "notes": "stop-loss",
                }
            )


def test_defensive_circuit_trips_on_sl_cluster(tmp_path, monkeypatch):
    now = datetime.now(tz=timezone.utc)
    _write_sl_csv(tmp_path / "trades_2026-06.csv", 10, now=now)
    overrides = tmp_path / "alpha_overrides.json"
    commands = tmp_path / "alpha_commands.json"
    circuit_path = tmp_path / "alpha_defensive_circuit.json"
    store = OperatorRuntimeStore(overrides_path=overrides, commands_path=commands)
    store.save_overrides({"alpha_max_pending_buys": 4, "alpha_risk_per_trade_pct": 5.0})

    cfg = BotConfig(
        alpha_defensive_circuit_enabled=True,
        alpha_defensive_sl_exit_threshold=8,
        alpha_defensive_window_hours=14,
        dry_run=False,
    )
    cb = DefensiveCircuit(store=store, state_path=circuit_path)
    result = cb.tick(cfg, logs_dir=tmp_path)

    assert result["event"] == "activated"
    saved = store.load_overrides()
    assert saved["alpha_operator_market_regime"] == "bear"
    assert saved["alpha_max_pending_buys"] == 1
    assert saved["alpha_risk_per_trade_pct"] == 2.5
    state = json.loads(circuit_path.read_text(encoding="utf-8"))
    assert state["active"] is True


def test_defensive_circuit_manual_release(tmp_path):
    now = datetime.now(tz=timezone.utc)
    _write_sl_csv(tmp_path / "trades_2026-06.csv", 10, now=now)
    overrides = tmp_path / "alpha_overrides.json"
    commands = tmp_path / "alpha_commands.json"
    circuit_path = tmp_path / "alpha_defensive_circuit.json"
    store = OperatorRuntimeStore(overrides_path=overrides, commands_path=commands)
    store.save_overrides({"alpha_max_pending_buys": 4})

    cfg = BotConfig(alpha_defensive_circuit_enabled=True, dry_run=False)
    cb = DefensiveCircuit(store=store, state_path=circuit_path)
    cb.tick(cfg, logs_dir=tmp_path)
    release = cb.release_manual()
    assert release["event"] == "released"
    assert store.load_overrides().get("alpha_max_pending_buys") == 4
    assert json.loads(circuit_path.read_text(encoding="utf-8"))["active"] is False


def test_defensive_status_snapshot(tmp_path):
    snap = defensive_status_snapshot(logs_dir=tmp_path, config=BotConfig())
    assert "replay" in snap
    assert "thresholds" in snap
    assert snap["enabled"] is True


@pytest.fixture
def pro_client(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from alpha.hud import routes_pro
    from alpha.hud.server import app

    overrides = tmp_path / "alpha_overrides.json"
    commands = tmp_path / "alpha_commands.json"
    circuit = tmp_path / "alpha_defensive_circuit.json"
    monkeypatch.setattr(routes_pro, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(routes_pro, "_OVERRIDES", overrides)
    monkeypatch.setattr(routes_pro, "_COMMANDS", commands)
    monkeypatch.setattr(routes_pro, "_CIRCUIT", circuit)
    return TestClient(app)


def test_pro_routes_status(pro_client):
    r = pro_client.get("/operator/pro/status")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "treasury" in data
    assert data["treasury"]["status"] == "placeholder"
