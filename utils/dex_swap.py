"""Operator XRP/RLUSD DEX swap. Preview is pure; execute signs one IOC offer."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

MAX_SWAP_XRP = 200.0
DEFAULT_MAX_SLIPPAGE_BPS = 30.0
MIN_SWAP_XRP = 1.0
_FILL_DUST_XRP = 0.0001
_FILL_DUST_RLUSD = 0.0001

DIRECTIONS = ("xrp_to_rlusd", "rlusd_to_xrp")


def _f(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _levels(book: Dict[str, Any], side: str) -> List[Dict[str, float]]:
    raw = book.get(side) or []
    out: List[Dict[str, float]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        price = _f(row.get("price"))
        size = _f(row.get("size"))
        if price > 0 and size > 0:
            out.append({"price": price, "size": size})
    return out


def _fail(message: str, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"ok": False, "message": message}
    payload.update(extra)
    return payload


def preview_swap(
    *,
    direction: str,
    amount: float,
    book: Dict[str, Any],
    xrp_balance: float,
    rlusd_balance: float,
    xrp_reserve: float,
    open_offer_count: int = 0,
    has_rlusd_trust: bool = True,
    max_slippage_bps: float = DEFAULT_MAX_SLIPPAGE_BPS,
) -> Dict[str, Any]:
    """Walk the live book. Refuse unless the whole amount fills inside the slippage cap."""
    if direction not in DIRECTIONS:
        return _fail("Direction must be xrp_to_rlusd or rlusd_to_xrp.")
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return _fail("Amount must be a number.")
    if amount <= 0:
        return _fail("Amount must be greater than zero.")

    try:
        slip = float(max_slippage_bps)
    except (TypeError, ValueError):
        slip = DEFAULT_MAX_SLIPPAGE_BPS
    slip = max(1.0, min(DEFAULT_MAX_SLIPPAGE_BPS, slip))

    if open_offer_count > 0:
        return _fail("Cancel open offers before swapping. A swap must not cross the bot's own quotes.")
    if not has_rlusd_trust:
        return _fail("No RLUSD trust line on the bot account.")

    bids = _levels(book, "bids")
    asks = _levels(book, "asks")
    if not bids or not asks:
        return _fail("Need a two-sided XRP/RLUSD book to price the swap.")

    best_bid = max(row["price"] for row in bids)
    best_ask = min(row["price"] for row in asks)
    if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask:
        return _fail("Book is crossed or empty. Refresh and try again.")
    mid = (best_bid + best_ask) / 2.0

    reserve = max(0.0, _f(xrp_reserve))
    spendable_xrp = max(0.0, _f(xrp_balance) - reserve)

    if direction == "xrp_to_rlusd":
        if amount < MIN_SWAP_XRP:
            return _fail(f"Minimum swap is {MIN_SWAP_XRP:g} XRP.")
        if amount > MAX_SWAP_XRP:
            return _fail(f"Maximum swap is {MAX_SWAP_XRP:g} XRP per click.")
        if amount > spendable_xrp + 1e-9:
            return _fail(
                f"Swap would enter the XRP reserve. Balance={_f(xrp_balance):.4f}, "
                f"amount={amount:.4f}, reserve={reserve:.4f}, spendable={spendable_xrp:.4f}."
            )
        worst = mid * (1.0 - slip / 10_000.0)
        filled_xrp, rlusd_out = _walk_sell(bids, amount, worst)
        if amount - filled_xrp > _FILL_DUST_XRP:
            return _fail(
                f"Book cannot fill {amount:.4f} XRP inside {slip:.0f} bps of mid "
                f"({filled_xrp:.4f} XRP available at or above {worst:.6f})."
            )
        average = rlusd_out / filled_xrp
        slippage_bps = (mid - average) / mid * 10_000.0
        return {
            "ok": True,
            "message": (
                f"Sell {filled_xrp:.4f} XRP for about {rlusd_out:.4f} RLUSD "
                f"at avg {average:.6f} ({slippage_bps:.1f} bps vs mid {mid:.6f})."
            ),
            "direction": direction,
            "amount": amount,
            "mid": mid,
            "best_price": best_bid,
            "average_price": average,
            "limit_price": worst,
            "output_amount": rlusd_out,
            "output_asset": "RLUSD",
            "slippage_bps": slippage_bps,
            "max_slippage_bps": slip,
            "xrp_leg": filled_xrp,
            "rlusd_leg": filled_xrp * worst,
            "fully_filled": True,
        }

    xrp_equiv = amount / mid
    if xrp_equiv < MIN_SWAP_XRP:
        return _fail(f"Minimum swap is about {MIN_SWAP_XRP:g} XRP ({MIN_SWAP_XRP * mid:.4f} RLUSD at mid).")
    if xrp_equiv > MAX_SWAP_XRP:
        return _fail(
            f"Maximum swap is {MAX_SWAP_XRP:g} XRP equivalent "
            f"({MAX_SWAP_XRP * mid:.4f} RLUSD at mid)."
        )
    if amount > _f(rlusd_balance) + 1e-9:
        return _fail(
            f"Insufficient RLUSD. Balance={_f(rlusd_balance):.4f}, amount={amount:.4f}."
        )
    if spendable_xrp <= 0:
        return _fail(
            f"XRP balance {_f(xrp_balance):.4f} is inside the reserve {reserve:.4f}. "
            "A swap still pays a tiny fee."
        )
    worst = mid * (1.0 + slip / 10_000.0)
    rlusd_spent, xrp_out = _walk_buy(asks, amount, worst)
    if amount - rlusd_spent > _FILL_DUST_RLUSD:
        return _fail(
            f"Book cannot fill {amount:.4f} RLUSD inside {slip:.0f} bps of mid "
            f"({rlusd_spent:.4f} RLUSD available at or below {worst:.6f})."
        )
    average = rlusd_spent / xrp_out
    slippage_bps = (average - mid) / mid * 10_000.0
    return {
        "ok": True,
        "message": (
            f"Spend {rlusd_spent:.4f} RLUSD for about {xrp_out:.4f} XRP "
            f"at avg {average:.6f} ({slippage_bps:.1f} bps vs mid {mid:.6f})."
        ),
        "direction": direction,
        "amount": amount,
        "mid": mid,
        "best_price": best_ask,
        "average_price": average,
        "limit_price": worst,
        "output_amount": xrp_out,
        "output_asset": "XRP",
        "slippage_bps": slippage_bps,
        "max_slippage_bps": slip,
        "xrp_leg": rlusd_spent / worst,
        "rlusd_leg": rlusd_spent,
        "fully_filled": True,
    }


def _walk_sell(bids: List[Dict[str, float]], xrp_amount: float, worst: float) -> tuple[float, float]:
    remaining = xrp_amount
    rlusd_out = 0.0
    for row in sorted(bids, key=lambda item: item["price"], reverse=True):
        if row["price"] + 1e-12 < worst:
            break
        take = min(remaining, row["size"])
        rlusd_out += take * row["price"]
        remaining -= take
        if remaining <= _FILL_DUST_XRP:
            break
    return xrp_amount - remaining, rlusd_out


def _walk_buy(asks: List[Dict[str, float]], rlusd_amount: float, worst: float) -> tuple[float, float]:
    remaining = rlusd_amount
    xrp_out = 0.0
    for row in sorted(asks, key=lambda item: item["price"]):
        if row["price"] - 1e-12 > worst:
            break
        level_rlusd = row["size"] * row["price"]
        spend = min(remaining, level_rlusd)
        xrp_out += spend / row["price"]
        remaining -= spend
        if remaining <= _FILL_DUST_RLUSD:
            break
    return rlusd_amount - remaining, xrp_out


def _log_swap(row: Dict[str, Any]) -> None:
    path = Path("logs/swaps.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    fields = [
        "timestamp_utc",
        "direction",
        "requested",
        "xrp_delta",
        "rlusd_delta",
        "average_price",
        "tx_hash",
        "partial",
    ]
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if write_header:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in fields})


async def preview_swap_for_operator(
    *,
    direction: str,
    amount: float,
    max_slippage_bps: float = DEFAULT_MAX_SLIPPAGE_BPS,
) -> Dict[str, Any]:
    from config.settings import BotConfig
    from connectors import XRPLConnector, XRPLNetworkConfig

    config = BotConfig.load()
    if not (config.bot_account_address or "").strip():
        return _fail("bot_account_address is not configured.")
    connector = XRPLConnector(
        account_address=config.bot_account_address.strip(),
        secret=config.bot_secret_key,
        rlusd_issuer=config.resolved_rlusd_issuer(),
        rlusd_currency=config.resolved_rlusd_currency_code(),
        network=XRPLNetworkConfig(json_rpc_url=config.resolved_rpc_url()),
    )
    book = await connector.fetch_xrp_rlusd_order_book()
    xrp_balance = await connector.get_xrp_balance()
    trust = await connector.get_rlusd_trust_line()
    open_offers = await connector.get_open_offer_sequences()
    return preview_swap(
        direction=direction,
        amount=amount,
        book=book,
        xrp_balance=xrp_balance,
        rlusd_balance=trust.balance,
        xrp_reserve=float(config.xrp_reserve),
        open_offer_count=len(open_offers),
        has_rlusd_trust=trust.exists,
        max_slippage_bps=max_slippage_bps,
    )


async def execute_swap_for_operator(
    *,
    direction: str,
    amount: float,
    max_slippage_bps: float = DEFAULT_MAX_SLIPPAGE_BPS,
) -> Dict[str, Any]:
    """Re-preview on a fresh book, then sign one IOC offer. Does not rest a quote."""
    from config.settings import BotConfig
    from connectors import XRPLConnector, XRPLNetworkConfig

    config = BotConfig.load()
    if not (config.bot_account_address or "").strip():
        raise ValueError("bot_account_address is not configured.")
    if not (config.bot_secret_key or "").strip():
        raise ValueError("bot_secret_key is required to swap.")

    connector = XRPLConnector(
        account_address=config.bot_account_address.strip(),
        secret=config.bot_secret_key,
        rlusd_issuer=config.resolved_rlusd_issuer(),
        rlusd_currency=config.resolved_rlusd_currency_code(),
        network=XRPLNetworkConfig(json_rpc_url=config.resolved_rpc_url()),
    )
    book = await connector.fetch_xrp_rlusd_order_book()
    xrp_before = await connector.get_xrp_balance()
    trust = await connector.get_rlusd_trust_line()
    open_offers = await connector.get_open_offer_sequences()
    preview = preview_swap(
        direction=direction,
        amount=amount,
        book=book,
        xrp_balance=xrp_before,
        rlusd_balance=trust.balance,
        xrp_reserve=float(config.xrp_reserve),
        open_offer_count=len(open_offers),
        has_rlusd_trust=trust.exists,
        max_slippage_bps=max_slippage_bps,
    )
    if not preview.get("ok"):
        raise ValueError(str(preview.get("message") or "Swap preview refused."))

    tx_hash, offer_seq, resting = await connector.place_ioc_swap(
        direction=direction,
        xrp_amount=float(preview["xrp_leg"]),
        rlusd_amount=float(preview["rlusd_leg"]),
    )
    if resting:
        if offer_seq:
            await connector.cancel_offer(int(offer_seq))
        else:
            await connector.cancel_all_offers()
        raise RuntimeError(
            "Swap left a resting offer and it was cancelled. Check balances before trying again. "
            f"hash={tx_hash}"
        )

    xrp_after = await connector.get_xrp_balance()
    rlusd_after = await connector.get_rlusd_balance()
    # Positive xrp_delta means XRP left the wallet. Positive rlusd_delta means RLUSD arrived.
    xrp_delta = xrp_before - xrp_after
    rlusd_delta = rlusd_after - trust.balance
    no_fill = abs(rlusd_delta) < 0.01 and abs(xrp_delta) < 0.001
    if direction == "xrp_to_rlusd":
        sold = max(0.0, xrp_delta)
        partial = (not no_fill) and sold + 0.01 < float(preview["xrp_leg"]) * 0.98
        average = (rlusd_delta / sold) if sold > 0.0001 and rlusd_delta > 0 else None
    else:
        spent = max(0.0, -rlusd_delta)
        partial = (not no_fill) and spent + 0.05 < float(preview["rlusd_leg"]) * 0.98
        bought = max(0.0, -xrp_delta)
        average = (spent / bought) if bought > 0.0001 and spent > 0 else None

    _log_swap(
        {
            "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
            "direction": direction,
            "requested": f"{amount:.6f}",
            "xrp_delta": f"{xrp_delta:.6f}",
            "rlusd_delta": f"{rlusd_delta:.6f}",
            "average_price": "" if average is None else f"{average:.6f}",
            "tx_hash": tx_hash,
            "partial": "no-fill" if no_fill else ("yes" if partial else "no"),
        }
    )
    if no_fill:
        filled_note = "No fill — the book moved. Nothing is resting. "
    elif partial:
        filled_note = "Partial fill. "
    else:
        filled_note = ""
    return {
        "ok": True,
        "partial": partial or no_fill,
        "no_fill": no_fill,
        "tx_hash": tx_hash,
        "direction": direction,
        "xrp_before": xrp_before,
        "xrp_after": xrp_after,
        "rlusd_before": trust.balance,
        "rlusd_after": rlusd_after,
        "xrp_delta": xrp_delta,
        "rlusd_delta": rlusd_delta,
        "average_price": average,
        "message": (
            f"{filled_note}Swap submitted. XRP {xrp_before:.4f} → {xrp_after:.4f}, "
            f"RLUSD {trust.balance:.4f} → {rlusd_after:.4f}."
        ),
    }
