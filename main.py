#!/usr/bin/env python3
"""
XLedgerMate - XRPL Avellaneda Market Maker Bot
Built for mdeckstine1

Core Rules:
- Main "Mangie" bag is NEVER touched
- Only risk capital in the Bot Account is used
- All profits auto-rollover and compound inside the Bot Account
- Everything runs on pure XRPL
"""

import logging
import asyncio
import sys

from config.settings import BotConfig
from connectors import XRPLConnector, XRPLNetworkConfig
from core import BotPerception, DecisionLog, VERSION, get_profile
from utils.logging_setup import setup_logging
from utils.testnet import is_testnet_mode

from risk.drawdown import DrawdownMonitor, KillSwitch
from risk.inventory import InventorySkew
from strategy.avellaneda_strategy import AvellanedaStrategy
from monitoring.telegram_alerts import TelegramAlerts
from monitoring.csv_logger import CSVLogger

from gui.streamlit_gui import run_gui

setup_logging()
logger = logging.getLogger(__name__)


async def main():
    config = BotConfig.load()

    logger.info("=" * 60)
    logger.info("🚀 XLedgerMate Starting")
    logger.info(f"Version: v{VERSION}")
    logger.info(f"Risk Capital: {config.risk_capital_xrp:,.2f} XRP (Bot Account only)")
    logger.info(f"Auto Rollover: ENABLED — profits compound in Bot Account")
    logger.info(f"Main Mangie bag: 100% ISOLATED and untouched")
    logger.info("=" * 60)

    if is_testnet_mode():
        logger.warning("⚠️  Running in TESTNET mode. Change config.testnet to False when ready for mainnet.")

    # Initialize risk systems
    drawdown_monitor = DrawdownMonitor(max_drawdown_percent=config.max_daily_drawdown_percent)
    kill_switch = KillSwitch()
    inventory_skew = InventorySkew(target_xrp_ratio=config.inventory_target_xrp_ratio)

    # Initialize strategy + perception
    strategy = AvellanedaStrategy(config)
    profile = get_profile(config.active_profile)
    perception = BotPerception(active_profile=profile)
    decision_log = DecisionLog(max_entries=150)

    # Initialize monitoring
    alerts = TelegramAlerts(
        token=config.telegram_token,
        chat_id=config.telegram_chat_id,
        enabled=config.telegram_enabled
    )
    csv_logger = CSVLogger()

    logger.info("✅ All modules loaded successfully")
    logger.info("Use the GUI to adjust settings live: streamlit run gui/streamlit_gui.py")

    # Build live market perception snapshot before GUI launch.
    try:
        connector = XRPLConnector(
            account_address=config.bot_account_address,
            secret=config.bot_secret_key,
            network=XRPLNetworkConfig(json_rpc_url=config.xrpl_testnet_rpc_url),
        )
        await build_perception_snapshot(
            config=config,
            connector=connector,
            strategy=strategy,
            perception=perception,
            decision_log=decision_log,
            drawdown_monitor=drawdown_monitor,
            kill_switch=kill_switch,
        )
    except Exception as exc:
        logger.warning("Skipping XRPL snapshot setup: %s", exc)

    # Launch GUI (current operator control entrypoint).
    run_gui()


async def build_perception_snapshot(
    *,
    config: BotConfig,
    connector: XRPLConnector,
    strategy: AvellanedaStrategy,
    perception: BotPerception,
    decision_log: DecisionLog,
    drawdown_monitor: DrawdownMonitor,
    kill_switch: KillSwitch,
) -> None:
    try:
        balance = connector.get_xrp_balance()
        drawdown_monitor.update_balance(balance)
        if drawdown_monitor.is_kill_switch_triggered():
            kill_switch.activate("Daily drawdown threshold reached")
            decision_log.add("risk", "Kill switch activated due to drawdown.")
            return

        order_book = connector.fetch_xrp_rlusd_order_book()
        liquidity = connector.compute_liquidity_metrics(order_book)
        mid_price = connector.compute_mid_price(order_book)
        volatility_pct = connector.update_and_estimate_volatility_pct(mid_price)
        spread_result = strategy.compute_spreads(
            volatility_pct=volatility_pct,
            liquidity_score=liquidity.liquidity_score,
            profile=perception.active_profile,
        )
        perception.update_market_state(
            mid_price=mid_price or 0.0,
            volatility_pct=volatility_pct,
            liquidity=liquidity,
            effective_spreads_pct=spread_result.effective_spreads_pct,
        )
        decision_log.add("spread", spread_result.reason)
        logger.info(
            "Perception | profile=%s vol=%.2f%% liq=%.2f spreads=%s",
            perception.active_profile.name,
            perception.volatility_pct,
            perception.liquidity.liquidity_score,
            perception.effective_spreads_pct,
        )
    except Exception as exc:
        logger.warning("Perception snapshot unavailable: %s", exc)
        decision_log.add("error", f"Snapshot failed: {exc}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        sys.exit(1)
