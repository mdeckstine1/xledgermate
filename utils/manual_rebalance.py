"""Live inventory rebalance assessment (advisory — no on-chain swap)."""

from __future__ import annotations

from typing import Any, Dict

from config.settings import BotConfig
from connectors import XRPLConnector, XRPLNetworkConfig
from core.market_conditions import compute_book_spread_pct
from strategy.inventory_balance import RebalanceAdvice, assess_rebalance_need
from utils.gui_runtime_sync import patch_runtime_state_file


async def run_manual_rebalance_check(config: BotConfig | None = None) -> str:
    """
    Fetch ledger balances + book mid, assess inventory vs target, patch runtime_state for GUI.
    Returns a short human-readable summary (does not swap on-chain).
    """
    cfg = config or BotConfig.load()
    if not cfg.bot_account_address.strip():
        raise ValueError("Set bot_account_address in config before rebalancing.")
    if not (cfg.bot_secret_key or "").strip():
        raise ValueError("bot_secret_key is required to read balances from the ledger.")

    connector = XRPLConnector(
        account_address=cfg.bot_account_address.strip(),
        secret=cfg.bot_secret_key,
        rlusd_issuer=cfg.resolved_rlusd_issuer(),
        rlusd_currency=cfg.resolved_rlusd_currency_code(),
        network=XRPLNetworkConfig(json_rpc_url=cfg.resolved_rpc_url()),
    )

    xrp = await connector.get_xrp_balance()
    rlusd = await connector.get_rlusd_balance()
    order_book = await connector.fetch_xrp_rlusd_order_book()
    best_bid, best_ask = connector.compute_best_prices(order_book)
    mid_raw = connector.compute_mid_price(order_book)
    mid = float(mid_raw or 0.0)
    spendable = max(0.0, xrp - float(cfg.xrp_reserve))

    advice = assess_rebalance_need(
        xrp_balance=xrp,
        rlusd_balance=rlusd,
        mid_price=mid,
        target_xrp_ratio=float(cfg.inventory_target_xrp_ratio),
        spendable_xrp=spendable,
        xrp_reserve=float(cfg.xrp_reserve),
        min_order_xrp=float(cfg.min_order_size_xrp),
        fund_with_xrp_only=bool(cfg.fund_with_xrp_only),
    )

    total_xrp = xrp + (rlusd / mid if mid > 0 else 0.0)
    ratio = (xrp / total_xrp) if total_xrp > 0 else 0.0
    port_xrp = total_xrp
    port_rlusd = port_xrp * mid if mid > 0 else 0.0

    patch: Dict[str, Any] = {
        "balance_xrp": xrp,
        "balance_rlusd": rlusd,
        "mid_price": mid if mid > 0 else None,
        "portfolio_value_xrp": port_xrp,
        "rebalance_action": advice.action,
        "rebalance_summary": advice.summary,
        "inventory_label": advice.label,
        "best_bid_rlusd_per_xrp": best_bid,
        "best_ask_rlusd_per_xrp": best_ask,
        "book_spread_pct": compute_book_spread_pct(best_bid, best_ask),
    }
    patch_runtime_state_file(patch)

    target = float(cfg.inventory_target_xrp_ratio)
    lines = [
        f"XRP {xrp:.4f} | RLUSD {rlusd:.4f}",
        f"Mix **{ratio:.0%} XRP** (target **{target:.0%} XRP**)",
        advice.summary,
    ]
    if advice.suggested_xrp_to_convert > 0 and advice.action == "reduce_xrp":
        lines.append(
            f"Suggested manual swap: ~**{advice.suggested_xrp_to_convert:.1f} XRP -> RLUSD** "
            "(e.g. in Xaman) - bot does not auto-swap."
        )
    elif advice.action == "accumulate_rlusd":
        lines.append("Steer via bot quotes (bids on) or swap RLUSD -> XRP in Xaman if you want more XRP.")
    return "\n\n".join(lines)


def run_manual_rebalance_check_sync(config: BotConfig | None = None) -> str:
    import asyncio

    return asyncio.run(run_manual_rebalance_check(config))
