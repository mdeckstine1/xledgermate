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

    # Initialize strategy
    strategy = AvellanedaStrategy(config)

    # Initialize monitoring
    alerts = TelegramAlerts(
        token=config.telegram_token,
        chat_id=config.telegram_chat_id,
        enabled=config.telegram_enabled
    )
    csv_logger = CSVLogger()

    logger.info("✅ All modules loaded successfully")
    logger.info("Use the GUI to adjust settings live: streamlit run gui/streamlit_gui.py")

    # Launch the GUI (this is the current entry point)
    # In a full production version, this would start the Hummingbot Avellaneda strategy instead
    run_gui()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        sys.exit(1)
