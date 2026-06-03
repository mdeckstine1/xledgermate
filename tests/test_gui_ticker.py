"""Marquee ticker feed builder."""

from gui.ticker import TickerItem, build_ticker_items, format_ticker_track_html


def test_build_ticker_splits_quote_decision_summary() -> None:
    runtime = {
        "quote_decision_summary": (
            "safe: favorable → tighter; inventory xrp_heavy (72%) → steer; "
            "operating mode: market make"
        ),
        "kill_switch_active": False,
        "pause_bids": True,
        "pause_asks": False,
    }
    items = build_ticker_items(runtime, engine_running=True)
    texts = [item.text for item in items]
    assert any("Quoting: bids paused" in t for t in texts)
    assert any("operating mode: market make" in t for t in texts)
    assert any(item.kind == "warn" for item in items)


def test_kill_switch_first_priority() -> None:
    items = build_ticker_items(
        {"kill_switch_active": True, "kill_switch_reason": "drawdown"},
        engine_running=True,
    )
    assert items[0].priority == 0
    assert "Kill switch" in items[0].text


def test_format_ticker_escapes_html() -> None:
    html = format_ticker_track_html(
        [TickerItem(text="book < tight & edge", kind="warn")]
    )
    assert "book &lt; tight &amp; edge" in html
    assert "book < tight" not in html


def test_quoting_policy_label_high_priority() -> None:
    items = build_ticker_items(
        {
            "quoting_policy_label": "Policy: near-touch 0.085% | relevant ≤0.10% from touch",
            "quote_decision_summary": "safe: favorable; MM → near-touch",
        },
        engine_running=True,
    )
    policy = next(
        item for item in items if item.text.startswith("Policy:")
    )
    assert policy.priority == 1
    assert policy.kind == "quote"


def test_stopped_engine_notice() -> None:
    items = build_ticker_items({"quote_decision_summary": "MM → touch"}, engine_running=False)
    assert any("Engine stopped" in item.text for item in items)
