"""RLUSD currency code must be 40-char hex for xrpl-py BookOffers."""

from connectors.xrpl_connector import XRPLConnector
from utils.xrpl_currency import RLUSD_CURRENCY_HEX, resolve_rlusd_currency_code


def test_resolve_rlusd_from_display_name() -> None:
    assert resolve_rlusd_currency_code("RLUSD") == RLUSD_CURRENCY_HEX
    assert len(resolve_rlusd_currency_code("rlusd")) == 40


def test_connector_never_uses_display_name_for_book() -> None:
    conn = XRPLConnector(
        account_address="rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe",
        secret=None,
        rlusd_issuer="rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De",
        rlusd_currency="RLUSD",
    )
    assert conn._issued_rlusd_currency_code() == RLUSD_CURRENCY_HEX
    assert conn._issued_rlusd_currency_code() != "RLUSD"
