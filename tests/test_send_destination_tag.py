"""Destination tag / memo tag parsing and Payment construction."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from connectors.xrpl_connector import XRPLConnector
from utils.send_funds import parse_destination_tag, parse_memo_text

_BOT = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"
_DEST = "rPT1Sjq2YGrBMTttX4GZHjKu9ddFzN6uqv"


def test_parse_destination_tag_empty() -> None:
    assert parse_destination_tag(None) is None
    assert parse_destination_tag("") is None
    assert parse_destination_tag("   ") is None


def test_parse_destination_tag_zero_is_valid() -> None:
    assert parse_destination_tag(0) == 0
    assert parse_destination_tag("0") == 0


def test_parse_destination_tag_numeric_and_commas() -> None:
    assert parse_destination_tag(424242) == 424242
    assert parse_destination_tag("424242") == 424242
    assert parse_destination_tag("1,234,567") == 1234567
    assert parse_destination_tag(" 99 001 ") == 99001


def test_parse_destination_tag_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="whole number"):
        parse_destination_tag("abc")
    with pytest.raises(ValueError, match="whole number"):
        parse_destination_tag(-1)
    with pytest.raises(ValueError, match="whole number"):
        parse_destination_tag(2**32)
    with pytest.raises(ValueError, match="whole number"):
        parse_destination_tag(True)
    with pytest.raises(ValueError, match="whole number"):
        parse_destination_tag("12.5")


def test_parse_memo_text() -> None:
    assert parse_memo_text(None) is None
    assert parse_memo_text("  ") is None
    assert parse_memo_text(" invoice 9 ") == "invoice 9"
    with pytest.raises(ValueError, match="too long"):
        parse_memo_text("x" * 1025)


def test_send_payment_attaches_destination_tag_and_memo() -> None:
    conn = XRPLConnector.__new__(XRPLConnector)
    conn.account_address = _BOT
    captured: dict = {}

    async def fake_submit(tx, wallet):
        captured["tx"] = tx
        return SimpleNamespace(result={"hash": "ABC123", "meta": {"TransactionResult": "tesSUCCESS"}})

    async def fake_balance():
        return 500.0

    async def fake_requires(dest):
        return False

    conn._sign_and_submit = fake_submit  # type: ignore[method-assign]
    conn.get_xrp_balance = fake_balance  # type: ignore[method-assign]
    conn.destination_requires_dest_tag = fake_requires  # type: ignore[method-assign]
    conn.load_wallet = lambda: object()  # type: ignore[method-assign]

    tx_hash = asyncio.run(
        conn.send_payment(
            destination=_DEST,
            amount=10.0,
            asset="XRP",
            xrp_reserve=1.0,
            destination_tag=424242,
            memo="exchange deposit",
        )
    )
    assert tx_hash == "ABC123"
    tx = captured["tx"]
    assert tx.destination_tag == 424242
    assert tx.destination == _DEST
    assert tx.memos and tx.memos[0].memo_data == "exchange deposit".encode("utf-8").hex().upper()


def test_send_payment_blocks_when_dest_requires_tag() -> None:
    conn = XRPLConnector.__new__(XRPLConnector)
    conn.account_address = _BOT

    async def fake_requires(dest):
        return True

    conn.destination_requires_dest_tag = fake_requires  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="requires a destination tag"):
        asyncio.run(
            conn.send_payment(
                destination=_DEST,
                amount=10.0,
                asset="XRP",
                xrp_reserve=1.0,
            )
        )


def test_validate_tec_dst_tag_needed() -> None:
    resp = SimpleNamespace(
        result={"hash": "DEAD", "meta": {"TransactionResult": "tecDST_TAG_NEEDED"}}
    )
    with pytest.raises(RuntimeError, match="tecDST_TAG_NEEDED"):
        XRPLConnector._validate_tx_response(resp)
