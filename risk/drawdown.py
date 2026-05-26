from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class DrawdownMonitor:
    def __init__(self, max_drawdown_percent: float = 3.5):
        self.max_drawdown_percent = max_drawdown_percent
        self.daily_start_balance: Optional[float] = None
        self.daily_start_time = datetime.utcnow()
        self.current_balance: Optional[float] = None

    def update_balance(self, balance: float):
        now = datetime.utcnow()
        if self.daily_start_balance is None or now.date() > self.daily_start_time.date():
            self.daily_start_balance = balance
            self.daily_start_time = now
            logger.info(f"New daily baseline set: {balance:.2f} XRP")
        self.current_balance = balance

    def get_drawdown_percent(self) -> float:
        if self.daily_start_balance is None or self.current_balance is None:
            return 0.0
        loss = self.daily_start_balance - self.current_balance
        return (loss / self.daily_start_balance) * 100

    def is_kill_switch_triggered(self) -> bool:
        drawdown = self.get_drawdown_percent()
        if drawdown >= self.max_drawdown_percent:
            logger.warning(f"🚨 KILL SWITCH TRIGGERED! Drawdown: {drawdown:.2f}% (max: {self.max_drawdown_percent}%)")
            return True
        return False

class KillSwitch:
    def __init__(self):
        self.activated = False

    def activate(self, reason: str = "Drawdown limit exceeded"):
        self.activated = True
        logger.critical(f"🚨 KILL SWITCH ACTIVATED: {reason}")

    def is_active(self) -> bool:
        return self.activated