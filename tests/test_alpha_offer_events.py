"""Tests for XRPL offer cancel detection (bracket safety)."""

from __future__ import annotations

from alpha.ledger.offer_events import offer_cancel_seen


def test_offer_cancel_seen_by_offer_sequence():
    messages = [
        {
            "type": "transaction",
            "transaction": {
                "TransactionType": "OfferCancel",
                "OfferSequence": 500,
                "Account": "rTest",
            },
        }
    ]
    assert offer_cancel_seen(messages, 500)
    assert not offer_cancel_seen(messages, 501)


def test_offer_cancel_seen_ignores_other_tx_types():
    messages = [
        {
            "type": "transaction",
            "transaction": {
                "TransactionType": "Payment",
                "Account": "rTest",
            },
        }
    ]
    assert not offer_cancel_seen(messages, 500)
