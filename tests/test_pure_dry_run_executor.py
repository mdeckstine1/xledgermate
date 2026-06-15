"""D2 — pure dry-run offer sync tests."""

from experimental.ws_feed.pure_dry_run_executor import PureDryRunExecutor


def _l1_intents(*, active: bool = True) -> list:
    return [
        {"level": 1, "side": "bid", "price": 1.10, "size_xrp": 10.0, "active": active, "planned": not active},
        {"level": 1, "side": "ask", "price": 1.11, "size_xrp": 10.0, "active": active, "planned": not active},
        {"level": 2, "side": "bid", "price": 1.09, "size_xrp": 6.0, "active": False, "planned": True},
    ]


def test_initial_place_two_offers() -> None:
    ex = PureDryRunExecutor()
    diff = ex.sync(_l1_intents(), would_quote=True)
    assert len(diff.to_place) == 2
    assert len(diff.to_cancel) == 0
    assert len(diff.open_offers) == 2
    assert "placed 2" in diff.summary


def test_no_quote_cancels_all() -> None:
    ex = PureDryRunExecutor()
    ex.sync(_l1_intents(), would_quote=True)
    diff = ex.sync(_l1_intents(active=False), would_quote=False)
    assert len(diff.to_cancel) == 2
    assert len(diff.open_offers) == 0


def test_unchanged_when_prices_match() -> None:
    ex = PureDryRunExecutor()
    ex.sync(_l1_intents(), would_quote=True)
    diff = ex.sync(_l1_intents(), would_quote=True)
    assert len(diff.to_place) == 0
    assert len(diff.to_cancel) == 0
    assert len(diff.unchanged) == 2


def test_replace_on_price_change() -> None:
    ex = PureDryRunExecutor()
    ex.sync(_l1_intents(), would_quote=True)
    intents = _l1_intents()
    intents[0]["price"] = 1.1005
    diff = ex.sync(intents, would_quote=True)
    assert len(diff.to_cancel) == 1
    assert len(diff.to_place) == 1
    assert len(diff.unchanged) == 1
