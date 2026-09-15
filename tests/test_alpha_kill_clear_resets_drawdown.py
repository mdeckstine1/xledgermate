"""Clearing the Alpha kill switch must restart the daily drawdown mark."""

from __future__ import annotations

from pathlib import Path

import pytest

from alpha.risk.engine import RiskEngine
from alpha.types import BalanceSnapshot, TrustLineSnapshot
from config.settings import BotConfig
from risk.kill_switch import DRAWDOWN_RESET_FLAG, KillSwitch


def _trust() -> TrustLineSnapshot:
    return TrustLineSnapshot(exists=True, balance=0.0, limit=1_000_000.0)


def test_clear_kill_writes_drawdown_reset_flag(tmp_path: Path) -> None:
    kill = KillSwitch(path=tmp_path / "kill_switch.json")
    kill.activate("drawdown 11.18% >= limit 10.00%")
    assert kill.is_active()
    kill.clear("Operator cleared via HUD")
    assert not kill.is_active()
    assert (tmp_path / DRAWDOWN_RESET_FLAG).is_file()


def test_risk_engine_does_not_retrip_after_clear(tmp_path: Path) -> None:
    cfg = BotConfig(
        bot_account_address="rTestAccount123456789012345678901234",
        max_daily_drawdown_percent=10.0,
        trading_enabled=True,
        dry_run=True,
    )
    engine = RiskEngine(cfg, state_dir=tmp_path)
    start = BalanceSnapshot(xrp=1000.0, rlusd=0.0, mid_rlusd_per_xrp=1.0, portfolio_xrp_equiv=1000.0)
    dumped = BalanceSnapshot(xrp=880.0, rlusd=0.0, mid_rlusd_per_xrp=1.0, portfolio_xrp_equiv=880.0)

    snap = engine.evaluate(balances=start, trust_line=_trust())
    assert snap.kill_switch_active is False
    snap = engine.evaluate(balances=dumped, trust_line=_trust())
    assert snap.kill_switch_active is True
    assert "drawdown" in snap.kill_switch_reason

    KillSwitch(path=tmp_path / "kill_switch.json").clear("Operator cleared via HUD")
    snap = engine.evaluate(balances=dumped, trust_line=_trust())
    assert snap.kill_switch_active is False
    assert snap.drawdown_pct < 1.0
    assert not (tmp_path / DRAWDOWN_RESET_FLAG).exists()


def test_eleven_percent_mtm_does_not_kill_at_25pct_limit(tmp_path: Path) -> None:
    cfg = BotConfig(
        bot_account_address="rTestAccount123456789012345678901234",
        max_daily_drawdown_percent=25.0,
        trading_enabled=True,
        dry_run=True,
    )
    engine = RiskEngine(cfg, state_dir=tmp_path)
    start = BalanceSnapshot(xrp=1000.0, rlusd=0.0, mid_rlusd_per_xrp=1.0, portfolio_xrp_equiv=1000.0)
    dumped = BalanceSnapshot(xrp=888.0, rlusd=0.0, mid_rlusd_per_xrp=1.0, portfolio_xrp_equiv=888.0)
    engine.evaluate(balances=start, trust_line=_trust())
    snap = engine.evaluate(balances=dumped, trust_line=_trust())
    assert snap.kill_switch_active is False
    assert snap.drawdown_pct == pytest.approx(11.2, abs=0.1)
