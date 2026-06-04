from utils.risk_capital_sync import risk_capital_mismatch_pct, suggest_risk_capital_sync


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
