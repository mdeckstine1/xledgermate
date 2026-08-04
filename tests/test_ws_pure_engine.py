"""Tests for WS pure production engine helpers."""

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


def test_engine_restores_session_capture_brake_after_restart(tmp_path, monkeypatch) -> None:
    from datetime import datetime, timezone

    from config.settings import BotConfig
    from core.runtime_state import RuntimeState, RuntimeStateStore
    from experimental.ws_feed.quote_decision.adapter import compute_quoting_decision

    monkeypatch.chdir(tmp_path)
    boot = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    recent_fill = {
        "kind": "fill",
        "ts_utc": boot,
        "side": "BUY",
        "xrp_amount": 100.0,
        "capture_xrp": -0.02,
        "quote_age_seconds": 4.5,
    }
    RuntimeStateStore().save(
        RuntimeState(
            active_profile="ws_pure",
            as_mode="pure",
            session_boot_utc=boot,
            session_baseline_xrp=180.0,
            session_baseline_rlusd=200.0,
            session_baseline_mid=1.0,
            fills_session=7,
            session_spread_capture_xrp=-0.02,
            recent_fill_quote_ages=[recent_fill],
            acquisition_metrics={
                "inventory_growth_at_edge": {"buy_capture_xrp": -0.02},
                "sell_capture_by_state": {"balanced": {"cap": 0.01}},
            },
        )
    )

    eng = WsPureTradingEngine(BotConfig())

    assert eng._session_boot_utc == boot
    assert eng._session_fills == 7
    assert eng._session_fill_records == [recent_fill]
    assert eng._last_fill_quote_age_seconds == 4.5
    assert eng._last_session_buy_capture_xrp == -0.02
    assert eng._last_session_sell_capture_xrp == 0.01

    qd = compute_quoting_decision(
        mid=1.0,
        best_bid=0.999,
        best_ask=1.001,
        l1_bid_price=0.999,
        l1_ask_price=1.001,
        xrp_balance=500.0,
        rlusd_balance=500.0,
        target_xrp_ratio=0.5,
        inventory_label="balanced",
        peer_lane_empty=False,
        peer_lane_count=3,
        session_buy_capture_xrp=eng._last_session_buy_capture_xrp,
        session_sell_capture_xrp=eng._last_session_sell_capture_xrp,
        recent_fills=tuple(eng._session_fill_records),
    )
    assert qd.bid.allowed is False
    assert qd.bid.block_reason == "session_buy_cap=-0.0200"
    assert qd.ask.allowed is True


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
