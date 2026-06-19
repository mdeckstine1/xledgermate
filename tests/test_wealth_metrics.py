"""RLUSD-stable wealth metrics for operator HUD."""

from core.wealth_metrics import (
    compute_wealth_metrics,
    enrich_runtime_wealth,
    wealth_rlusd,
)


def test_wealth_rlusd_is_rlusd_plus_xrp_at_mid() -> None:
    assert wealth_rlusd(balance_xrp=100.0, balance_rlusd=50.0, mid_rlusd_per_xrp=1.5) == 200.0


def test_compute_wealth_metrics_session_decomposition() -> None:
    runtime = {
        "mid_price": 1.152,
        "balance_xrp": 188.8,
        "balance_rlusd": 212.0,
        "session_baseline_xrp": 188.0,
        "session_baseline_rlusd": 212.0,
        "session_baseline_mid": 1.15,
        "session_spread_capture_xrp": -0.034,
    }
    m = compute_wealth_metrics(runtime)
    assert m["wealth_rlusd"] == round(212.0 + 188.8 * 1.152, 4)
    assert m["wealth_baseline_rlusd"] == round(212.0 + 188.0 * 1.15, 4)
    assert m["wealth_delta_session_rlusd"] is not None
    assert m["skim_delta_rlusd"] == round(-0.034 * 1.152, 6)
    assert m["spot_delta_rlusd"] == round(188.0 * (1.152 - 1.15), 4)
    assert m["rebalance_delta_rlusd"] is not None
    delta = m["wealth_delta_session_rlusd"]
    skim = m["skim_delta_rlusd"]
    spot = m["spot_delta_rlusd"]
    reb = m["rebalance_delta_rlusd"]
    assert abs(delta - skim - spot - reb) < 0.01


def test_enrich_runtime_wealth_attaches_fields() -> None:
    rt = {
        "mid_price": 1.32,
        "balance_xrp": 150.0,
        "balance_rlusd": 66.0,
        "session_spread_capture_xrp": 0.01,
    }
    out = enrich_runtime_wealth(rt)
    assert out is rt
    assert rt["wealth_rlusd"] == round(66.0 + 150.0 * 1.32, 4)
    assert rt["skim_delta_rlusd"] == round(0.01 * 1.32, 6)
    assert rt["xrp_share_pct"] is not None


def test_wealth_hud_payload_includes_decomposition() -> None:
    from core.wealth_metrics import wealth_hud_payload

    runtime = {
        "mid_price": 1.152,
        "balance_xrp": 188.8,
        "balance_rlusd": 212.0,
        "session_baseline_xrp": 188.0,
        "session_baseline_rlusd": 212.0,
        "session_baseline_mid": 1.15,
        "session_spread_capture_xrp": -0.034,
    }
    payload = wealth_hud_payload(runtime)
    assert payload["spot_delta_rlusd"] is not None
    assert payload["rebalance_delta_rlusd"] is not None
    assert payload["xrp_value_rlusd"] is not None
    assert payload["xrp_share_pct"] is not None
    assert payload["session_baseline_xrp"] == 188.0
