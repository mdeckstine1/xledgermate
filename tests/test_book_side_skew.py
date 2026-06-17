"""Tests for I5 book-wide side skew aggregate."""

from experimental.market_analysis.competitor_intel import (
    CompetitorProfile,
    aggregate_book_side_skew,
)
from experimental.ws_feed.hud_intel_support import (
    book_side_skew_hud_fields,
    structured_peer_briefing,
)


def test_aggregate_book_side_skew_bid_heavy() -> None:
    profiles = [
        CompetitorProfile(account="rA", sides_quoted={"bid": 10, "ask": 2}),
        CompetitorProfile(account="rB", sides_quoted={"bid": 8, "ask": 4}),
    ]
    out = aggregate_book_side_skew(profiles)
    assert out["book_bid_offers"] == 18
    assert out["book_ask_offers"] == 6
    assert out["book_side_skew_label"] == "bid_heavy"
    assert out["book_side_skew"] is not None
    assert out["book_side_skew"] > 0.15


def test_aggregate_book_side_skew_empty() -> None:
    out = aggregate_book_side_skew([])
    assert out["book_side_skew_label"] == "unknown"
    assert out["book_side_skew"] is None


def test_book_side_skew_hud_fields() -> None:
    runtime = {
        "competitor_intel": {
            "book_bid_offers": 40,
            "book_ask_offers": 10,
            "book_side_skew": 0.6,
            "book_side_skew_label": "bid_heavy",
        }
    }
    fields = book_side_skew_hud_fields(runtime)
    assert "b40/a10" in fields["book_side_skew_display"]
    assert fields["book_side_skew_label"] == "bid_heavy"


def test_book_side_skew_rollup_from_top_competitors() -> None:
    runtime = {
        "top_competitors": [
            {"account": "rA...", "sides": "b12/a4"},
            {"account": "rB...", "sides": "b8/a6"},
        ],
    }
    fields = book_side_skew_hud_fields(runtime)
    assert fields["book_bid_offers"] == 20
    assert fields["book_ask_offers"] == 10
    assert "b20/a10" in fields["book_side_skew_display"]


def test_structured_peer_briefing_schema() -> None:
    ctx = {
        "profile": {
            "account_full": "rTest123",
            "touch_xrp": 12.0,
            "last_spread": 0.18,
            "avg_spread": 0.2,
            "activity": 50,
            "cancels": 1,
            "sides": "b10/a5",
        },
        "source": "peer_lane",
        "in_peer_lane": True,
        "touch_xrp": 12.0,
        "our_lane_xrp": 9.0,
        "peer_band_low_xrp": 3.6,
        "peer_band_high_xrp": 22.5,
        "fled_events": [],
        "evidence_lines": ["scrape_source=peer_lane"],
        "lane_note": "IN peer touch band",
    }
    state = {"competitor_pressure": 0.3, "peer_lane_count": 2, "book_side_skew_label": "balanced"}
    doc = structured_peer_briefing(ctx, address="rTest123", state=state)
    assert doc["schema_version"] == 1
    assert doc["address"] == "rTest123"
    assert doc["in_peer_lane"] is True
    assert doc["profile"]["account"] == "rTest123"
    assert doc["macro"]["competitor_pressure"] == 0.3
