"""Factory for ledger adapters."""

from __future__ import annotations

from typing import Optional

from alpha.dry_run import DryRunGuard
from alpha.ledger.interface import LedgerInterface
from alpha.ledger.xrpl_adapter import XrplLedgerAdapter
from config.settings import BotConfig


def build_ledger(
    config: BotConfig,
    *,
    dry_run_guard: Optional[DryRunGuard] = None,
) -> LedgerInterface:
    guard = dry_run_guard or DryRunGuard(
        dry_run=config.dry_run,
        network=config.network_name(),
    )
    return XrplLedgerAdapter.from_config(config, dry_run_guard=guard)
