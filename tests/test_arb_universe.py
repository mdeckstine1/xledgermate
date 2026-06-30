"""Tests for XRPL arb universe monitor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alpha.hud.server import app
from experimental.arb.arb_universe import refresh_arb_universe, tail_universe_records

pytest.importorskip("fastapi")


@pytest.fixture
def client():
    return TestClient(app)


def test_refresh_arb_universe_writes_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "arb_universe.jsonl"

    def fake_amm(**_kwargs):
        return {"mid": 1.04, "trading_fee_bps": 5.0}

    def fake_book(**_kwargs):
        return {"mid": 1.041, "spread_pct": 0.1}

    def fake_cross(**_kwargs):
        return {"mid": 1.0001}

    with (
        patch("experimental.arb.arb_universe.fetch_amm_info_sync", side_effect=fake_amm),
        patch("experimental.arb.arb_universe.fetch_token_xrp_book_mid_sync", side_effect=fake_book),
        patch("experimental.arb.arb_universe.fetch_stable_cross_book_mid_sync", side_effect=fake_cross),
    ):
        snap = refresh_arb_universe(
            rpc_url="http://localhost",
            rlusd_currency="RLUSD",
            rlusd_issuer="rTEST",
            rlusd_clob_mid=1.039,
            rlusd_spread_pct=0.08,
            path=path,
        )

    assert snap["net_positive_count"] >= 0
    assert len(snap["pairs"]) == 4
    ids = {p["id"] for p in snap["pairs"]}
    assert ids == {"rlusd_xrp", "usdc_xrp", "usd_xrp", "rlusd_usdc_basis"}
    rows = tail_universe_records(limit=5, path=path)
    assert len(rows) == 1


def test_arb_state_includes_universe(client, monkeypatch):
    fake = {
        "mode": "read_only",
        "latest": None,
        "history": [],
        "summary": {},
        "universe": {
            "pairs": [{"id": "usdc_xrp", "label": "USDC/XRP", "net_positive": True, "net_edge_bps": 2.0}],
            "net_positive_count": 1,
            "best_net": 2.0,
        },
    }
    monkeypatch.setattr("alpha.hud.routes_arb.arb_snapshot_cached", lambda: fake)
    r = client.get("/arb/state")
    assert r.status_code == 200
    data = r.json()
    assert data["universe"]["net_positive_count"] == 1
    assert data["universe"]["pairs"][0]["id"] == "usdc_xrp"
