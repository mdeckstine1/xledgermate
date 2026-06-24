"""Tests for WS pure production engine helpers."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
    eng.config.dry_run = False
    msg = eng._execution_summary(
        eng.config, 0, cancelled=2, would_sync=0, would_quote=False
    )
    assert "pulled 2" in msg


def test_drawdown_kill_cancels_and_persists_same_cycle(monkeypatch) -> None:
    from config.settings import BotConfig

    class FakeConnector:
        async def get_xrp_balance(self) -> float:
            return 90.0

        async def get_rlusd_balance(self) -> float:
            return 0.0

        async def get_rlusd_trust_line(self):
            return SimpleNamespace(exists=True, limit=1_000.0, no_ripple=False)

    class FakeKillSwitch:
        active = False
        reason = ""

        def is_active(self) -> bool:
            return self.active

        def activate(self, reason: str) -> None:
            self.active = True
            self.reason = reason

    config = BotConfig()
    config.dry_run = False
    config.trading_enabled = True
    config.bot_secret_key = "test-secret"
    config.telegram_enabled = False
    config.ws_drawdown_kill_enabled = True
    config.max_daily_drawdown_percent = 5.0
    monkeypatch.setattr(BotConfig, "load", classmethod(lambda cls, filepath=None: config))

    eng = WsPureTradingEngine(config)
    eng.connector = FakeConnector()
    eng.kill_switch = FakeKillSwitch()
    eng._ws_feed = object()
    eng._adapter = object()
    eng._ensure_ws_stack = AsyncMock()
    eng._refresh_book_state = AsyncMock(
        return_value=(SimpleNamespace(age_seconds=lambda: 0.1), 1.00, 1.10, 1.05)
    )
    eng._cancel_if_live = AsyncMock()
    eng._persist_cycle = AsyncMock()
    eng.drawdown_monitor.daily_start_value = 100.0
    eng.drawdown_monitor.current_value = 100.0

    asyncio.run(eng._run_cycle())

    reason = "Daily portfolio drawdown 10.00%"
    assert eng.kill_switch.active is True
    assert eng.kill_switch.reason == reason
    eng._cancel_if_live.assert_awaited_once_with(eng.connector, config, reason)
    eng._persist_cycle.assert_awaited_once()
    persist_args = eng._persist_cycle.await_args.args
    persist_kwargs = eng._persist_cycle.await_args.kwargs
    assert persist_args[:8] == (config, 1.05, 1.00, 1.10, 90.0, 0.0, 90.0, [])
    assert persist_args[8] == 0
    assert persist_kwargs == {"execution": reason, "engine_dec": None}


def test_sync_offers_keeps_age_tracking_when_cancel_fails() -> None:
    from config.settings import BotConfig
    from datetime import datetime, timedelta, timezone

    class CancelFailsConnector:
        def __init__(self) -> None:
            self.offers = [OpenOffer(sequence=44, side="ask", price=1.20, size_xrp=10.0)]

        async def get_open_offers(self):
            return self.offers

        async def cancel_offer(self, sequence: int) -> None:
            raise RuntimeError("submit timeout")

        async def place_quote(self, intent) -> None:
            raise AssertionError("no placement expected")

    config = BotConfig()
    config.dry_run = False
    config.bot_secret_key = "test-secret"
    eng = WsPureTradingEngine(config)
    eng.connector = CancelFailsConnector()
    placed_at = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    eng._offer_age.record_place("ask", placed_utc=placed_at, sequence=44)

    placed, cancelled = asyncio.run(
        eng._sync_offers([], mid=1.10, best_bid=1.00, best_ask=1.10)
    )

    assert (placed, cancelled) == (0, 0)
    age = eng._offer_age.age_seconds_at(
        "ask",
        sequence=44,
        detected_utc=placed_at + timedelta(seconds=90),
    )
    assert age == 90.0


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
