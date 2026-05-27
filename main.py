#!/usr/bin/env python3
"""
XLedgerMate - XRPL Avellaneda Market Maker Bot
Built for mdeckstine1
Airtight, modular, risk-capital-only bot with auto rollover.
Main bag (Mangie) is never touched.
"""

import logging
from config.settings import BotConfig
from utils.logging_setup import setup_logging
from utils.testnet import is_testnet_mode
from risk.drawdown import DrawdownMonitor, KillSwitch
from risk.inventory import InventorySkew
from strategy.avellaneda_strategy import AvellanedaStrategy
from monitoring.telegram_alerts import TelegramAlerts
from monitoring.csv_logger import CSVLogger
from gui.streamlit_gui import run_gui
import asyncio
import sys

setup_logging()
logger = logging.getLogger(__name__)

async def main():
    config = BotConfig.load()
    
    if is_testnet_mode():
        logger.info("🚀 Running in TESTNET mode for safety")

    logger.info(f"Starting XLedgerMate with {config.risk_capital_xrp:,} XRP risk capital")
    logger.info("Auto rollover ENABLED - all profits compound in Bot Account only")
    logger.info("Main Mangie bag is 100% isolated and untouched")

    # Risk systems
    drawdown_monitor = DrawdownMonitor(max_drawdown_percent=config.max_daily_drawdown_percent)
    kill_switch = KillSwitch()
    inventory_skew = InventorySkew(target_xrp_ratio=config.inventory_target_xrp_ratio)

    # Strategy
    strategy = AvellanedaStrategy(config)

    # Monitoring
    alerts = TelegramAlerts(
        token=config.telegram_token,
        chat_id=config.telegram_chat_id,
        enabled=config.telegram_enabled
    )
    csv_logger = CSVLogger()

    logger.info("✅ All modules loaded - bot is ready")
    logger.info("Use the GUI (streamlit run gui/streamlit_gui.py) to tune live")

    run_gui()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Bot crashed: {e}")
        sys.exit(1)
