"""Tests for WsBookFeed freshness helpers."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

from experimental.ws_feed.ws_book_feed import WsBookFeed


def _make_feed() -> WsBookFeed:
    connector = MagicMock()
    return WsBookFeed(
        connector=connector,
        ws_url="wss://example.test",
        pair=MagicMock(),
    )


def test_refresh_if_stale_skips_fresh_book() -> None:
    feed = _make_feed()
    feed.state.last_update_monotonic = time.monotonic()
    feed.seed_from_ws_snapshot = AsyncMock()  # type: ignore[method-assign]

    async def _run() -> float:
        return await feed.refresh_if_stale(12.0)

    age = asyncio.run(_run())
    assert age < 1.0
    feed.seed_from_ws_snapshot.assert_not_called()


def test_refresh_if_stale_reseeds_when_old() -> None:
    feed = _make_feed()
    feed.state.last_update_monotonic = time.monotonic() - 60.0
    feed.seed_from_ws_snapshot = AsyncMock()  # type: ignore[method-assign]

    async def _run() -> None:
        await feed.refresh_if_stale(12.0)

    asyncio.run(_run())
    feed.seed_from_ws_snapshot.assert_called_once()


def test_is_fresh_and_backoff() -> None:
    feed = _make_feed()
    feed.state.last_update_monotonic = __import__("time").monotonic()
    assert feed.is_fresh() is True
    feed.reconnect_count = 2
    assert feed.reconnect_backoff_seconds() == 20.0
    health = feed.feed_health_snapshot()
    assert health["ws_book_is_fresh"] is True
    assert health["ws_reconnect_count"] == 2


def test_refresh_if_stale_reseeds_when_old_and_updates_touch() -> None:
    feed = _make_feed()

    async def _touch_seed(**_kwargs: object) -> dict:
        feed.state._touch()
        return {"bids": [], "asks": []}

    feed.state.last_update_monotonic = time.monotonic() - 60.0
    feed.seed_from_ws_snapshot = _touch_seed  # type: ignore[method-assign]

    async def _run() -> float:
        return await feed.refresh_if_stale(12.0)

    age = asyncio.run(_run())
    assert age < 1.0
