"""Tests for PureQuotePath (B1 — no profiles)."""

import asyncio

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
            },
        )
        assert d.l1_xrp == 45.5  # min(150, 0.07*650)
        assert d.bid_size > 0
        assert d.ask_size > d.bid_size  # xrp-heavy + low pressure → ask boost
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
    """G4: empty lane neutral; peer lane + fled applies skim side bias."""
    path = PureQuotePath(gamma=0.35, kappa=3.5, configured_l1_xrp=150.0, balance_fraction_k=0.07)

    async def run() -> None:
        empty = await path.compute_decision(
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
        )
        assert empty.g4_grade == "empty_lane"
        assert "G4 neutral" in empty.g4_summary

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
        assert skim.ask_size > empty.ask_size

    asyncio.run(run())
