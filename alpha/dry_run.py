"""Dry-run safety gate — all live ledger mutations must pass through this."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DryRunGuard:
    """Wraps config.dry_run with explicit logging for skipped live actions."""

    dry_run: bool
    network: str

    @property
    def live_trading_allowed(self) -> bool:
        return not self.dry_run

    def require_live(self, action: str) -> bool:
        """
        Return True if the action may proceed on ledger.

        When dry_run is True, logs and returns False (caller must not submit).
        """
        if self.dry_run:
            logger.info(
                "DRY_RUN skip | action=%s | network=%s | no ledger mutation",
                action,
                self.network,
            )
            return False
        return True

    def log_mode_banner(self) -> None:
        mode = "DRY-RUN (paper)" if self.dry_run else "LIVE"
        logger.info("Trading Bot Alpha | mode=%s | network=%s", mode, self.network)
