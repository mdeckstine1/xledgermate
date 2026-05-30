"""Tests for ledger-accurate fill parsing."""

from monitoring.ledger_fills import LedgerFillScanner, parse_ledger_fill_from_tx


def _sell_fill_tx() -> dict:
    return {
        "hash": "ABC123",
        "ledger_index": 9000001,
        "tx": {
            "TransactionType": "Payment",
            "Account": "rTaker",
            "hash": "ABC123",
        },
        "meta": {
            "TransactionResult": "tesSUCCESS",
            "AffectedNodes": [
                {
                    "ModifiedNode": {
                        "LedgerEntryType": "AccountRoot",
                        "PreviousFields": {"Balance": "100000000"},
                        "FinalFields": {
                            "Account": "rBot",
                            "Balance": "95000000",
                        },
                    }
                },
                {
                    "ModifiedNode": {
                        "LedgerEntryType": "RippleState",
                        "PreviousFields": {"Balance": "0"},
                        "FinalFields": {
                            "Balance": "32.5",
                            "HighLimit": {"issuer": "rIssuer", "account": "rBot"},
                            "LowLimit": {"issuer": "rIssuer", "account": "rOther"},
                        },
                    }
                },
            ],
        },
    }


def test_parse_sell_fill_from_meta() -> None:
    fill = parse_ledger_fill_from_tx(
        _sell_fill_tx(),
        account="rBot",
        rlusd_currency="524C555344000000000000000000000000000000",
        rlusd_issuer="rIssuer",
    )
    assert fill is not None
    assert fill.side == "SELL"
    assert fill.rlusd_amount == 32.5
    assert fill.tx_hash == "ABC123"


def test_scanner_dedupes_tx_hash() -> None:
    scanner = LedgerFillScanner(cursor_path="logs/test_ledger_fill_cursor.json")
    scanner.cursor.seen_tx_hashes.clear()
    txs = [_sell_fill_tx()]
    first = scanner.scan_transactions(
        txs,
        account="rBot",
        rlusd_currency="524C555344000000000000000000000000000000",
        rlusd_issuer="rIssuer",
    )
    second = scanner.scan_transactions(
        txs,
        account="rBot",
        rlusd_currency="524C555344000000000000000000000000000000",
        rlusd_issuer="rIssuer",
    )
    assert len(first) == 1
    assert len(second) == 0
