#!/usr/bin/env python3
"""
XLedgerMate - XRPL market-making bot (Bot Account risk capital only).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from config.settings import BotConfig
from core import VERSION
from engine import TradingEngine
from gui.streamlit_gui import run_gui
from utils.logging_setup import setup_logging
from utils.testnet import is_testnet_mode

setup_logging()
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="XLedgerMate XRPL market maker")
    parser.add_argument(
        "--mode",
        choices=["engine", "gui", "once"],
        default="engine",
        help="engine=continuous loop, gui=control panel, once=single market cycle",
    )
    return parser.parse_args()


def log_startup_banner(config: BotConfig) -> None:
    logger.info("=" * 60)
    logger.info("XLedgerMate starting")
    logger.info("Version: v%s", VERSION)
    logger.info("Risk capital: %.2f XRP (Bot Account only)", config.risk_capital_xrp)
    logger.info("XRPL network: %s", config.network_name())
    logger.info("XRPL RPC: %s", config.resolved_rpc_url())
    logger.info("Dry run: %s | Trading enabled: %s", config.dry_run, config.trading_enabled)
    logger.info("=" * 60)
    if is_testnet_mode():
        logger.warning("Running on TESTNET. Set testnet: false in config for mainnet.")
    else:
        logger.warning("Running on MAINNET. Real funds at risk on Bot Account.")


async def main() -> None:
    args = parse_args()
    config = BotConfig.load()
    log_startup_banner(config)

    if args.mode == "gui":
        run_gui()
        return

    engine = TradingEngine(config)
    if args.mode == "once":
        await engine._run_cycle()
        logger.info("Single cycle complete.")
        return

    try:
        await engine.run()
    except KeyboardInterrupt:
        engine.stop()
        logger.info("Trading engine stopped by user.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as exc:
        logger.critical("Fatal error: %s", exc)
        sys.exit(1)
