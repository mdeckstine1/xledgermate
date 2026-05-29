from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def portfolio_value_xrp(xrp_balance: float, rlusd_balance: float, mid_rlusd_per_xrp: float) -> float:
    """Total book value expressed in XRP (RLUSD converted at mid)."""
    if mid_rlusd_per_xrp <= 0:
        return xrp_balance
    return xrp_balance + (rlusd_balance / mid_rlusd_per_xrp)


def session_pnl_balance_delta_xrp(
    *,
    balance_xrp: float,
    balance_rlusd: float,
    baseline_xrp: float,
    baseline_rlusd: float,
    mid_rlusd_per_xrp: float,
) -> float:
    """P&L from wallet balance changes only, both legs marked at the current mid."""
    if mid_rlusd_per_xrp <= 0:
        return balance_xrp - baseline_xrp
    current = portfolio_value_xrp(balance_xrp, balance_rlusd, mid_rlusd_per_xrp)
    baseline = portfolio_value_xrp(baseline_xrp, baseline_rlusd, mid_rlusd_per_xrp)
    return current - baseline


def session_pnl_mtm_xrp(*, portfolio_value_xrp: float, baseline_portfolio_xrp: float) -> float:
    """Mark-to-market P&L since session start (aligned with cycle log portfolio)."""
    return portfolio_value_xrp - baseline_portfolio_xrp


class DrawdownMonitor:
    """Daily drawdown on portfolio value (XRP + RLUSD at mid)."""

    def __init__(self, max_drawdown_percent: float = 3.5):
        self.max_drawdown_percent = max_drawdown_percent
        self.daily_start_value: Optional[float] = None
        self.daily_start_time = datetime.utcnow()
        self.current_value: Optional[float] = None

    def update_portfolio(self, xrp_balance: float, rlusd_balance: float, mid_rlusd_per_xrp: float) -> float:
        value = portfolio_value_xrp(xrp_balance, rlusd_balance, mid_rlusd_per_xrp)
        now = datetime.utcnow()
        if self.daily_start_value is None or now.date() > self.daily_start_time.date():
            self.daily_start_value = value
            self.daily_start_time = now
            logger.info("New daily portfolio baseline: %.4f XRP equiv.", value)
        self.current_value = value
        return value

    def reset_baseline(self, value: Optional[float] = None) -> None:
        """Operator cleared kill switch — restart drawdown from current portfolio."""
        baseline = value if value is not None else self.current_value
        if baseline is None:
            return
        self.daily_start_value = baseline
        self.daily_start_time = datetime.utcnow()
        logger.info("Drawdown baseline reset: %.4f XRP equiv.", baseline)

    def get_drawdown_percent(self) -> float:
        if self.daily_start_value is None or self.current_value is None:
            return 0.0
        if self.daily_start_value <= 0:
            return 0.0
        loss = self.daily_start_value - self.current_value
        return max(0.0, (loss / self.daily_start_value) * 100)

    def is_kill_switch_triggered(self) -> bool:
        drawdown = self.get_drawdown_percent()
        if drawdown >= self.max_drawdown_percent:
            logger.warning(
                "Drawdown kill threshold: %.2f%% (max %.2f%%)",
                drawdown,
                self.max_drawdown_percent,
            )
            return True
        return False
