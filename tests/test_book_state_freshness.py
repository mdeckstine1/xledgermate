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


def test_freshness_snapshot_includes_unix_anchor() -> None:
    connector = object()
    state = BookState(connector=connector)  # type: ignore[arg-type]
    state._touch()
    snap = state.freshness_snapshot()
    assert snap["ws_message_count"] == 1
    assert snap["ws_book_last_update_unix"] is not None
    assert snap["ws_book_last_update_utc"]
