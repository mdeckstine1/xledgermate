"""Send funds from the Bot Account to another XRPL address."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config.settings import BotConfig
from connectors import XRPLConnector, XRPLNetworkConfig
from monitoring.csv_logger import CSVLogger

DEST_TAG_MAX = 0xFFFFFFFF
DEST_TAG_HELP = (
    "Destination tag / memo tag must be a whole number from 0 to 4294967295. "
    "Exchanges show this as Memo, Memo Tag, or Destination Tag on the deposit screen."
)


def parse_destination_tag(value: Any) -> Optional[int]:
    """Parse an XRPL DestinationTag (exchange memo tag). Empty → None. 0 is valid."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(DEST_TAG_HELP)
    if isinstance(value, int):
        tag = value
    else:
        raw = str(value).strip().replace(",", "").replace(" ", "")
        if not raw:
            return None
        if not raw.isdigit():
            raise ValueError(DEST_TAG_HELP)
        tag = int(raw)
    if tag < 0 or tag > DEST_TAG_MAX:
        raise ValueError(DEST_TAG_HELP)
    return tag


def parse_memo_text(value: Any, *, max_len: int = 1024) -> Optional[str]:
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    if len(text) > max_len:
        raise ValueError(f"Memo text is too long (max {max_len} characters).")
    return text


def _log_transfer(
    *,
    network: str,
    asset: str,
    amount: float,
    destination: str,
    tx_hash: str,
    destination_tag: Optional[int] = None,
) -> None:
    path = Path("logs/transfers.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if write_header:
            writer.writerow(
                [
                    "timestamp_utc",
                    "network",
                    "asset",
                    "amount",
                    "destination",
                    "tx_hash",
                    "destination_tag",
                ]
            )
        writer.writerow(
            [
                datetime.now(tz=timezone.utc).isoformat(),
                network,
                asset,
                f"{amount:.6f}",
                destination,
                tx_hash,
                "" if destination_tag is None else str(destination_tag),
            ]
        )


async def send_from_bot_account(
    *,
    destination: str,
    amount: float,
    asset: str = "XRP",
    destination_tag: Any = None,
    memo: Any = None,
) -> str:
    config = BotConfig.load()
    if not config.bot_account_address.strip():
        raise ValueError("bot_account_address is not configured.")
    if not (config.bot_secret_key or "").strip():
        raise ValueError("bot_secret_key is required to send funds.")

    tag = parse_destination_tag(destination_tag)
    memo_text = parse_memo_text(memo)

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
        destination_tag=tag,
        memo=memo_text,
    )
    dest = destination.strip()
    _log_transfer(
        network=config.network_name(),
        asset=asset.upper(),
        amount=amount,
        destination=dest,
        tx_hash=tx_hash,
        destination_tag=tag,
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
        destination=dest,
        tx_hash=tx_hash,
        balance_xrp_after=bal_xrp,
        balance_rlusd_after=bal_rlusd,
        destination_tag=tag,
        memo=memo_text,
    )
    return tx_hash
