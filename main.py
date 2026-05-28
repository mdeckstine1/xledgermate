#!/usr/bin/env python3
"""
XLedgerMate - XRPL market-making bot (Bot Account risk capital only).
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import logging
import os
import sys
from pathlib import Path

from config.settings import BotConfig
from connectors import XRPLConnector, XRPLNetworkConfig
from core import VERSION
from engine import TradingEngine
from gui.streamlit_gui import run_gui
from utils.logging_setup import setup_logging
from utils.send_funds import send_from_bot_account
from utils.testnet import is_testnet_mode

setup_logging()
logger = logging.getLogger(__name__)

ENGINE_PID_FILE = Path("logs/engine.pid")


def _write_engine_pid() -> None:
    ENGINE_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENGINE_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def _clear_engine_pid() -> None:
    ENGINE_PID_FILE.unlink(missing_ok=True)


def _register_engine_pid_cleanup() -> None:
    _write_engine_pid()
    atexit.register(_clear_engine_pid)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="XLedgerMate XRPL market maker")
    parser.add_argument(
        "--mode",
        choices=["engine", "gui", "once", "cancel-offers", "clear-kill", "setup-trust", "send"],
        default="engine",
        help="engine, gui, once, cancel-offers, clear-kill, setup-trust, send",
    )
    parser.add_argument("--to", dest="send_to", default="", help="Send destination r-address")
    parser.add_argument("--amount", type=float, default=0.0, help="Amount to send")
    parser.add_argument(
        "--asset",
        default="XRP",
        choices=["XRP", "RLUSD", "xrp", "rlusd"],
        help="Asset to send",
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


async def run_engine_async(config: BotConfig, mode: str, args: argparse.Namespace) -> None:
    engine = TradingEngine(config)
    if mode == "send":
        if not args.send_to or args.amount <= 0:
            raise ValueError("Send requires --to r... and --amount > 0")
        tx_hash = await send_from_bot_account(
            destination=args.send_to,
            amount=args.amount,
            asset=args.asset,
        )
        logger.info("Sent %s %s to %s | tx=%s", args.amount, args.asset.upper(), args.send_to, tx_hash)
        return
    if mode == "cancel-offers":
        count = await engine.cancel_all_offers()
        logger.info("Cancelled %s open offer(s).", count)
        return
    if mode == "clear-kill":
        engine.kill_switch.clear("Operator cleared via CLI")
        logger.info("Kill switch cleared.")
        return
    if mode == "setup-trust":
        cfg = BotConfig.load()
        if not cfg.bot_account_address.strip() or not (cfg.bot_secret_key or "").strip():
            raise ValueError("bot_account_address and bot_secret_key required for setup-trust.")
        connector = XRPLConnector(
            account_address=cfg.bot_account_address.strip(),
            secret=cfg.bot_secret_key,
            rlusd_issuer=cfg.resolved_rlusd_issuer(),
            rlusd_currency=cfg.resolved_rlusd_currency_code(),
            network=XRPLNetworkConfig(json_rpc_url=cfg.resolved_rpc_url()),
        )
        tx_hash = await connector.setup_rlusd_trust_line()
        logger.info("RLUSD trust line submitted: %s", tx_hash)
        return
    if mode == "once":
        await engine._run_cycle()
        logger.info("Single cycle complete.")
        return
    _register_engine_pid_cleanup()
    try:
        await engine.run()
    except KeyboardInterrupt:
        engine.stop()
        logger.info("Trading engine stopped by user.")
    finally:
        _clear_engine_pid()


if __name__ == "__main__":
    try:
        args = parse_args()
        config = BotConfig.load()
        log_startup_banner(config)

        if args.mode == "gui":
            run_gui()
        elif args.mode in {
            "engine",
            "once",
            "cancel-offers",
            "clear-kill",
            "setup-trust",
            "send",
        }:
            asyncio.run(run_engine_async(config, args.mode, args))
        else:
            raise ValueError(f"Unknown mode: {args.mode}")
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as exc:
        logger.critical("Fatal error: %s", exc)
        sys.exit(1)
