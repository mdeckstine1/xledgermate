"""Cancel all DEX offers for the bot account and refresh GUI runtime state."""

from __future__ import annotations

from typing import Tuple

from config.settings import BotConfig
from connectors.xrpl_connector import XRPLConnector, XRPLNetworkConfig
from utils.ledger_balances import sync_ledger_balances_to_runtime


async def cancel_all_offers_and_sync(
    config: BotConfig | None = None,
) -> Tuple[bool, str, int, int]:
    """
    Cancel open offers on-ledger, then patch runtime_state from live RPC.

    Returns (ok, message, cancelled_count, remaining_count).
    """
    cfg = config or BotConfig.load()
    address = cfg.bot_account_address.strip()
    secret = (cfg.bot_secret_key or "").strip()
    if not address:
        raise ValueError("Set bot_account_address in config.")
    if not secret:
        raise ValueError(
            "Bot secret required to cancel offers (Advanced → Bot account → Save credentials)."
        )

    connector = XRPLConnector(
        account_address=address,
        secret=secret,
        rlusd_issuer=cfg.resolved_rlusd_issuer(),
        rlusd_currency=cfg.resolved_rlusd_currency_code(),
        network=XRPLNetworkConfig(json_rpc_url=cfg.resolved_rpc_url()),
    )

    before = await connector.get_open_offer_sequences()
    if not before:
        await sync_ledger_balances_to_runtime(cfg)
        return True, "No open offers on the ledger.", 0, 0

    cancelled = await connector.cancel_all_offers()
    remaining = await connector.get_open_offer_sequences()
    await sync_ledger_balances_to_runtime(cfg)

    if remaining:
        return (
            False,
            f"Cancelled {cancelled} offer(s), but **{len(remaining)}** still on ledger "
            f"(seq {remaining[:5]}). Check Xaman or retry.",
            cancelled,
            len(remaining),
        )
    if cancelled == 0 and before:
        return (
            False,
            f"Found {len(before)} offer(s) but none were cancelled — check bot secret and RPC.",
            0,
            len(before),
        )
    return (
        True,
        f"Cancelled {cancelled} offer(s) on the ledger. GUI refreshed from RPC.",
        cancelled,
        0,
    )


def cancel_all_offers_and_sync_sync(
    config: BotConfig | None = None,
) -> Tuple[bool, str, int, int]:
    import asyncio

    return asyncio.run(cancel_all_offers_and_sync(config))
