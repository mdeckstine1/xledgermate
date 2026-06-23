"""Tests for RLUSD/XRP price precision helpers."""

from alpha.precision import (
    format_rlusd_price,
    price_eps,
    round_rlusd_price,
)
from alpha.orders.stale_pending import target_buy_limit_price


def test_round_rlusd_price_down_up():
    assert round_rlusd_price(1.09835, 2, direction="down") == 1.09
    assert round_rlusd_price(1.0912, 2, direction="up") == 1.10


def test_target_buy_limit_price_uses_floor():
    assert target_buy_limit_price(1.10, 0.15, price_decimals=2) == 1.09
    assert target_buy_limit_price(1.10, 0.15, price_decimals=6) < 1.10


def test_price_eps_scales_with_decimals():
    assert price_eps(2) == 0.005
    assert price_eps(6) == 0.0000005


def test_format_rlusd_price():
    assert format_rlusd_price(1.1, 2) == "1.10"
