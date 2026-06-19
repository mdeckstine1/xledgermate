"""BookState freshness / age semantics."""

from __future__ import annotations

import time

from experimental.ws_feed.book_state import BookState


def test_age_increases_without_touch() -> None:
    connector = object()
    state = BookState(connector=connector)  # type: ignore[arg-type]
    state._touch()
    age0 = state.age_seconds()
    time.sleep(0.05)
    age1 = state.age_seconds()
    assert age1 > age0


def test_depth_levels_caps_top_n() -> None:
    connector = object()
    state = BookState(connector=connector)  # type: ignore[arg-type]
    state.apply_snapshot(
        "bid",
        [{"price": 1.0 - i * 0.001, "size": float(10 + i)} for i in range(30)],
    )
    state.apply_snapshot(
        "ask",
        [{"price": 1.01 + i * 0.001, "size": float(5 + i)} for i in range(30)],
    )
    depth = state.depth_levels(max_levels=25)
    assert len(depth["bids"]) == 25
    assert len(depth["asks"]) == 25
    assert depth["bids"][0]["price"] > depth["bids"][-1]["price"]


def test_freshness_snapshot_includes_unix_anchor() -> None:
    connector = object()
    state = BookState(connector=connector)  # type: ignore[arg-type]
    state._touch()
    snap = state.freshness_snapshot()
    assert snap["ws_message_count"] == 1
    assert snap["ws_book_last_update_unix"] is not None
    assert snap["ws_book_last_update_utc"]
