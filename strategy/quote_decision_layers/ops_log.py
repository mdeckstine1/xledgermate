"""
Grep-friendly ops visibility for peer-lane posture and solo quote decisions.

Operators tail logs or grep tokens like ``peer_lane=``, ``solo_mode=``,
``posture_reason=``, ``SOLO_ACCUMULATE_ON_EDGE``, ``inventory_cb_skipped_solo``
to see why the bot chose solo vs crowded posture without reading layer code.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from strategy.quote_decision_layers.types import BookMode, Posture, QuoteIntent

logger = logging.getLogger(__name__)

# Stable grep tokens (documented in docs/QUOTE_DECISION_LAYERS.md).
LOG_PREFIX = "QD_OPS"


def intel_has_peer_fields(intel: Optional[Mapping[str, Any]]) -> bool:
    if not intel:
        return False
    return "peer_lane_count" in intel or "peer_lane_empty" in intel


def peer_lane_token(*, peer_lane_empty: bool, peer_lane_count: int, intel_present: bool) -> str:
    """Map inputs to peer_lane=empty|missing|crowded."""
    if not intel_present:
        return "missing"
    if peer_lane_empty or peer_lane_count <= 0:
        return "empty"
    return "crowded"


def posture_reason(
    *,
    solo: bool,
    peer_lane_empty: bool,
    peer_lane_count: int,
    intel_present: bool,
    low_book_pressure: bool,
) -> str:
    if not intel_present:
        return "missing_intel"
    if peer_lane_empty:
        return "confirmed_empty"
    if solo and low_book_pressure and peer_lane_count == 1:
        return "sparse_low_pressure"
    return "crowded_default"


def peer_intel_status(
    intel: Optional[Mapping[str, Any]],
    *,
    intel_stale: bool = False,
    intel_present: Optional[bool] = None,
) -> str:
    """present | missing | stale — for operator visibility on intel freshness."""
    has_fields = intel_present if intel_present is not None else intel_has_peer_fields(intel)
    if not has_fields:
        return "missing"
    if intel_stale or (intel and bool(intel.get("competitor_error"))):
        return "stale"
    return "present"


def format_posture_ops_line(
    *,
    posture: Posture,
    peer_lane_empty: bool,
    peer_lane_count: int,
    intel_present: bool,
    low_book_pressure: bool,
    intel_status: str = "present",
    path: str = "",
) -> str:
    solo = posture.book.solo
    reason = posture_reason(
        solo=solo,
        peer_lane_empty=peer_lane_empty,
        peer_lane_count=peer_lane_count,
        intel_present=intel_present,
        low_book_pressure=low_book_pressure,
    )
    lane = peer_lane_token(
        peer_lane_empty=peer_lane_empty,
        peer_lane_count=peer_lane_count,
        intel_present=intel_present,
    )
    parts = [
        f"{LOG_PREFIX} posture",
        f"peer_intel={intel_status}",
        f"peer_lane={lane}",
        f"peer_lane_empty={str(peer_lane_empty).lower()}",
        f"peer_lane_count={posture.book.peer_lane_count}",
        f"solo_mode={str(solo).lower()}",
        f"book_mode={posture.book.mode.value}",
        f"posture_reason={reason}",
    ]
    if path:
        parts.append(f"path={path}")
    return " | ".join(parts)


def log_posture_ops(
    *,
    posture: Posture,
    peer_lane_empty: bool,
    peer_lane_count: int,
    intel_present: bool,
    low_book_pressure: bool,
    intel: Optional[Mapping[str, Any]] = None,
    intel_stale: bool = False,
    path: str = "",
) -> str:
    """Log Layer-1 posture + peer lane consumption; returns the formatted line."""
    status = peer_intel_status(
        intel, intel_stale=intel_stale, intel_present=intel_present
    )
    line = format_posture_ops_line(
        posture=posture,
        peer_lane_empty=peer_lane_empty,
        peer_lane_count=peer_lane_count,
        intel_present=intel_present,
        low_book_pressure=low_book_pressure,
        intel_status=status,
        path=path,
    )
    logger.info(line)
    return line


def log_solo_accumulate_intent(
    *,
    posture: Posture,
    buy_edge_viable: bool,
    sell_edge_viable: bool,
    bid_edge_pct: float,
    ask_edge_pct: float,
    path: str = "",
) -> None:
    """Explicit log when SOLO_ACCUMULATE_ON_EDGE is selected."""
    favor = "bid" if buy_edge_viable else "ask"
    if posture.book.peer_lane_count <= 0 and posture.book.solo:
        lane = "empty"
    elif posture.book.peer_lane_count > 0:
        lane = "crowded"
    else:
        lane = "missing"
    parts = [
        f"{LOG_PREFIX} intent=SOLO_ACCUMULATE_ON_EDGE",
        f"peer_lane={lane}",
        f"solo_mode=true",
        f"book_mode={posture.book.mode.value}",
        f"favor_{favor}=true",
        f"buy_edge_viable={str(buy_edge_viable).lower()}",
        f"sell_edge_viable={str(sell_edge_viable).lower()}",
        f"bid_edge_pct={bid_edge_pct:.3f}",
        f"ask_edge_pct={ask_edge_pct:.3f}",
        f"drift_band={posture.inventory.band.value}",
    ]
    if path:
        parts.append(f"path={path}")
    logger.info(" | ".join(parts))


def log_inventory_cb_skipped_solo(*, path: str = "") -> None:
    """Inventory circuit breaker bypass on solo books (Layer 5)."""
    parts = [
        f"{LOG_PREFIX} inventory_cb_skipped_solo=true",
        "reason=solo_book_deferred_to_intent",
    ]
    if path:
        parts.append(f"path={path}")
    logger.info(" | ".join(parts))


def log_peer_lane_resolve(
    intel: Optional[Mapping[str, Any]],
    *,
    peer_lane_empty: bool,
    peer_lane_count: int,
    intel_stale: bool = False,
    path: str = "",
) -> str:
    """Log peer intel → posture inputs at consumption boundary."""
    present = intel_has_peer_fields(intel)
    status = peer_intel_status(intel, intel_stale=intel_stale, intel_present=present)
    lane = peer_lane_token(
        peer_lane_empty=peer_lane_empty,
        peer_lane_count=peer_lane_count,
        intel_present=present,
    )
    parts = [
        f"{LOG_PREFIX} peer_lane_resolve",
        f"peer_intel={status}",
        f"peer_lane={lane}",
        f"peer_lane_empty={str(peer_lane_empty).lower()}",
        f"peer_lane_count={peer_lane_count}",
    ]
    if path:
        parts.append(f"path={path}")
    line = " | ".join(parts)
    logger.info(line)
    return line


def maybe_log_solo_accumulate(
    intent_value: QuoteIntent,
    *,
    posture: Posture,
    buy_edge_viable: bool,
    sell_edge_viable: bool,
    bid_edge_pct: float,
    ask_edge_pct: float,
    path: str = "",
) -> None:
    if intent_value == QuoteIntent.SOLO_ACCUMULATE_ON_EDGE:
        log_solo_accumulate_intent(
            posture=posture,
            buy_edge_viable=buy_edge_viable,
            sell_edge_viable=sell_edge_viable,
            bid_edge_pct=bid_edge_pct,
            ask_edge_pct=ask_edge_pct,
            path=path,
        )
