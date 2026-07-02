import pytest

from config.settings import BotConfig
from utils.risk_capital_sync import (
    build_risk_capital_snapshot,
    risk_capital_mismatch_pct,
    suggest_risk_capital_sync,
)


def test_effective_risk_capital_syncs_portfolio() -> None:
    cfg = BotConfig(risk_capital_xrp=251.0, alpha_risk_capital_sync_portfolio=True)
    assert cfg.effective_risk_capital_xrp(1.09, portfolio_xrp_equiv=593.0) == 593.0
    cfg2 = BotConfig(risk_capital_xrp=800.0, alpha_risk_capital_sync_portfolio=True)
    assert cfg2.effective_risk_capital_xrp(1.09, portfolio_xrp_equiv=593.0) == 800.0


def test_build_risk_capital_snapshot_binding() -> None:
    cfg = BotConfig(
        risk_capital_xrp=251.0,
        alpha_risk_capital_sync_portfolio=True,
        alpha_risk_per_trade_pct=2.0,
        max_leg_size_pct_of_capital=0.12,
    )
    snap = build_risk_capital_snapshot(cfg, portfolio_xrp_equiv=593.0, mid_rlusd_per_xrp=1.09)
    assert snap["effective_xrp"] == 593.0
    assert snap["binding_cap"] == "risk_per_trade_pct"
    assert snap["risk_cap_xrp"] == pytest.approx(11.86, rel=0.01)


def test_mismatch_detected() -> None:
    live, msg = suggest_risk_capital_sync(
        {"portfolio_value_xrp": 250.0},
        configured_xrp=11254.0,
        warn_threshold_pct=15.0,
    )
    assert live == 250.0
    assert msg is not None
    assert risk_capital_mismatch_pct(11254.0, 250.0) > 15.0


def test_aligned_no_suggestion() -> None:
    live, msg = suggest_risk_capital_sync(
        {"portfolio_value_xrp": 246.0},
        configured_xrp=248.0,
        warn_threshold_pct=15.0,
    )
    assert live is None
    assert msg is None
