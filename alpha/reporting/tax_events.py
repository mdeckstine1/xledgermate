"""Log Alpha bracket fills and related activity to the monthly tax CSV."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Set

from alpha.orders.types import BracketFillEvent
from monitoring.csv_logger import CSVLogger

_logged_keys: Set[str] = set()
_strength_logged_keys: Set[str] = set()


def _dedupe_key(event: BracketFillEvent) -> str:
    return (
        f"{event.bracket_id}:{event.leg}:"
        f"{event.filled_xrp:.6f}:{event.price_rlusd_per_xrp:.6f}:"
        f"{event.new_state.value}"
    )


def _strength_key(sequence: int, size_xrp: float, price: float) -> str:
    return f"strength:{sequence}:{size_xrp:.6f}:{price:.6f}"


def reset_tax_event_dedupe_for_tests() -> None:
    """Clear in-process dedupe keys (tests only)."""
    _logged_keys.clear()
    _strength_logged_keys.clear()


def _usd_per_rlusd() -> float:
    try:
        from config.settings import BotConfig

        rate = float(BotConfig.load().alpha_tax_usd_per_rlusd)
        return rate if rate > 0 else 1.0
    except Exception:
        return 1.0


def _sell_proceeds_usd(rlusd_amount: float) -> float:
    return float(rlusd_amount) * _usd_per_rlusd()


def log_bracket_fill_tax_event(
    *,
    event: BracketFillEvent,
    entry_price: float,
    network: str,
    dry_run: bool,
    mid: Optional[float] = None,
    cycle: int = 0,
    log_dir: str | Path = "logs",
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

    logger = CSVLogger(log_dir=str(log_dir))
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
            cost_basis_rlusd_per_xrp=price,
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
            cost_basis_rlusd_per_xrp=entry if entry > 0 else None,
            proceeds_usd=_sell_proceeds_usd(rlusd),
            notes=f"alpha bracket {leg_label} {bracket_ref}{partial_note} entry={entry:.6f}",
        )
        return True

    return False


def log_strength_sell_tax_event(
    *,
    sequence: int,
    size_xrp: float,
    price_rlusd_per_xrp: float,
    network: str,
    dry_run: bool,
    cost_basis_rlusd_per_xrp: Optional[float] = None,
    mid: Optional[float] = None,
    cycle: int = 0,
    log_dir: str | Path = "logs",
) -> bool:
    """Log a filled inventory strength sell (non-bracket ask)."""
    if dry_run or size_xrp <= 0 or price_rlusd_per_xrp <= 0:
        return False

    key = _strength_key(sequence, size_xrp, price_rlusd_per_xrp)
    if key in _strength_logged_keys:
        return False
    _strength_logged_keys.add(key)

    from alpha.reporting.tax_ledger import estimate_avg_cost_basis_rlusd

    basis = cost_basis_rlusd_per_xrp
    if basis is None or basis <= 0:
        basis = estimate_avg_cost_basis_rlusd(Path(log_dir))

    filled = float(size_xrp)
    price = float(price_rlusd_per_xrp)
    rlusd = filled * price
    profit_rlusd = (price - basis) * filled if basis > 0 else 0.0
    mark_mid = mid if mid and mid > 0 else price
    profit_xrp = profit_rlusd / mark_mid if mark_mid > 0 else 0.0

    logger = CSVLogger(log_dir=str(log_dir))
    logger.log_sell(
        network=network,
        xrp_amount=filled,
        rlusd_amount=rlusd,
        price_rlusd_per_xrp=price,
        profit_xrp_equiv=profit_xrp,
        cycle=cycle,
        cost_basis_rlusd_per_xrp=basis if basis > 0 else None,
        proceeds_usd=_sell_proceeds_usd(rlusd),
        notes=f"alpha strength sell seq={sequence} basis={basis:.6f}",
    )
    return True
