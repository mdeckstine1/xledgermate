"""Tests for Alpha HUD read-only arb monitor routes."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from alpha.hud import arb_monitor
from alpha.hud.server import app

pytest.importorskip("fastapi")


@pytest.fixture
def client():
    return TestClient(app)


def test_arb_state_returns_cached_snapshot(client, monkeypatch):
    snap = {
        "mode": "read_only",
        "updated_utc": "2026-06-22T12:00:00+00:00",
        "dislocation_threshold_bps": 8.0,
        "latest": {
            "clob_mid_rlusd_per_xrp": 2.5,
            "amm_mid_rlusd_per_xrp": 2.49,
            "spread_bps": 4.0,
            "dislocation": False,
            "status": "ok",
        },
        "history": [],
        "summary": {"samples": 1, "dislocation_count": 0, "dislocation_pct": 0.0},
        "note": "test",
    }
    monkeypatch.setattr("alpha.hud.routes_arb.arb_snapshot_cached", lambda: dict(snap))

    r = client.get("/arb/state")
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "read_only"
    assert data["latest"]["spread_bps"] == 4.0


def test_arb_refresh_polls_without_touching_engine(client, monkeypatch):
    calls = []

    def _fake_refresh(**kwargs):
        calls.append(kwargs)
        return {
            "mode": "read_only",
            "updated_utc": "2026-06-22T12:01:00+00:00",
            "dislocation_threshold_bps": 8.0,
            "latest": {"spread_bps": 10.0, "dislocation": True, "status": "ok"},
            "history": [],
            "summary": {},
            "note": "monitor only",
        }

    monkeypatch.setattr("alpha.hud.routes_arb.refresh_arb_snapshot", _fake_refresh)

    r = client.post("/arb/refresh")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["latest"]["dislocation"] is True
    assert len(calls) == 1


def test_arb_snapshot_cached_backfills_from_jsonl(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    path = logs / "clob_amm_spread.jsonl"
    row = {
        "ts_utc": "2026-06-22T11:00:00+00:00",
        "clob_mid_rlusd_per_xrp": 2.0,
        "amm_mid_rlusd_per_xrp": 1.99,
        "spread_bps": 5.0,
        "dislocation": False,
        "status": "ok",
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    monkeypatch.setattr(arb_monitor, "_ARB_CACHE", {"latest": None, "history": []})

    snap = arb_monitor.arb_snapshot_cached(logs_dir=logs)
    assert snap["latest"]["spread_bps"] == 5.0
    assert snap["summary"]["samples"] == 1


def test_read_alpha_mid_from_runtime_state(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "alpha_runtime_state.json").write_text(
        json.dumps({"mid": 2.123456}),
        encoding="utf-8",
    )
    assert arb_monitor._read_alpha_mid(logs) == pytest.approx(2.123456)
