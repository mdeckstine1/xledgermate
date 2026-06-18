"""Tests for M6 fill quote-age JSONL stream."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from experimental.ws_feed.fill_quote_age_log import (
    append_fill_quote_age_record,
    build_fill_quote_age_record,
    push_recent_fill_age,
    tail_fill_quote_age_records,
)


def test_append_and_tail_fill_quote_age(tmp_path: Path) -> None:
    path = tmp_path / "logs" / "fill_quote_age.jsonl"
    row = build_fill_quote_age_record(
        cycle=10,
        side="BUY",
        offer_side="bid",
        xrp_amount=5.0,
        quote_age_seconds=12.5,
        offer_sequence=999,
        ws_as_version="2.1.19",
        fills_session=3,
        capture_xrp=0.02,
        tracking="m6_sequence",
    )
    append_fill_quote_age_record(row, path=path)
    rows = tail_fill_quote_age_records(limit=10, path=path)
    assert len(rows) == 1
    assert rows[0]["quote_age_seconds"] == 12.5
    assert rows[0]["offer_sequence"] == 999
    assert rows[0]["tracking"] == "m6_sequence"


def test_tail_filters_since_and_version(tmp_path: Path) -> None:
    path = tmp_path / "fill_quote_age.jsonl"
    old = build_fill_quote_age_record(
        cycle=1,
        side="SELL",
        offer_side="ask",
        xrp_amount=1.0,
        quote_age_seconds=1.0,
        offer_sequence=None,
        ws_as_version="2.1.18",
        fills_session=1,
        capture_xrp=0.0,
        tracking="m6_side",
    )
    old["ts_utc"] = "2026-06-18T10:00:00+00:00"
    new = build_fill_quote_age_record(
        cycle=2,
        side="BUY",
        offer_side="bid",
        xrp_amount=2.0,
        quote_age_seconds=3.0,
        offer_sequence=100,
        ws_as_version="2.1.19",
        fills_session=2,
        capture_xrp=0.01,
        tracking="m6_sequence",
    )
    new["ts_utc"] = "2026-06-18T20:00:00+00:00"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, separators=(",", ":")) for r in (old, new)) + "\n",
        encoding="utf-8",
    )
    since = datetime(2026, 6, 18, 19, 0, tzinfo=timezone.utc)
    rows = tail_fill_quote_age_records(
        path=path,
        since=since,
        ws_as_version="2.1.19",
    )
    assert len(rows) == 1
    assert rows[0]["cycle"] == 2


def test_push_recent_fill_age_caps_buffer() -> None:
    buf: list = []
    for i in range(25):
        buf = push_recent_fill_age(buf, {"cycle": i}, max_len=20)
    assert len(buf) == 20
    assert buf[0]["cycle"] == 5
    assert buf[-1]["cycle"] == 24
