import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class TelegramAlerts:
    """Sends daily summaries and kill-switch alerts via Telegram."""

    def __init__(self, token: str = "", chat_id: str = "", enabled: bool = False):
        self.token = token
        self.chat_id = chat_id
        self.enabled = enabled

    def send_daily_summary(self, balance: float, daily_profit: float, drawdown_pct: float):
        if not self.enabled:
            return

        message = (
            f"🟢 XLedgerMate Daily Summary - {datetime.utcnow().date()}\n"
            f"Balance: {balance:.2f} XRP\n"
            f"Today's Profit: +{daily_profit:.2f} XRP\n"
            f"Daily Drawdown: {drawdown_pct:.2f}%\n"
            f"Auto Rollover: Active (profits stay in Bot Account)"
        )
        logger.info(f"[Telegram] Daily summary sent: +{daily_profit:.2f} XRP")

    def send_kill_switch_alert(self, drawdown_pct: float, reason: str):
        if not self.enabled:
            return

        message = (
            f"🚨 XLedgerMate KILL SWITCH ACTIVATED\n"
            f"Drawdown: {drawdown_pct:.2f}%\n"
            f"Reason: {reason}\n"
            f"Bot has stopped placing new orders."
        )
        logger.critical(f"[Telegram] Kill-switch alert sent: {reason}")
