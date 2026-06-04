"""Trustworthy mid helper used for PnL and fill capture."""

from connectors.xrpl_connector import is_trustworthy_rlusd_mid


def test_crossed_book_mid_rejected() -> None:
    assert not is_trustworthy_rlusd_mid(0.283, best_bid=1.164, best_ask=0.283)


def test_normal_mid_accepted() -> None:
    assert is_trustworthy_rlusd_mid(1.175, best_bid=1.174, best_ask=1.176)
