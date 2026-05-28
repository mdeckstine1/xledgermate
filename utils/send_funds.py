"""Send funds from the Bot Account to another XRPL address."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from config.settings import BotConfig
from connectors import XRPLConnector, XRPLNetworkConfig
from monitoring.csv_logger import CSVLogger


def _log_transfer(
    *,
    network: str,
    asset: str,
    amount: float,
    destination: str,
    tx_hash: str,
) -> None:
    path = Path("logs/transfers.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if write_header:
            writer.writerow(
                ["timestamp_utc", "network", "asset", "amount", "destination", "tx_hash"]
            )
        writer.writerow(
            [
                datetime.now(tz=timezone.utc).isoformat(),
                network,
                asset,
                f"{amount:.6f}",
                destination,
                tx_hash,
            ]
        )


async def send_from_bot_account(
    *,
    destination: str,
    amount: float,
    asset: str = "XRP",
) -> str:
    config = BotConfig.load()
    if not config.bot_account_address.strip():
        raise ValueError("bot_account_address is not configured.")
    if not (config.bot_secret_key or "").strip():
        raise ValueError("bot_secret_key is required to send funds.")

    connector = XRPLConnector(
        account_address=config.bot_account_address.strip(),
        secret=config.bot_secret_key,
        rlusd_issuer=config.resolved_rlusd_issuer(),
        rlusd_currency=config.resolved_rlusd_currency_code(),
        network=XRPLNetworkConfig(json_rpc_url=config.resolved_rpc_url()),
    )
    tx_hash = await connector.send_payment(
        destination=destination.strip(),
        amount=amount,
        asset=asset,
        xrp_reserve=config.xrp_reserve,
    )
    _log_transfer(
        network=config.network_name(),
        asset=asset.upper(),
        amount=amount,
        destination=destination.strip(),
        tx_hash=tx_hash,
    )
    try:
        bal_xrp = await connector.get_xrp_balance()
        bal_rlusd = await connector.get_rlusd_balance()
    except Exception:
        bal_xrp = 0.0
        bal_rlusd = 0.0
    CSVLogger().log_transfer(
        network=config.network_name(),
        asset=asset.upper(),
        amount=amount,
        destination=destination.strip(),
        tx_hash=tx_hash,
        balance_xrp_after=bal_xrp,
        balance_rlusd_after=bal_rlusd,
    )
    return tx_hash
