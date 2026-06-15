#!/usr/bin/env python3
"""
Verify WS book age reporting against live BookState.

Runs the WS feed for N seconds and prints age + message count every second.
Age should climb between book updates and drop when msgs increase.

  python -m experimental.ws_feed.verify_ws_age --seconds 30
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config.settings import BotConfig
from connectors.xrpl_connector import XRPLConnector, XRPLNetworkConfig
from experimental.ws_feed.network_urls import rpc_url_to_websocket_url
from experimental.ws_feed.pair_books import RlusdXrpPair
from experimental.ws_feed.ws_book_feed import WsBookFeed
from utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def _build_connector(config: BotConfig) -> XRPLConnector:
    return XRPLConnector(
        account_address=config.bot_account_address or "rVerifyWsAgeXXXXXXXXXXXXXX",
        secret=None,
        rlusd_issuer=config.resolved_rlusd_issuer(),
        rlusd_currency=config.rlusd_currency,
        network=XRPLNetworkConfig(json_rpc_url=config.resolved_rpc_url()),
    )


async def verify_ws_age(*, seconds: float, ws_refresh_seconds: float) -> int:
    config = BotConfig.load()
    connector = _build_connector(config)
    ws_url = rpc_url_to_websocket_url(config.resolved_rpc_url())
    pair = RlusdXrpPair(
        rlusd_issuer=config.resolved_rlusd_issuer(),
        rlusd_currency=config.rlusd_currency,
        taker=(config.bot_account_address or "").strip() or "rVerifyWsAgeXXXXXXXXXXXXXX",
    )
    feed = WsBookFeed(connector=connector, ws_url=ws_url, pair=pair)
    task = asyncio.create_task(feed.run_forever(http_refresh_seconds=ws_refresh_seconds))

    print(f"WS verify: {ws_url} for {seconds:.0f}s (refresh={ws_refresh_seconds:.0f}s)")
    print("ts\tage_s\tmsgs\tlast_update_utc")
    prev_msgs = -1
    prev_age = -1.0
    issues = 0
    end = time.monotonic() + seconds
    try:
        while time.monotonic() < end:
            snap = feed.freshness_snapshot()
            age = float(snap["ws_book_age_s"])
            msgs = int(snap["ws_message_count"])
            utc = snap.get("ws_book_last_update_utc") or "—"
            print(f"{time.strftime('%H:%M:%S')}\t{age:.2f}\t{msgs}\t{utc}")

            if msgs > prev_msgs and age > prev_age + 2.0 and prev_msgs >= 0:
                issues += 1
                logger.warning(
                    "Age jumped up after new message (prev_age=%.1f age=%.1f msgs %s→%s)",
                    prev_age,
                    age,
                    prev_msgs,
                    msgs,
                )
            prev_msgs = msgs
            prev_age = age
            await asyncio.sleep(1.0)
    finally:
        feed._stop.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    if prev_msgs < 2:
        print("FAIL: fewer than 2 book updates — WS feed may not be connected")
        return 1
    if issues:
        print(f"WARN: {issues} suspicious age/msg transitions (see log)")
    else:
        print("OK: age stream looks consistent (climbs between updates, drops on refresh)")
    return 0 if prev_msgs >= 2 else 1


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Verify WS book age ticks correctly")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--ws-refresh-seconds", type=float, default=20.0)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(verify_ws_age(seconds=args.seconds, ws_refresh_seconds=args.ws_refresh_seconds)))


if __name__ == "__main__":
    main()
