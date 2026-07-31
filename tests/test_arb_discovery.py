"""Paper arb discovery scoring tests."""

from __future__ import annotations

from experimental.arb.discovery import (
    ACTIONABLE_MIN_FILL_BPS,
    build_discovery_score,
    paper_inventory_fundable,
    update_dwell_and_flags,
)


def test_paper_inventory_fundable():
    ok = paper_inventory_fundable(xrp=1000, rlusd=80, mid=1.06, notional_rlusd=50)
    assert ok["fundable"] is True
    poor = paper_inventory_fundable(xrp=1, rlusd=5, mid=1.06, notional_rlusd=500)
    assert poor["rlusd_ok"] is False


def test_dwell_requires_two_positive_polls(tmp_path):
    state = {"pairs": {}}
    d1 = update_dwell_and_flags(
        pair_id="rlusd_xrp",
        fill_bps_500=5.0,
        mid_net_bps=2.0,
        fundable_500=True,
        state=state,
    )
    assert d1["fill_pos_streak"] == 1
    assert d1["actionable"] is False
    d2 = update_dwell_and_flags(
        pair_id="rlusd_xrp",
        fill_bps_500=4.0,
        mid_net_bps=1.0,
        fundable_500=True,
        state=state,
    )
    assert d2["fill_pos_streak"] == 2
    assert d2["actionable"] is True
    d3 = update_dwell_and_flags(
        pair_id="rlusd_xrp",
        fill_bps_500=-1.0,
        mid_net_bps=-2.0,
        fundable_500=True,
        state=state,
    )
    assert d3["fill_pos_streak"] == 0
    assert d3["actionable"] is False


def test_build_discovery_without_depth(tmp_path):
    path = tmp_path / "arb_discovery_state.json"
    disc = build_discovery_score(
        {"clob_mid_rlusd_per_xrp": 1.06, "net_edge_bps": -5, "dislocation": False},
        xrp=1000,
        rlusd=80,
        state_path=path,
    )
    assert disc["fill_ladder"]["available"] is False
    assert disc["flag"] in ("ok", "MID+", "GROSS")
    assert disc["poll_sleep_seconds"] in (12, 60)
    assert disc["thresholds"]["actionable_min_fill_bps"] == ACTIONABLE_MIN_FILL_BPS
