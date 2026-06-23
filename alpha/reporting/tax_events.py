"""Log Alpha bracket fills and related activity to the monthly tax CSV."""

from __future__ import annotations

from typing import Optional, Set

from alpha.orders.types import BracketFillEvent
from monitoring.csv_logger import CSVLogger

_logged_keys: Set[str] = set()


def _dedupe_key(event: BracketFillEvent) -> str:
    return (
        f"{event.bracket_id}:{event.leg}:"
        f"{event.filled_xrp:.6f}:{event.price_rlusd_per_xrp:.6f}:"
        f"{event.new_state.value}"
    )


def reset_tax_event_dedupe_for_tests() -> None:
    """Clear in-process dedupe keys (tests only)."""
    _logged_keys.clear()


def log_bracket_fill_tax_event(
    *,
    event: BracketFillEvent,
    entry_price: float,
    network: str,
    dry_run: bool,
    mid: Optional[float] = None,
    cycle: int = 0,
) -> bool:
    """
    Append one taxable row to ``logs/trades_YYYY-MM.csv``.

    Returns True when a row was written.
    """
    if dry_run or event.filled_xrp <= 0:
        return False

    key = _dedupe_key(event)
    if key in _logged_keys:
        return False
    _logged_keys.add(key)

    logger = CSVLogger()
    filled = float(event.filled_xrp)
    price = float(event.price_rlusd_per_xrp)
    rlusd = filled * price
    bracket_ref = event.bracket_id[:8]
    partial_note = " partial" if event.partial else ""

    if event.leg == "buy":
        logger.log_buy(
            network=network,
            xrp_amount=filled,
            rlusd_amount=rlusd,
            price_rlusd_per_xrp=price,
            cycle=cycle,
            notes=f"alpha bracket buy {bracket_ref}{partial_note}",
        )
        return True

    if event.leg in ("tp", "sl"):
        entry = max(entry_price, 0.0)
        profit_rlusd = (price - entry) * filled if entry > 0 else 0.0
        mark_mid = mid if mid and mid > 0 else price
        profit_xrp = profit_rlusd / mark_mid if mark_mid > 0 else 0.0
        leg_label = "take-profit" if event.leg == "tp" else "stop-loss"
        logger.log_sell(
            network=network,
            xrp_amount=filled,
            rlusd_amount=rlusd,
            price_rlusd_per_xrp=price,
            profit_xrp_equiv=profit_xrp,
            cycle=cycle,
            notes=f"alpha bracket {leg_label} {bracket_ref}{partial_note} entry={entry:.6f}",
        )
        return True

    return False
