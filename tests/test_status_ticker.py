"""Operator status marquee."""

from gui.status_ticker import StatusTickerInput, build_status_ticker_items


def test_mainnet_and_no_offers() -> None:
    items = build_status_ticker_items(
        StatusTickerInput(
            dry_run=False,
            is_testnet=False,
            engine_running=True,
            has_bot_account=True,
            config_network_mismatch=False,
            engine_network="mainnet",
            saved_network="mainnet",
            profile_sync_text="",
            kill_switch_active=False,
            kill_switch_reason="",
            open_offers_count=0,
            offers_at_touch=None,
            quote_visibility_summary="",
            join_touch_active=True,
            pause_bids=False,
            pause_asks=False,
            inventory_mode="market_make",
            cycle_count=5,
            spread_check_failed=False,
            spread_check_error="",
            last_execution_summary="",
        )
    )
    texts = [item.text for item in items]
    assert any("Mainnet live" in t for t in texts)
    assert any("No offers on the ledger" in t for t in texts)


def test_defensive_session_headline() -> None:
    items = build_status_ticker_items(
        StatusTickerInput(
            dry_run=False,
            is_testnet=False,
            engine_running=True,
            has_bot_account=True,
            config_network_mismatch=False,
            engine_network="mainnet",
            saved_network="mainnet",
            profile_sync_text="",
            kill_switch_active=False,
            kill_switch_reason="",
            open_offers_count=2,
            offers_at_touch=True,
            quote_visibility_summary="",
            join_touch_active=True,
            pause_bids=False,
            pause_asks=False,
            inventory_mode="market_make",
            cycle_count=10,
            spread_check_failed=False,
            spread_check_error="",
            session_status="defensive",
            session_headline="Defensive — refresh or touch limited",
            last_execution_summary="",
        )
    )
    assert any("Defensive — refresh or touch limited" in item.text for item in items)


def test_kill_switch_first() -> None:
    items = build_status_ticker_items(
        StatusTickerInput(
            dry_run=False,
            is_testnet=False,
            engine_running=True,
            has_bot_account=True,
            config_network_mismatch=False,
            engine_network="mainnet",
            saved_network="mainnet",
            profile_sync_text="",
            kill_switch_active=True,
            kill_switch_reason="drawdown",
            open_offers_count=0,
            offers_at_touch=None,
            quote_visibility_summary="",
            join_touch_active=None,
            pause_bids=False,
            pause_asks=False,
            inventory_mode="market_make",
            cycle_count=1,
            spread_check_failed=False,
            spread_check_error="",
            last_execution_summary="",
        )
    )
    assert items[0].priority == 0
    assert "Kill switch" in items[0].text
