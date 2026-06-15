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
from utils.logging_setup import setup_logging
from utils.rpc_health import AMENDMENT_BLOCKED_HINT, rpc_reports_amendment_blocked
from utils.manual_rebalance import run_manual_rebalance_check
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
        choices=[
            "engine",
            "ws-engine",
            "gui",
            "once",
            "cancel-offers",
            "clear-kill",
            "setup-trust",
            "trust-no-ripple",
            "send",
            "rebalance-check",
        ],
        default="engine",
        help=(
            "engine = HTTP poll (legacy); ws-engine = WS + pure A-S v2; "
            "gui, once, cancel-offers, clear-kill, setup-trust, "
            "trust-no-ripple, send, rebalance-check"
        ),
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
    if config.risk_capital_unit_normalized() == "rlusd":
        logger.info(
            "Risk capital: %.2f RLUSD (~%.2f XRP equiv. at save) (Bot Account only)",
            config.risk_capital_rlusd,
            config.risk_capital_xrp,
        )
    else:
        logger.info("Risk capital: %.2f XRP (Bot Account only)", config.risk_capital_xrp)
    logger.info("XRPL network: %s", config.network_name())
    logger.info("XRPL RPC: %s", config.resolved_rpc_url())
    logger.info("Dry run: %s | Trading enabled: %s", config.dry_run, config.trading_enabled)
    logger.info("=" * 60)
    if is_testnet_mode():
        logger.warning("Running on TESTNET. Set testnet: false in config for mainnet.")
    else:
        logger.warning("Running on MAINNET. Real funds at risk on Bot Account.")

    rpc_url = config.resolved_rpc_url()
    blocked = rpc_reports_amendment_blocked(rpc_url)
    if blocked is True:
        logger.error("RPC reports amendment_blocked=true at %s", rpc_url)
        logger.error(AMENDMENT_BLOCKED_HINT)
    elif blocked is False and "xrplcluster.com" in rpc_url:
        logger.warning(
            "xrplcluster.com load-balances nodes; some are outdated and return "
            "amendmentBlocked. Prefer https://s1.ripple.com:51234 in config."
        )


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
        logger.info("RLUSD trust line submitted (No Ripple): %s", tx_hash)
        return
    if mode == "trust-no-ripple":
        cfg = BotConfig.load()
        if not cfg.bot_account_address.strip() or not (cfg.bot_secret_key or "").strip():
            raise ValueError("bot_account_address and bot_secret_key required for trust-no-ripple.")
        connector = XRPLConnector(
            account_address=cfg.bot_account_address.strip(),
            secret=cfg.bot_secret_key,
            rlusd_issuer=cfg.resolved_rlusd_issuer(),
            rlusd_currency=cfg.resolved_rlusd_currency_code(),
            network=XRPLNetworkConfig(json_rpc_url=cfg.resolved_rpc_url()),
        )
        trust = await connector.get_rlusd_trust_line()
        if not trust.exists:
            raise ValueError("No RLUSD trust line — run setup-trust first.")
        if trust.no_ripple:
            logger.info("RLUSD trust line already has rippling disabled (No Ripple).")
            return
        tx_hash = await connector.disable_rlusd_rippling()
        logger.info("RLUSD rippling disabled (No Ripple set): %s", tx_hash)
        return
    if mode == "once":
        await engine._run_cycle()
        logger.info("Single cycle complete.")
        return
    if mode == "rebalance-check":
        summary = await run_manual_rebalance_check(config)
        # Windows consoles may be cp1252; keep output ASCII-safe.
        print(summary.encode("ascii", errors="replace").decode("ascii"))
        return
    if mode == "ws-engine":
        from experimental.ws_feed.ws_pure_engine import WsPureTradingEngine
        from experimental.ws_feed.pure_quote_path import WS_AS_VERSION

        ws_engine = WsPureTradingEngine(config)
        logger.info("WS pure engine path v%s (same config/credentials as legacy engine)", WS_AS_VERSION)
        _register_engine_pid_cleanup()
        try:
            await ws_engine.run()
        except KeyboardInterrupt:
            ws_engine.stop()
            logger.info("WS pure engine stopped by user.")
        finally:
            _clear_engine_pid()
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
            from gui.streamlit_gui import run_gui

            run_gui()
        elif args.mode in {
            "engine",
            "ws-engine",
            "once",
            "cancel-offers",
            "clear-kill",
            "setup-trust",
            "trust-no-ripple",
            "send",
            "rebalance-check",
        }:
            asyncio.run(run_engine_async(config, args.mode, args))
        else:
            raise ValueError(f"Unknown mode: {args.mode}")
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as exc:
        logger.critical("Fatal error: %s", exc)
        sys.exit(1)
