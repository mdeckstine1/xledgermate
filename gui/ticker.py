"""Marquee ticker feed — extensible status lines for the top command bar."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence


@dataclass(frozen=True)
class TickerItem:
    """One scrolling line segment; lower priority appears first."""

    text: str
    kind: str = "info"
    priority: int = 5


_TICKER_KINDS = frozenset({"info", "quote", "warn", "danger", "success"})
_MAX_ITEMS = 16
_MAX_SEGMENT_CHARS = 220
_SUMMARY_SPLIT = re.compile(r"\s*;\s*")


def _clip(text: str, limit: int = _MAX_SEGMENT_CHARS) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _add(
    items: list[TickerItem],
    seen: set[str],
    *,
    text: str,
    kind: str = "info",
    priority: int = 5,
) -> None:
    clipped = _clip(text)
    if not clipped:
        return
    key = clipped.casefold()
    if key in seen:
        return
    seen.add(key)
    kind_norm = kind if kind in _TICKER_KINDS else "info"
    items.append(TickerItem(text=clipped, kind=kind_norm, priority=priority))


def _segments_from_summary(summary: str) -> list[str]:
    parts = [p.strip() for p in _SUMMARY_SPLIT.split(summary) if p.strip()]
    return parts or ([summary.strip()] if summary.strip() else [])


def _classify_quote_segment(segment: str) -> str:
    lowered = segment.casefold()
    if any(
        token in lowered
        for token in (
            "bailout",
            "pause bids",
            "pause asks",
            "toxic",
            "hostile",
            "defensive only",
            "kill",
            "thin edge",
        )
    ):
        return "warn"
    if "favorable" in lowered or "ok (" in lowered:
        return "success"
    return "quote"


def build_ticker_items(
    runtime: Mapping[str, Any],
    *,
    engine_running: bool = False,
    extra_notices: Optional[Sequence[str]] = None,
) -> list[TickerItem]:
    """
    Merge engine runtime fields and GUI context into ordered ticker segments.

    Add new providers by appending TickerItem entries here — render_marquee_ticker
    stays unchanged.
    """
    items: list[TickerItem] = []
    seen: set[str] = set()

    for notice in extra_notices or ():
        _add(items, seen, text=str(notice), kind="warn", priority=1)

    if not engine_running:
        _add(
            items,
            seen,
            text="Engine stopped — ticker shows last saved cycle",
            kind="warn",
            priority=2,
        )

    policy_label = str(runtime.get("quoting_policy_label") or "").strip()
    if policy_label:
        _add(items, seen, text=policy_label, kind="quote", priority=1)

    if runtime.get("pause_bids") or runtime.get("pause_asks"):
        flags = []
        if runtime.get("pause_bids"):
            flags.append("bids paused")
        if runtime.get("pause_asks"):
            flags.append("asks paused")
        _add(
            items,
            seen,
            text="Quoting: " + ", ".join(flags),
            kind="warn",
            priority=2,
        )

    fill_summary = str(runtime.get("fill_quality_summary") or "").strip()
    if fill_summary and fill_summary.casefold() != "no recent fills":
        kind = "warn" if "poor" in fill_summary.casefold() or "stressed" in fill_summary.casefold() else "info"
        _add(items, seen, text=fill_summary, kind=kind, priority=3)

    rebalance = str(runtime.get("rebalance_summary") or "").strip()
    if rebalance:
        _add(items, seen, text=rebalance, kind="info", priority=3)

    if runtime.get("market_edge_met") is False:
        edge_pct = float(runtime.get("market_edge_pct") or 0.0)
        _add(
            items,
            seen,
            text=f"Market edge thin ({edge_pct:+.3f}% capture vs book)",
            kind="warn",
            priority=3,
        )

    decision = str(runtime.get("quote_decision_summary") or "").strip()
    for segment in _segments_from_summary(decision):
        _add(
            items,
            seen,
            text=segment,
            kind=_classify_quote_segment(segment),
            priority=5,
        )

    if not items and engine_running:
        _add(
            items,
            seen,
            text="Awaiting first engine cycle…",
            kind="info",
            priority=9,
        )

    items.sort(key=lambda item: (item.priority, item.text.casefold()))
    return items[:_MAX_ITEMS]


def format_ticker_track_html(items: Sequence[TickerItem]) -> str:
    """Build inner HTML for the marquee track (escaped)."""
    if not items:
        return ""

    parts: list[str] = []
    for idx, item in enumerate(items):
        if idx:
            parts.append('<span class="xlm-marquee-sep"> · </span>')
        safe = html.escape(item.text)
        parts.append(
            f'<span class="xlm-marquee-item xlm-marquee-{item.kind}">{safe}</span>'
        )
    return "".join(parts)
