"""Unit tests for experimental WebSocket book message parsing (no network)."""

from connectors.xrpl_connector import XRPLConnector
from experimental.ws_feed.book_messages import extract_offers_from_message


def test_response_snapshot_ask_side() -> None:
    issuer = "rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De"
    message = {
        "type": "response",
        "result": {
            "taker_gets": {"currency": "XRP"},
            "taker_pays": {"currency": "USD", "issuer": issuer, "value": "1"},
            "offers": [
                {
                    "TakerGets": "1000000",
                    "TakerPays": {
                        "currency": "524C555344000000000000000000000000",
                        "issuer": issuer,
                        "value": "1.18",
                    },
                }
            ],
        },
    }
    rows = extract_offers_from_message(message, rlusd_issuer=issuer)
    assert len(rows) == 1
    side, offers, deleted = rows[0]
    assert side == "ask"
    assert not deleted
    assert len(offers) == 1


def test_normalize_ask_price() -> None:
    issuer = "rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De"
    conn = XRPLConnector.__new__(XRPLConnector)
    raw = [
        {
            "TakerGets": "2000000",
            "TakerPays": {
                "currency": "524C555344000000000000000000000000",
                "issuer": issuer,
                "value": "2.36",
            },
        }
    ]
    out = conn._normalize_offers(raw, side="ask")
    assert len(out) == 1
    assert out[0]["price"] > 0.9