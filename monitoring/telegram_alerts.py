"""Telegram Bot API alerts for XLedgerMate."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


class TelegramAlerts:
    """Send alerts via Telegram Bot API (https://core.telegram.org/bots/api)."""

    def __init__(self, token: str = "", chat_id: str = "", enabled: bool = False) -> None:
        self.token = (token or "").strip()
        self.chat_id = (chat_id or "").strip()
        self.enabled = enabled

    def is_configured(self) -> bool:
        return bool(self.enabled and self.token and self.chat_id)

    def send_message(self, text: str) -> bool:
        if not self.enabled:
            return False
        if not self.token or not self.chat_id:
            logger.warning("Telegram enabled but bot token or chat_id is missing")
            return False
        if httpx is None:
            logger.error("httpx is not installed — cannot send Telegram messages")
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            response = httpx.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
                timeout=20.0,
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                logger.error("Telegram API error: %s", payload.get("description", payload))
                return False
            return True
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            return False

    def send_test(self) -> tuple[bool, str]:
        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        ok = self.send_message(
            f"XLedgerMate test message\n"
            f"Time: {ts}\n"
            f"If you see this, Telegram alerts are wired correctly."
        )
        if ok:
            return True, "Test message sent to Telegram."
        return False, "Failed to send. Check bot token, chat ID, and that you started the bot in Telegram."

    def send_daily_summary(
        self, balance: float, daily_profit: float, drawdown_pct: float
    ) -> bool:
        if not self.enabled:
            return False
        message = (
            f"XLedgerMate daily summary — {datetime.now(tz=timezone.utc).date()}\n"
            f"Balance: {balance:.2f} XRP equiv.\n"
            f"Session P&L estimate: {daily_profit:+.2f} XRP equiv.\n"
            f"Drawdown: {drawdown_pct:.2f}%"
        )
        return self.send_message(message)

    def send_kill_switch_alert(self, drawdown_pct: float, reason: str) -> bool:
        if not self.enabled:
            return False
        message = (
            "XLedgerMate KILL SWITCH ACTIVATED\n"
            f"Drawdown: {drawdown_pct:.2f}%\n"
            f"Reason: {reason}\n"
            "New orders suppressed; open offers cancelled if live trading was on."
        )
        sent = self.send_message(message)
        if sent:
            logger.critical("Kill-switch Telegram alert sent: %s", reason)
        return sent

    def send_cycle_summary(
        self,
        *,
        network: str,
        mid: float,
        cycle: int,
        dry_run: bool,
        placed: int,
        preflight_ok: bool,
    ) -> bool:
        if not self.enabled:
            return False
        mode = "DRY-RUN" if dry_run else "LIVE"
        message = (
            f"XLedgerMate cycle #{cycle} ({network}, {mode})\n"
            f"Mid: {mid:.6f} RLUSD/XRP\n"
            f"Offers placed: {placed}\n"
            f"Preflight: {'OK' if preflight_ok else 'FAIL'}"
        )
        return self.send_message(message)
