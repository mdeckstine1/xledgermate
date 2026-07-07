"""Tests for WS pure production engine helpers."""

import asyncio

from config.settings import BotConfig
from connectors.xrpl_connector import TrustLineInfo
from connectors.xrpl_connector import OpenOffer
from engine.order_sync import plan_order_sync
from experimental.ws_feed.offer_age_tracker import OfferAgeTracker
from experimental.ws_feed.stale_quote_guard import stale_quote_sequences_to_cancel
from experimental.ws_feed.ws_pure_engine import (
    WsPureTradingEngine,
    fill_side_to_offer_age_side,
    pure_intents_to_quote_intents,
    resolve_ws_sync_tolerances,
)


def test_plan_order_sync_empty_intents_cancels_all() -> None:
    offers = [
        OpenOffer(sequence=1, side="bid", price=1.1, size_xrp=10.0),
        OpenOffer(sequence=2, side="ask", price=1.11, size_xrp=10.0),
    ]
    plan = plan_order_sync([], offers, best_bid=1.1, best_ask=1.11)
    assert plan.cancel_sequences == [1, 2]
    assert plan.place_intents == []


def test_execution_summary_pull_when_blocked() -> None:
    from config.settings import BotConfig

    eng = WsPureTradingEngine(BotConfig.load())
    msg = eng._execution_summary(
        eng.config, 0, cancelled=2, would_sync=0, would_quote=False
    )
    assert "pulled 2" in msg


def test_pure_intents_active_l1_only() -> None:
    ladder = [
        {"level": 1, "side": "bid", "price": 1.1, "size_xrp": 12.0, "active": True},
        {"level": 1, "side": "ask", "price": 1.11, "size_xrp": 12.0, "active": True},
        {"level": 2, "side": "bid", "price": 1.09, "size_xrp": 8.0, "active": False},
    ]
    intents = pure_intents_to_quote_intents(ladder, would_quote=True)
    assert len(intents) == 2
    assert {i.side for i in intents} == {"bid", "ask"}


def test_pure_intents_empty_when_blocked() -> None:
    ladder = [
        {"level": 1, "side": "bid", "price": 1.1, "size_xrp": 12.0, "active": True},
    ]
    assert pure_intents_to_quote_intents(ladder, would_quote=False) == []


def test_resolve_ws_sync_tolerances_small_mid_move_keeps_queue() -> None:
    """Sub-8 bps mid wiggle should preserve queue (v2.1.22 churn tuning)."""
    tol, preserve = resolve_ws_sync_tolerances(
        mid=1.2758,
        last_sync_mid=1.2750,
        toxic_ratio_30s=0.0,
        recent_fills=0,
        g2_active=False,
        base_price_tolerance_pct=0.08,
    )
    assert preserve is True
    assert tol == 0.08


def test_resolve_ws_sync_tolerances_mid_move_disables_preserve() -> None:
    tol, preserve = resolve_ws_sync_tolerances(
        mid=1.2800,
        last_sync_mid=1.2750,
        toxic_ratio_30s=0.0,
        recent_fills=0,
        g2_active=False,
        base_price_tolerance_pct=0.08,
    )
    assert preserve is False
    assert tol <= 0.03


def test_resolve_ws_sync_tolerances_g2_disables_preserve() -> None:
    tol, preserve = resolve_ws_sync_tolerances(
        mid=1.2750,
        last_sync_mid=1.2750,
        toxic_ratio_30s=0.40,
        recent_fills=5,
        g2_active=True,
        base_price_tolerance_pct=0.08,
    )
    assert preserve is False
    assert tol <= 0.04


def test_resolve_ws_sync_tolerances_calm_keeps_queue() -> None:
    tol, preserve = resolve_ws_sync_tolerances(
        mid=1.2751,
        last_sync_mid=1.2750,
        toxic_ratio_30s=0.10,
        recent_fills=2,
        g2_active=False,
        base_price_tolerance_pct=0.08,
    )
    assert preserve is True
    assert tol == 0.08


def test_resolve_ws_sync_tolerances_solo_low_toxic_preserves_and_looser() -> None:
    # Lever 4 (all-4): solo relax keeps preserve=True + looser tol to reduce flip and let quotes rest.
    tol, preserve = resolve_ws_sync_tolerances(
        mid=1.2751,
        last_sync_mid=1.2750,
        toxic_ratio_30s=0.05,
        recent_fills=5,
        g2_active=False,
        base_price_tolerance_pct=0.06,
        solo_acquisition=True,
        peer_lane_empty=True,
    )
    assert preserve is True
    assert tol >= 0.08


def test_fill_side_to_offer_age_side() -> None:
    assert fill_side_to_offer_age_side("BUY") == "bid"
    assert fill_side_to_offer_age_side("SELL") == "ask"
    assert fill_side_to_offer_age_side("") is None


def test_engine_offer_age_tracker_on_fill() -> None:
    from config.settings import BotConfig
    from datetime import datetime, timedelta, timezone

    eng = WsPureTradingEngine(BotConfig.load())
    placed = datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc)
    eng._offer_age.record_place("bid", placed_utc=placed)
    detected = placed + timedelta(seconds=3.0)
    age = eng._offer_age.effective_quote_age_at_fill_seconds("bid", fill_detected_utc=detected)
    assert age == 3.0


def test_engine_analysis_bundle_starts_empty() -> None:
    from config.settings import BotConfig

    eng = WsPureTradingEngine(BotConfig.load())
    assert eng._analysis_bundle["sample_history"] == []


def test_stale_quote_merged_into_sync_cancel_plan() -> None:
    """Stale sequences cancel even when preserve_touch_queue would keep them."""
    from datetime import datetime, timedelta, timezone

    from core.runtime_state import QuoteIntent

    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    offers = [
        OpenOffer(sequence=1, side="bid", price=1.2750, size_xrp=10.0),
        OpenOffer(sequence=2, side="ask", price=1.2760, size_xrp=10.0),
    ]
    intents = [
        QuoteIntent(level=1, side="bid", price=1.2750, size_xrp=10.0),
        QuoteIntent(level=1, side="ask", price=1.2760, size_xrp=10.0),
    ]
    plan = plan_order_sync(
        intents,
        offers,
        best_bid=1.2750,
        best_ask=1.2760,
        preserve_touch_queue=True,
    )
    assert plan.cancel_sequences == []
    tracker = OfferAgeTracker()
    tracker.record_place("ask", placed_utc=now - timedelta(seconds=127.0), sequence=2)
    stale = stale_quote_sequences_to_cancel(
        offers,
        tracker,
        now=now,
        toxic_ratio_30s=0.0,
        mid=1.2755,
        last_sync_mid=1.2755,
    )
    merged = list(plan.cancel_sequences) + [s for s in stale if s not in plan.cancel_sequences]
    assert merged == [2]


def test_run_cycle_refreshes_balances_after_intel_scrape(monkeypatch) -> None:
    """A fill during the slow intel scrape must affect the quote decision immediately."""
    from experimental.ws_feed import ws_pure_engine as wpe

    class DummyState:
        def best_prices(self) -> tuple[float, float]:
            return 1.099, 1.101

        def age_seconds(self) -> float:
            return 0.0

    class DummyFeed:
        state = DummyState()

        async def refresh_if_stale(self, _stale_after_s: float) -> None:
            return None

    class DummyConnector:
        def __init__(self) -> None:
            self.xrp_balances = [100.0, 90.0]
            self.rlusd_balances = [100.0, 111.0]

        async def get_xrp_balance(self) -> float:
            if len(self.xrp_balances) > 1:
                return self.xrp_balances.pop(0)
            return self.xrp_balances[0]

        async def get_rlusd_balance(self) -> float:
            if len(self.rlusd_balances) > 1:
                return self.rlusd_balances.pop(0)
            return self.rlusd_balances[0]

        async def get_rlusd_trust_line(self) -> TrustLineInfo:
            return TrustLineInfo(exists=True, balance=0.0, limit=1_000.0, no_ripple=True)

        async def get_open_offers(self) -> list[OpenOffer]:
            return []

    class DummyAdapter:
        def __init__(self) -> None:
            self.seen_balances: tuple[float, float] | None = None

        async def compute_pure_as_decision(self, **kwargs):
            self.seen_balances = (kwargs["xrp_bal"], kwargs["rlusd_bal"])
            return {
                "would_quote": False,
                "quote_intents": [],
                "quote_decision_summary": "off",
                "qd_bid_allowed": False,
                "qd_ask_allowed": False,
            }

    config = BotConfig(
        bot_account_address="rTest",
        dry_run=True,
        trading_enabled=True,
        fund_with_xrp_only=False,
        order_sizes=[10.0],
        min_order_size_xrp=1.0,
        xrp_reserve=12.0,
    )
    monkeypatch.setattr(wpe.BotConfig, "load", classmethod(lambda cls: config))

    engine = WsPureTradingEngine(config)
    connector = DummyConnector()
    adapter = DummyAdapter()
    engine.connector = connector
    engine._ws_feed = DummyFeed()
    engine._adapter = adapter
    engine.balance_logger.log_snapshot = lambda **_kwargs: None
    engine._append_decision_file = lambda **_kwargs: None

    async def no_persist(*_args, **_kwargs) -> None:
        return None

    async def cached_intel(_config) -> dict:
        return {"peer_lane_empty": True, "peer_lane_count": 0}

    async def run() -> None:
        engine._persist_cycle = no_persist
        engine._maybe_refresh_competitor_intel = cached_intel
        await engine._run_cycle()

    asyncio.run(run())

    assert adapter.seen_balances == (90.0, 111.0)
