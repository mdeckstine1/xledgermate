"""
Shared types for the layered quote decision stack.

Design: no shared pause_bids/pause_asks flags across layers. Each layer produces
read-only or side-local outputs; Layer 5 alone sets final permissions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from strategy.fill_quality import FillQualityState


QUOTE_DECISION_VERSION = "2.3.0"


class BookMode(str, Enum):
    """Layer 1 — how crowded the peer lane is."""

    SOLO = "solo"
    SPARSE = "sparse"
    CROWDED = "crowded"


class DriftBand(str, Enum):
    """Layer 1 — inventory drift vs target (wide tolerance bands)."""

    NEUTRAL = "neutral"
    MILD_XRP = "mild_xrp"
    HEAVY_XRP = "heavy_xrp"
    MILD_RLUSD = "mild_rlusd"
    HEAVY_RLUSD = "heavy_rlusd"


class QuoteIntent(str, Enum):
    """Layer 2 — what the bot is trying to accomplish this cycle."""

    SOLO_ACCUMULATE_ON_EDGE = "solo_accumulate_on_edge"
    PATIENT_SOLO = "patient_solo"
    TWO_SIDED_SKIM = "two_sided_skim"
    INVENTORY_UNLOAD = "inventory_unload"
    PROTECT_BLEED = "protect_bleed"  # legacy alias — strategy uses side-local bleed + L5
    HOLD_OFF = "hold_off"


@dataclass(frozen=True)
class BookPosture:
    solo: bool
    peer_lane_count: int
    mode: BookMode


@dataclass(frozen=True)
class InventoryDrift:
    xrp_ratio: float
    target_xrp_ratio: float
    deviation: float
    label: str
    band: DriftBand


@dataclass(frozen=True)
class SideFillQuality:
    """Recent economics on one side — input to bleed detection only."""

    fill_count: int
    session_capture_xrp: float
    recent_capture_xrp: float
    avg_edge_bps: Optional[float]
    bleeding: bool
    bleed_reason: str = ""


@dataclass(frozen=True)
class PostureSnapshot:
    """
    Layer 1 output — single read-only view of the cycle context.

    Built once per cycle; never mutated by downstream layers.
    """

    book: BookPosture
    inventory: InventoryDrift
    buy_quality: SideFillQuality
    sell_quality: SideFillQuality
    toxic_ratio_30s: float
    g2_spread_mult: float
    g2_grade: str


@dataclass(frozen=True)
class EdgeViability:
    """Layer 3 output — net edge after fee + adverse buffer."""

    implied_edge_bps: Optional[float]
    min_edge_bps: float
    viable: bool
    reason: str


@dataclass(frozen=True)
class SidePermission:
    """
    Layer 5 output — final permission for one side.

    Replaces pause_bids/pause_asks: explicit allowed + size_mult + reason.
    """

    allowed: bool
    size_mult: float
    implied_edge_bps: Optional[float] = None
    block_reason: str = ""
    pause_cause: str = ""  # edge | bleed | inventory | tape | intent | operator | ""


@dataclass(frozen=True)
class LayerTrace:
    """Debug / HUD / intel — why each layer chose what it chose."""

    intent: QuoteIntent
    intent_reason: str
    bid_edge: EdgeViability
    ask_edge: EdgeViability
    bid_bleed_note: str = ""
    ask_bleed_note: str = ""


@dataclass(frozen=True)
class QuotingDecision:
    """Layer 5 — sole authority on final quoting permissions."""

    bid: SidePermission
    ask: SidePermission
    intent: QuoteIntent
    posture: PostureSnapshot
    trace: LayerTrace
    summary: str
    would_quote: bool
    inventory_cb_mode: str = "clear"
    inventory_cb_note: str = ""
    heavy_drift_l5_deferred: bool = False

    def to_legacy_flags(self) -> Dict[str, Any]:
        """
        Thin bridge for gradual migration — maps to pause_* for old code paths.

        Prefer reading bid/ask directly in new integrations.
        """
        return {
            "quote_decision_version": QUOTE_DECISION_VERSION,
            "quote_intent": self.intent.value,
            "bid_allowed": self.bid.allowed,
            "ask_allowed": self.ask.allowed,
            "bid_size_mult": self.bid.size_mult,
            "ask_size_mult": self.ask.size_mult,
            "bid_block_reason": self.bid.block_reason,
            "ask_block_reason": self.ask.block_reason,
            # Legacy compat — prefer bid/ask.allowed in new integrations
            "bid_allowed": self.bid.allowed,
            "ask_allowed": self.ask.allowed,
            "would_quote": self.would_quote,
            "quote_decision_summary": self.summary,
        }


@dataclass
class CycleQuoteInputs:
    """Everything needed to run the pipeline for one cycle."""

    mid: float
    best_bid: float
    best_ask: float
    l1_bid_price: float
    l1_ask_price: float
    xrp_ratio: float
    target_xrp_ratio: float
    inventory_label: str
    peer_lane_empty: bool
    peer_lane_count: int = 0
    toxic_ratio_30s: float = 0.0
    g2_spread_mult: float = 1.0
    g2_grade: str = ""
    session_buy_capture_xrp: Optional[float] = None
    session_sell_capture_xrp: Optional[float] = None
    recent_buys: tuple[Dict[str, Any], ...] = field(default_factory=tuple)
    recent_sells: tuple[Dict[str, Any], ...] = field(default_factory=tuple)
    reservation_allows_bid: bool = True
    reservation_allows_ask: bool = True
    fill_quality: Optional["FillQualityState"] = None
    market_condition: str = "favorable"
    mid_momentum_pct: float = 0.0
    min_edge_pct: float = 0.0
    market_edge_met: bool = True
    inventory_max_deviation: float = 0.12
    inventory_mode: str = "market_make"
    acquiring_rlusd: bool = False
    mm_mode: bool = True
    momentum_pause_vulnerable: bool = False
    low_book_pressure: bool = False
    peer_intel_present: bool = False
    bid_half_spread_pct: Optional[float] = None
    ask_half_spread_pct: Optional[float] = None
