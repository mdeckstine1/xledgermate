"""Risk aggregation — kill switch, drawdown, edge validation, session P&L."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from alpha.risk.session import SessionPnlTracker
from alpha.types import BalanceSnapshot, RiskSnapshot, TrustLineSnapshot
from config.settings import BotConfig
from risk.drawdown import DrawdownMonitor
from risk.kill_switch import KillSwitch
from utils.preflight import evaluate_preflight

logger = logging.getLogger(__name__)

_DEFAULT_STATE_DIR = Path("logs")


class RiskEngine:
    """Wraps existing risk modules; validates entries and persists kill on drawdown."""

    def __init__(
        self,
        config: BotConfig,
        *,
        state_dir: Path | None = None,
    ) -> None:
        self._config = config
        state_dir = state_dir or _DEFAULT_STATE_DIR
        state_dir.mkdir(parents=True, exist_ok=True)
        self._kill = KillSwitch(path=state_dir / "kill_switch.json")
        self._drawdown = DrawdownMonitor(
            max_drawdown_percent=config.max_daily_drawdown_percent,
        )
        self._session = SessionPnlTracker(path=state_dir / "alpha_session.json")

    @property
    def kill_switch(self) -> KillSwitch:
        return self._kill

    def evaluate(
        self,
        *,
        balances: BalanceSnapshot,
        trust_line: TrustLineSnapshot,
    ) -> RiskSnapshot:
        kill_active = self._kill.is_active()
        kill_reason = self._kill.reason if kill_active else ""
        mid = balances.mid_rlusd_per_xrp
        alerts: List[str] = []

        self._drawdown.update_portfolio(
            balances.xrp,
            balances.rlusd,
            mid,
        )
        drawdown_pct = self._drawdown.get_drawdown_percent()

        if self._drawdown.is_kill_switch_triggered() and not kill_active:
            kill_reason = (
                f"drawdown {drawdown_pct:.2f}% >= limit "
                f"{self._config.max_daily_drawdown_percent:.2f}%"
            )
            self._kill.activate(kill_reason)
            kill_active = True
            alerts.append(kill_reason)

        session_pnl = self._session.update(
            xrp=balances.xrp,
            rlusd=balances.rlusd,
            mid_rlusd_per_xrp=mid,
        )

        preflight = evaluate_preflight(
            config=self._config,
            xrp_balance=balances.xrp,
            rlusd_balance=balances.rlusd,
            trust_line_limit=trust_line.limit if trust_line.exists else None,
            has_trust_line=trust_line.exists,
            trust_line_no_ripple=trust_line.no_ripple if trust_line.exists else None,
            mid_price=mid,
            kill_switch_active=kill_active,
        )

        if preflight.warnings:
            alerts.extend(preflight.warnings[:3])
        if kill_active:
            alerts.insert(0, f"KILL SWITCH: {kill_reason or 'active'}")

        trading_allowed = (
            not kill_active
            and preflight.ready
            and self._config.trading_enabled
        )

        snap = RiskSnapshot(
            kill_switch_active=kill_active,
            kill_switch_reason=kill_reason or "",
            drawdown_pct=drawdown_pct,
            max_drawdown_pct=self._config.max_daily_drawdown_percent,
            preflight_ready=preflight.ready,
            preflight_summary=preflight.summary(),
            preflight_errors=list(preflight.errors),
            preflight_warnings=list(preflight.warnings),
            session_pnl_xrp=session_pnl,
            trading_allowed=trading_allowed,
            edge_validation_required=True,
            alerts=alerts,
        )
        logger.info(
            "risk_snapshot | kill=%s | drawdown=%.2f%% | session_pnl=%+.4f | trading_allowed=%s",
            kill_active,
            drawdown_pct,
            session_pnl,
            trading_allowed,
        )
        return snap

    def validate_edge(self, edge_pct: Optional[float]) -> tuple[bool, str]:
        """Return whether edge meets configured minimum for entry."""
        if not self._config.trading_enabled:
            return False, "trading_disabled"
        min_edge = self._config.alpha_min_edge_threshold_pct
        if edge_pct is None:
            return False, "edge_unknown"
        if edge_pct < min_edge:
            return False, f"edge {edge_pct:.3f}% < min {min_edge:.3f}%"
        return True, "edge_ok"

    def validate_entry(
        self,
        risk: RiskSnapshot,
        *,
        edge_pct: Optional[float] = None,
    ) -> tuple[bool, str]:
        """Gate before any new order placement."""
        if risk.kill_switch_active:
            return False, f"kill_switch: {risk.kill_switch_reason or 'active'}"
        if not risk.preflight_ready:
            return False, "preflight_not_ready"
        if not risk.trading_allowed:
            return False, "trading_not_allowed"
        if edge_pct is not None and risk.edge_validation_required:
            ok, msg = self.validate_edge(edge_pct)
            if not ok:
                return False, msg
        return True, "ok"

    def validate_bracket_placement(self, risk: RiskSnapshot) -> tuple[bool, str]:
        """Gate before placing TP/SL legs after a fill."""
        if risk.kill_switch_active:
            return False, "kill_switch_active"
        if not risk.preflight_ready:
            return False, "preflight_not_ready"
        return True, "ok"
