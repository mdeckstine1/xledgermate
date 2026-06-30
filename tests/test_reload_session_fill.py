"""Reload session fill tracking on funding-sell fills."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from alpha.dry_run import DryRunGuard
from alpha.decision.reload_regime import ReloadSessionTracker
from alpha.orders.manager import OrderManager
from alpha.orders.strength_sells import StrengthSellRecord
from config.settings import BotConfig


def test_reload_funding_fill_updates_session(tmp_path: Path) -> None:
    session = ReloadSessionTracker(path=tmp_path / "reload_session.json")
    guard = DryRunGuard(dry_run=True, network="mainnet")
    orders = OrderManager(object(), guard, BotConfig(dry_run=True), state_dir=tmp_path)
    orders.set_reload_session(session)
    orders._strength_sells.register(
        StrengthSellRecord(
            sequence=99,
            size_xrp=10.0,
            price_rlusd_per_xrp=1.0,
            purpose="reload_funding",
        )
    )

    asyncio.run(orders._reconcile_strength_sell_fills({}))

    assert session._state.get("rlusd_filled_xrp_equiv", 0.0) == pytest.approx(10.0)


def test_register_strength_sell_reload_purpose(tmp_path: Path) -> None:
    guard = DryRunGuard(dry_run=True, network="mainnet")
    orders = OrderManager(object(), guard, BotConfig(dry_run=True), state_dir=tmp_path)
    orders.register_strength_sell(
        sequence=7,
        size_xrp=5.0,
        price_rlusd_per_xrp=1.1,
        purpose="reload_funding",
    )
    rec = orders._strength_sells.get(7)
    assert rec is not None
    assert rec.purpose == "reload_funding"
