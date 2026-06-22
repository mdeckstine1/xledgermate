"""Session P&L tracking for Alpha reporting (portfolio MTM in XRP equiv)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from risk.drawdown import portfolio_value_xrp

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path("logs/alpha_session.json")


@dataclass
class SessionPnlState:
    baseline_portfolio_xrp: float
    baseline_utc: str
    last_portfolio_xrp: float = 0.0
    last_updated_utc: str = ""

    @property
    def session_pnl_xrp(self) -> float:
        return self.last_portfolio_xrp - self.baseline_portfolio_xrp


class SessionPnlTracker:
    """Persists session baseline across restarts until operator reset."""

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> SessionPnlState:
        if not self.path.exists():
            return SessionPnlState(baseline_portfolio_xrp=0.0, baseline_utc="")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return SessionPnlState(
                baseline_portfolio_xrp=float(data.get("baseline_portfolio_xrp", 0.0)),
                baseline_utc=str(data.get("baseline_utc", "")),
                last_portfolio_xrp=float(data.get("last_portfolio_xrp", 0.0)),
                last_updated_utc=str(data.get("last_updated_utc", "")),
            )
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return SessionPnlState(baseline_portfolio_xrp=0.0, baseline_utc="")

    def _save(self) -> None:
        payload = {
            "baseline_portfolio_xrp": self._state.baseline_portfolio_xrp,
            "baseline_utc": self._state.baseline_utc,
            "last_portfolio_xrp": self._state.last_portfolio_xrp,
            "last_updated_utc": self._state.last_updated_utc,
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def update(
        self,
        *,
        xrp: float,
        rlusd: float,
        mid_rlusd_per_xrp: Optional[float],
    ) -> float:
        """Update MTM and return session P&L in XRP equiv. Initializes baseline on first valid mid."""
        if mid_rlusd_per_xrp is None or mid_rlusd_per_xrp <= 0:
            return self._state.session_pnl_xrp

        portfolio = portfolio_value_xrp(xrp, rlusd, float(mid_rlusd_per_xrp))
        now = datetime.now(tz=timezone.utc).isoformat()

        if self._state.baseline_portfolio_xrp <= 0:
            self._state.baseline_portfolio_xrp = portfolio
            self._state.baseline_utc = now
            logger.info("alpha_session_baseline | portfolio_xrp=%.4f", portfolio)

        self._state.last_portfolio_xrp = portfolio
        self._state.last_updated_utc = now
        self._save()
        pnl = self._state.session_pnl_xrp
        logger.info("alpha_session_pnl | pnl_xrp=%+.4f | portfolio=%.4f", pnl, portfolio)
        return pnl

    def reset_baseline(self, portfolio_xrp: Optional[float] = None) -> None:
        baseline = portfolio_xrp if portfolio_xrp is not None else self._state.last_portfolio_xrp
        if baseline <= 0:
            return
        self._state.baseline_portfolio_xrp = baseline
        self._state.baseline_utc = datetime.now(tz=timezone.utc).isoformat()
        self._save()
        logger.info("alpha_session_reset | baseline=%.4f", baseline)
