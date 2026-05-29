"""Session P&L helpers — MTM vs balance-only views."""

from risk.drawdown import (
    portfolio_value_xrp,
    session_pnl_balance_delta_xrp,
    session_pnl_mtm_xrp,
)


def test_session_pnl_mtm_reflects_mid_move_with_flat_balances() -> None:
    baseline_port = portfolio_value_xrp(187.0, 63.0, 1.317)
    current_port = portfolio_value_xrp(187.0, 63.0, 1.312)
    pnl = session_pnl_mtm_xrp(
        portfolio_value_xrp=current_port,
        baseline_portfolio_xrp=baseline_port,
    )
    assert pnl > 0
    assert abs(pnl - (current_port - baseline_port)) < 1e-9


def test_session_pnl_balance_ignores_mid_revaluation() -> None:
    pnl = session_pnl_balance_delta_xrp(
        balance_xrp=187.0,
        balance_rlusd=63.0,
        baseline_xrp=187.0,
        baseline_rlusd=63.0,
        mid_rlusd_per_xrp=1.312,
    )
    assert pnl == 0.0


def test_session_pnl_balance_captures_xrp_fee_drag() -> None:
    pnl = session_pnl_balance_delta_xrp(
        balance_xrp=186.9306,
        balance_rlusd=63.07194,
        baseline_xrp=186.930982,
        baseline_rlusd=63.07194,
        mid_rlusd_per_xrp=1.31215,
    )
    assert pnl < 0
    assert abs(pnl - (-0.00038)) < 0.0001
