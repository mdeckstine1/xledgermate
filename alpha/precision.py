"""RLUSD/XRP price rounding — operator-tunable via alpha_rlusd_price_decimals."""

from __future__ import annotations

import math
from typing import Literal, Union

from config.settings import BotConfig

DEFAULT_ALPHA_RLUSD_PRICE_DECIMALS = 2
MIN_ALPHA_RLUSD_PRICE_DECIMALS = 0
MAX_ALPHA_RLUSD_PRICE_DECIMALS = 6

RoundDirection = Literal["nearest", "down", "up"]


def clamp_price_decimals(decimals: int) -> int:
    return max(MIN_ALPHA_RLUSD_PRICE_DECIMALS, min(MAX_ALPHA_RLUSD_PRICE_DECIMALS, int(decimals)))


def price_decimals(config: Union[BotConfig, None] = None, *, default: int = DEFAULT_ALPHA_RLUSD_PRICE_DECIMALS) -> int:
    if config is None:
        return default
    raw = getattr(config, "alpha_rlusd_price_decimals", default)
    try:
        return clamp_price_decimals(int(raw))
    except (TypeError, ValueError):
        return default


def price_eps(decimals: int) -> float:
    dec = clamp_price_decimals(decimals)
    if dec <= 0:
        return 0.5
    return 10 ** (-dec) / 2.0


def round_rlusd_price(
    price: float,
    decimals: int,
    *,
    direction: RoundDirection = "nearest",
) -> float:
    dec = clamp_price_decimals(decimals)
    factor = 10**dec
    scaled = float(price) * factor
    if direction == "down":
        return math.floor(scaled + 1e-12) / factor
    if direction == "up":
        return math.ceil(scaled - 1e-12) / factor
    return round(float(price), dec)


def format_rlusd_price(price: float, decimals: int) -> str:
    dec = clamp_price_decimals(decimals)
    return f"{round_rlusd_price(price, dec):.{dec}f}"


def format_rlusd_amount(amount: float, decimals: int) -> str:
    """RLUSD leg on offers — enough precision for size × price at chosen decimals."""
    dec = clamp_price_decimals(decimals)
    amount_decimals = min(MAX_ALPHA_RLUSD_PRICE_DECIMALS, max(dec, dec + 2))
    return f"{round(float(amount), amount_decimals):.{amount_decimals}f}"
