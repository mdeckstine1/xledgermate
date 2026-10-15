"""DEX swap preview math and HUD confirm gate. No live ledger."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from alpha.hud.server import app
from utils.dex_swap import preview_swap

pytest.importorskip("fastapi")


def _book():
    return {
        "bids": [
            {"price": 1.319, "size": 50.0},
            {"price": 1.317, "size": 80.0},
            {"price": 1.300, "size": 500.0},
        ],
        "asks": [
            {"price": 1.321, "size": 40.0},
            {"price": 1.323, "size": 80.0},
            {"price": 1.360, "size": 500.0},
        ],
    }


def _preview(**kwargs):
    base = dict(
        book=_book(),
        xrp_balance=200.0,
        rlusd_balance=200.0,
        xrp_reserve=12.0,
        open_offer_count=0,
        has_rlusd_trust=True,
    )
    base.update(kwargs)
    return preview_swap(**base)


def test_sell_walks_bids_inside_cap():
    preview = _preview(direction="xrp_to_rlusd", amount=90.0)
    assert preview["ok"] is True
    assert preview["output_asset"] == "RLUSD"
    assert preview["output_amount"] == pytest.approx(50 * 1.319 + 40 * 1.317)
    assert preview["average_price"] == pytest.approx(preview["output_amount"] / 90.0)
    assert preview["limit_price"] < preview["mid"]
    assert preview["slippage_bps"] < 30


def test_sell_refuses_when_book_is_outside_slippage():
    book = _book()
    book["bids"] = [{"price": 1.300, "size": 500.0}]
    preview = _preview(direction="xrp_to_rlusd", amount=10.0, book=book)
    assert preview["ok"] is False
    assert "inside" in preview["message"]


def test_sell_refuses_reserve_breach():
    preview = _preview(direction="xrp_to_rlusd", amount=30.0, xrp_balance=37.8, xrp_reserve=12.0)
    assert preview["ok"] is False
    assert "reserve" in preview["message"]


def test_sell_refuses_over_max_and_open_offers():
    too_big = _preview(direction="xrp_to_rlusd", amount=200.1)
    assert too_big["ok"] is False
    assert "200" in too_big["message"]
    blocked = _preview(direction="xrp_to_rlusd", amount=5.0, open_offer_count=1)
    assert blocked["ok"] is False
    assert "open offers" in blocked["message"]


def test_buy_walks_asks_inside_cap():
    preview = _preview(direction="rlusd_to_xrp", amount=100.0)
    assert preview["ok"] is True
    assert preview["output_asset"] == "XRP"
    assert preview["output_amount"] > 0
    assert preview["average_price"] >= 1.321
    assert preview["limit_price"] > preview["mid"]


def test_buy_refuses_thin_rlusd_balance():
    preview = _preview(direction="rlusd_to_xrp", amount=50.0, rlusd_balance=10.0)
    assert preview["ok"] is False
    assert "Insufficient RLUSD" in preview["message"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    commands = tmp_path / "alpha_commands.json"
    controls = tmp_path / "alpha_controls.json"
    kill = tmp_path / "kill_switch.json"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_yaml = config_dir / "config.yaml"
    config_yaml.write_text("testnet: true\n", encoding="utf-8")
    monkeypatch.setattr("alpha.hud.routes_operator._COMMANDS", commands)
    monkeypatch.setattr("alpha.hud.routes_operator._KILL", kill)
    monkeypatch.setattr("alpha.hud.routes_config._COMMANDS", commands)
    monkeypatch.setattr("alpha.hud.server._CONTROLS", controls)
    monkeypatch.setattr("config.settings.CONFIG_FILE", config_yaml)
    monkeypatch.chdir(tmp_path)
    return TestClient(app)


def test_swap_requires_swap_confirm(client):
    response = client.post(
        "/operator/swap",
        json={"direction": "xrp_to_rlusd", "amount": 5},
    )
    assert response.status_code == 400
    assert "SWAP" in response.json()["message"]


def test_swap_execute_uses_operator_helper(client, monkeypatch):
    captured = {}

    async def fake_execute(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "partial": False,
            "tx_hash": "HASHSWAP",
            "message": "Swap submitted.",
        }

    monkeypatch.setattr("utils.dex_swap.execute_swap_for_operator", fake_execute)
    response = client.post(
        "/operator/swap",
        json={
            "direction": "xrp_to_rlusd",
            "amount": 5,
            "max_slippage_bps": 15,
            "confirm_text": "SWAP",
            "confirm_engine_running": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["tx_hash"] == "HASHSWAP"
    assert captured["direction"] == "xrp_to_rlusd"
    assert captured["amount"] == 5
    assert captured["max_slippage_bps"] == 15


def test_place_ioc_swap_sets_immediate_or_cancel_flag():
    from xrpl.models.transactions import OfferCreateFlag

    from connectors.xrpl_connector import XRPLConnector, XRPLNetworkConfig

    captured = {}
    connector = XRPLConnector(
        account_address="rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe",
        secret=None,
        rlusd_issuer="rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De",
        rlusd_currency="RLUSD",
        network=XRPLNetworkConfig(json_rpc_url="https://s1.ripple.com:51234"),
    )
    connector.load_wallet = lambda: object()

    async def fake_submit(tx, wallet):
        captured["tx"] = tx

        class _Response:
            result = {
                "hash": "ABC",
                "meta": {"TransactionResult": "tesSUCCESS", "AffectedNodes": []},
            }

        return _Response()

    connector._sign_and_submit = fake_submit
    tx_hash, seq, resting = asyncio.run(
        connector.place_ioc_swap(direction="xrp_to_rlusd", xrp_amount=5.0, rlusd_amount=6.58)
    )
    assert tx_hash == "ABC"
    assert resting is False
    assert seq is None
    assert int(captured["tx"].flags) & int(OfferCreateFlag.TF_IMMEDIATE_OR_CANCEL)
