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
