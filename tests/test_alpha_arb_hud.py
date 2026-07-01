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
        json.dumps({"mid": 2.123456, "book": {"spread_pct": 0.0987}}),
        encoding="utf-8",
    )
    assert arb_monitor._read_alpha_book_context(logs)["mid"] == pytest.approx(2.123456)
    assert arb_monitor._read_alpha_book_context(logs)["spread_pct"] == pytest.approx(0.0987)


def test_arb_snapshot_includes_fill_simulation(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    depth_row = {
        "ts_utc": "2026-06-22T11:00:00+00:00",
        "clob_mid_rlusd_per_xrp": 1.12,
        "amm_mid_rlusd_per_xrp": 1.10,
        "spread_bps": 18.0,
        "clob_spread_pct": 0.1,
        "amm_fee_bps": 5.0,
        "dislocation": True,
        "status": "ok",
        "amm_xrp_reserve": 50_000.0,
        "amm_rlusd_reserve": 55_000.0,
        "book_depth": {
            "best_bid": 1.12,
            "best_ask": 1.13,
            "mid": 1.125,
            "bids": [{"p": 1.12, "x": 500.0}],
            "asks": [{"p": 1.13, "x": 500.0}],
        },
    }
    path = logs / "clob_amm_spread.jsonl"
    path.write_text(json.dumps(depth_row) + "\n", encoding="utf-8")

    monkeypatch.setattr(arb_monitor, "_ARB_CACHE", {"latest": None, "history": []})

    snap = arb_monitor.arb_snapshot_cached(logs_dir=logs)
    assert "fill_simulation" in snap
    assert snap["fill_simulation"]["live"]["available"] is True
    assert len(snap["fill_simulation"]["live"]["rows"]) == 3


def test_arb_soak_report_route(client, monkeypatch):
    monkeypatch.setattr(
        "alpha.hud.arb_monitor.arb_soak_report_text",
        lambda **_: "=== soak ===\nnet positive",
    )
    r = client.get("/arb/report.txt")
    assert r.status_code == 200
    assert "net positive" in r.text
