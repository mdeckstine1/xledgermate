#!/usr/bin/env python3
"""
Compare HTTP poll vs WebSocket book feed without starting the trading engine.

  python -m experimental.ws_feed.run_probe --seconds 90
  python -m experimental.ws_feed.run_probe --http-only --seconds 30
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
from experimental.ws_feed.http_poll_feed import HttpPollBookFeed
from experimental.ws_feed.network_urls import rpc_url_to_websocket_url
from experimental.ws_feed.pair_books import RlusdXrpPair
from experimental.ws_feed.ws_book_feed import WsBookFeed
from utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def _build_connector(config: BotConfig) -> XRPLConnector:
    return XRPLConnector(
        account_address=config.bot_account_address or "rProbeNoAccountXXXXXXXXXXXXXX",
        secret=None,
        rlusd_issuer=config.resolved_rlusd_issuer(),
        rlusd_currency=config.rlusd_currency,
        network=XRPLNetworkConfig(json_rpc_url=config.resolved_rpc_url()),
    )


async def _http_loop(feed: HttpPollBookFeed, seconds: float, interval: float) -> None:
    end = time.monotonic() + seconds
    n = 0
    while time.monotonic() < end:
        book = await feed.fetch_order_book()
        bid, ask, mid = feed.best_and_mid(book)
        n += 1
        logger.info(
            "[HTTP #%s] bid=%.6f ask=%.6f mid=%s latency_ms=%.0f",
            n,
            bid or 0,
            ask or 0,
            f"{mid:.6f}" if mid else "—",
            feed.last_latency_ms,
        )
        await asyncio.sleep(interval)


async def _run_ws_probe(
    config: BotConfig,
    *,
    seconds: float,
    ws_seconds: float,
) -> None:
    connector = _build_connector(config)
    rpc = config.resolved_rpc_url()
    ws_url = rpc_url_to_websocket_url(rpc)
    taker = (config.bot_account_address or "").strip() or "rProbeNoAccountXXXXXXXXXXXXXX"
    pair = RlusdXrpPair(
        rlusd_issuer=config.resolved_rlusd_issuer(),
        rlusd_currency=config.rlusd_currency,
        taker=taker,
    )
    http_feed = HttpPollBookFeed(connector)
    ws_feed = WsBookFeed(connector=connector, ws_url=ws_url, pair=pair)

    logger.info("RPC=%s WS=%s network=%s taker=%s", rpc, ws_url, config.network_name(), taker[:12] + "…")

    t0 = time.monotonic()
    try:
        ws_book = await ws_feed.fetch_order_book_over_ws()
        bid, ask, mid = http_feed.best_and_mid(ws_book)
        logger.info(
            "[WS one-shot BookOffers] bid=%.6f ask=%.6f mid=%s (%.0f ms)",
            bid or 0,
            ask or 0,
            f"{mid:.6f}" if mid else "—",
            (time.monotonic() - t0) * 1000,
        )
    except Exception:
        logger.exception("WS one-shot BookOffers failed")

    http_task = asyncio.create_task(_http_loop(http_feed, seconds=seconds, interval=15.0))
    try:
        state = await ws_feed.run(seconds=ws_seconds, http_refresh_seconds=45.0)
        bid, ask = state.best_prices()
        mid = state.mid()
        logger.info(
            "[WS subscribe end] bid=%.6f ask=%.6f mid=%s msgs=%s age_s=%.1f",
            bid or 0,
            ask or 0,
            f"{mid:.6f}" if mid else "—",
            state.message_count,
            state.age_seconds(),
        )
    except Exception:
        logger.exception("WS subscribe run failed")
    finally:
        http_task.cancel()
        try:
            await http_task
        except asyncio.CancelledError:
            pass


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="HTTP vs WebSocket book probe (sandbox)")
    parser.add_argument("--seconds", type=float, default=90.0, help="Total probe duration")
    parser.add_argument(
        "--ws-seconds",
        type=float,
        default=0.0,
        help="WS subscribe duration (0 = same as --seconds)",
    )
    parser.add_argument(
        "--http-only",
        action="store_true",
        help="Only run HTTP poll loop (no WebSocket)",
    )
    args = parser.parse_args()
    ws_seconds = args.ws_seconds or args.seconds

    config = BotConfig.load()
    if args.http_only:
        connector = _build_connector(config)
        feed = HttpPollBookFeed(connector)
        asyncio.run(_http_loop(feed, seconds=args.seconds, interval=15.0))
        return

    asyncio.run(
        _run_ws_probe(config, seconds=args.seconds, ws_seconds=ws_seconds)
    )


if __name__ == "__main__":
    main()