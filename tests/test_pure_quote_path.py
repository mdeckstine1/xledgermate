"""Tests for PureQuotePath (B1 — no profiles)."""

import asyncio

from experimental.ws_feed.execution_envelope import JOIN_BACKOFF_BPS, PASSIVE_BACKOFF_BPS
from experimental.ws_feed.pure_quote_path import PureQuotePath, WS_AS_VERSION, book_scaled_volatility_pct


def test_pure_quote_inside_l1() -> None:
    path = PureQuotePath(gamma=0.35, kappa=3.5)

    async def run() -> None:
        d = await path.compute_decision(
            mid=1.10,
            best_bid=1.099,
            best_ask=1.101,
            xrp_bal=138.0,
            rlusd_bal=124.0,
        )
        assert d.path_version == WS_AS_VERSION
        assert "PURE A-S" in d.quote_decision_summary
        assert "tight_spread" not in d.quote_decision_summary.lower()
        assert "market_edge_met=false" not in d.quote_decision_summary.lower()

    asyncio.run(run())


def test_book_scaled_vol_not_05_floor() -> None:
    assert book_scaled_volatility_pct(0.125) < 0.2
    assert book_scaled_volatility_pct(0.125) > 0.05


def test_live_book_params_can_quote() -> None:
    """Regression: session book (~0.125% spread) must not 0-quote from vol floor alone."""
    path = PureQuotePath(gamma=0.35, kappa=3.5)

    async def run() -> None:
        d = await path.compute_decision(
            mid=1.120508,
            best_bid=1.1198083175159341,
            best_ask=1.1212070418817652,
            xrp_bal=138.0,
            rlusd_bal=124.0,
        )
        assert d.volatility_pct < 0.2
        assert d.would_quote is True
        assert d.zero_quote_reason == "quoted"

    asyncio.run(run())


def test_b2_dynamic_sizing_on_quote() -> None:
    path = PureQuotePath(gamma=0.35, kappa=3.5, configured_l1_xrp=150.0, balance_fraction_k=0.07)

    async def run() -> None:
        d = await path.compute_decision(
            mid=1.120508,
            best_bid=1.1198083175159341,
            best_ask=1.1212070418817652,
            xrp_bal=650.0,
            rlusd_bal=500.0,
            competitor_intel={
                "competitor_pressure": 0.2,
                "competitor_observed_spread_pct": 0.11,
                "peer_lane_count": 2,
                "peer_pressure_score": 0.2,
            },
        )
        assert d.l1_xrp == 45.5  # min(150, 0.07*650)
        assert d.ask_size > 0
        assert d.ask_size > d.bid_size  # reservation blocks bid; ask boosted on xrp-heavy
        assert "SIZE L1=" in d.quote_decision_summary
        assert "ask-boost" in d.size_rationale
        assert len(d.quote_intents) == 6
        assert any(i["level"] == 3 for i in d.quote_intents)

    asyncio.run(run())


def test_b3_stale_book_raises_effective_vol() -> None:
    path = PureQuotePath(gamma=0.35, kappa=3.5)

    async def run() -> None:
        kwargs = dict(
            mid=1.120508,
            best_bid=1.1198083175159341,
            best_ask=1.1212070418817652,
            xrp_bal=138.0,
            rlusd_bal=124.0,
        )
        fresh = await path.compute_decision(**kwargs, ws_book_age_s=1.0)
        stale = await path.compute_decision(**kwargs, ws_book_age_s=30.0)
        assert "BOOK_AGE" in stale.book_age_rationale
        assert stale.volatility_pct > fresh.volatility_pct
        assert "BOOK_AGE" in stale.quote_decision_summary

    asyncio.run(run())


def test_b4_tight_book_note_when_quoting() -> None:
    path = PureQuotePath(gamma=0.35, kappa=3.5)

    async def run() -> None:
        d = await path.compute_decision(
            mid=1.113765,
            best_bid=1.112930,
            best_ask=1.1146,
            xrp_bal=138.0,
            rlusd_bal=124.0,
            ws_book_age_s=30.0,
            competitor_intel={"competitor_pressure": 0.6},
        )
        assert d.would_quote is True
        assert d.as_optimal_spread_pct > d.book_spread_pct
        assert "TIGHT OK" in (d.tight_book_note or d.quote_decision_summary)

    asyncio.run(run())


def test_zero_quote_reason_in_summary() -> None:
    path = PureQuotePath(gamma=0.35, kappa=3.5)

    async def run() -> None:
        d = await path.compute_decision(
            mid=1.1215,
            best_bid=1.12088,
            best_ask=1.12215,
            xrp_bal=138.0,
            rlusd_bal=124.0,
        )
        if not d.would_quote:
            assert "0 quotes:" in d.quote_decision_summary
            assert d.zero_quote_reason in d.quote_decision_summary

    asyncio.run(run())


def test_g4_peer_lane_in_quote_path() -> None:
    """G4: empty lane solo_acquire; v2.2 QD solo accumulate on buy edge."""
    path = PureQuotePath(gamma=0.35, kappa=3.5, configured_l1_xrp=150.0, balance_fraction_k=0.07)

    async def run() -> None:
        balanced_empty = await path.compute_decision(
            mid=1.10,
            best_bid=1.099,
            best_ask=1.101,
            xrp_bal=500.0,
            rlusd_bal=550.0,
            competitor_intel={
                "competitor_pressure": 0.85,
                "peer_lane_count": 0,
                "peer_lane_empty": True,
            },
        )
        assert balanced_empty.g4_grade == "solo_acquire"
        assert balanced_empty.g7_solo_acquisition is True
        assert balanced_empty.qd_intent == "solo_accumulate_on_edge"
        assert balanced_empty.qd_bid_allowed is True
        assert balanced_empty.qd_ask_allowed is False
        assert balanced_empty.qd_bid_allowed is True
        assert balanced_empty.qd_ask_allowed is False
        assert balanced_empty.suggested_ask is None
        assert balanced_empty.suggested_bid is not None

        xrp_empty = await path.compute_decision(
            mid=1.120508,
            best_bid=1.1198083175159341,
            best_ask=1.1212070418817652,
            xrp_bal=650.0,
            rlusd_bal=500.0,
            competitor_intel={
                "competitor_pressure": 0.85,
                "peer_lane_count": 0,
                "peer_lane_empty": True,
            },
            inventory_max_deviation=0.12,
        )
        assert xrp_empty.g4_grade == "solo_acquire"
        assert xrp_empty.qd_bid_allowed is True
        assert xrp_empty.qd_ask_allowed is False
        assert xrp_empty.would_quote is True

        skim = await path.compute_decision(
            mid=1.120508,
            best_bid=1.1198083175159341,
            best_ask=1.1212070418817652,
            xrp_bal=650.0,
            rlusd_bal=500.0,
            competitor_intel={
                "peer_lane_count": 2,
                "peer_pressure_score": 0.2,
                "peer_observed_spread_pct": 0.11,
                "peer_fled_touch_count": 2,
            },
        )
        assert skim.g4_grade == "skim"
        assert skim.g4_active is True
        assert skim.g4_ask_size_mult > 1.0
        assert skim.ask_size > xrp_empty.ask_size

    asyncio.run(run())


def test_xrp_heavy_solo_qd_allowed_but_cap_zero_does_not_quote() -> None:
    """QD may allow the edge bid, but the executable ladder must honor size caps."""
    path = PureQuotePath(gamma=0.35, kappa=3.5, configured_l1_xrp=150.0)

    async def run() -> None:
        d = await path.compute_decision(
            mid=1.10,
            best_bid=1.099,
            best_ask=1.101,
            xrp_bal=200.0,
            rlusd_bal=80.0,
            target_ratio=0.55,
            inventory_max_deviation=0.12,
            competitor_intel={"peer_lane_empty": True, "peer_lane_count": 0},
        )
        assert d.qd_bid_allowed is True
        assert d.qd_ask_allowed is False
        assert d.bid_size == 0.0
        assert d.suggested_bid is None
        assert d.would_quote is False
        assert not [i for i in d.quote_intents if i.get("active")]

    asyncio.run(run())


def test_g7_xrp_heavy_ask_tighter_touch() -> None:
    path = PureQuotePath(gamma=0.35, kappa=3.5)

    async def run() -> None:
        d = await path.compute_decision(
            mid=1.10,
            best_bid=1.099,
            best_ask=1.101,
            xrp_bal=200.0,
            rlusd_bal=80.0,
            target_ratio=0.55,
        )
        assert d.ask_touch_backoff_bps == JOIN_BACKOFF_BPS
        assert d.bid_touch_backoff_bps == PASSIVE_BACKOFF_BPS
        assert d.g7_summary.startswith("G7 xrp_heavy")
        assert d.g7_ask_role == "join"
        assert d.g7_bid_role == "passive"
        assert "join" in d.g7_scaler_label
        assert d.g2_scaler_label
        assert "G7" in d.execution_brakes_summary
        assert d.suggested_ask is None  # v2.2 QD solo accumulate — bid only
        assert d.qd_bid_allowed is True
        assert d.bid_size == 0.0
        assert d.suggested_bid is None

    asyncio.run(run())
