"""Bracket price math and leg sizing."""

from __future__ import annotations

from dataclasses import dataclass

from alpha.precision import price_decimals, round_rlusd_price
from config.settings import BotConfig


@dataclass(frozen=True)
class BracketPrices:
    """Computed TP/SL limit prices for a long-XRP bracket."""

    entry_price_rlusd_per_xrp: float
    take_profit_price: float
    stop_loss_price: float
    take_profit_pct_effective: float
    stop_loss_pct: float
    pricing_mode: str  # "rr" | "fixed_pct"


def compute_bracket_prices(
    entry_price_rlusd_per_xrp: float,
    config: BotConfig,
) -> BracketPrices:
    """
    Compute TP and SL limit prices after a buy fill.

    When ``take_profit_rr > 0``, TP distance = ``initial_stop_loss_pct * take_profit_rr``
  (risk-reward mode). Otherwise ``take_profit_pct`` is used as a fixed % above entry.
    """
    if entry_price_rlusd_per_xrp <= 0:
        raise ValueError("entry_price_rlusd_per_xrp must be positive")

    sl_pct = max(0.0, config.initial_stop_loss_pct)
    dec = price_decimals(config)
    sl_price = round_rlusd_price(entry_price_rlusd_per_xrp * (1.0 - sl_pct), dec, direction="down")

    if config.take_profit_rr > 0:
        tp_pct = sl_pct * config.take_profit_rr
        mode = "rr"
    else:
        tp_pct = max(0.0, config.take_profit_pct)
        mode = "fixed_pct"

    tp_price = round_rlusd_price(entry_price_rlusd_per_xrp * (1.0 + tp_pct), dec, direction="up")
    return BracketPrices(
        entry_price_rlusd_per_xrp=entry_price_rlusd_per_xrp,
        take_profit_price=tp_price,
        stop_loss_price=sl_price,
        take_profit_pct_effective=tp_pct,
        stop_loss_pct=sl_pct,
        pricing_mode=mode,
    )


def normalize_partial_fill_mode(mode: str) -> str:
    normalized = (mode or "wait_full").strip().lower()
    if normalized not in ("wait_full", "proportional"):
        raise ValueError(f"unsupported partial_fill_mode: {mode!r}")
    return normalized
