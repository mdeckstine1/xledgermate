"""
Layered quote decision types for the sacred / long-run engine path.

Design: posture is read-only (Layer 1); bleed is side-local (Layer 4);
Layer 5 alone sets final bid/ask permissions mapped to pause_bids/pause_asks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class BookMode(str, Enum):
    """How crowded the peer lane is."""

    SOLO = "solo"
    SPARSE = "sparse"
    CROWDED = "crowded"


class DriftBand(str, Enum):
    """Inventory drift vs target — wide tolerance bands for growth from edge."""

    NEUTRAL = "neutral"
    MILD_XRP = "mild_xrp"
    HEAVY_XRP = "heavy_xrp"
    MILD_RLUSD = "mild_rlusd"
    HEAVY_RLUSD = "heavy_rlusd"


class QuoteIntent(str, Enum):
    """Operational goal for this cycle — Layer 2."""

    SOLO_ACCUMULATE_ON_EDGE = "solo_accumulate_on_edge"
    PATIENT_SOLO = "patient_solo"
    TWO_SIDED_SKIM = "two_sided_skim"
    INVENTORY_UNLOAD = "inventory_unload"
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
    """Recent economics on one side — bleed detection input only."""

    fill_count: int
    toxic_ratio_30s: float
    mean_markout_30s_pct: float
    bleeding: bool
    bleed_reason: str = ""


@dataclass(frozen=True)
class Posture:
    """
    Layer 1 — single read-only snapshot per cycle.

    Captures book state, inventory drift, and per-side fill quality.
    """

    book: BookPosture
    inventory: InventoryDrift
    buy_quality: SideFillQuality
    sell_quality: SideFillQuality
    market_condition: str
    mid_momentum_pct: float


@dataclass(frozen=True)
class IntentSelection:
    """Layer 2 — what we are trying to accomplish (not final permissions)."""

    intent: QuoteIntent
    reason: str
    favor_bid: bool
    favor_ask: bool
    allow_two_sided: bool


@dataclass(frozen=True)
class EdgeViability:
    """Layer 3 — net edge after fees + adverse buffer."""

    implied_edge_pct: float
    min_edge_pct: float
    viable: bool
    reason: str


@dataclass(frozen=True)
class SidePermission:
    """Layer 5 — final permission for one side."""

    allowed: bool
    size_mult: float
    implied_edge_pct: float = 0.0
    block_reason: str = ""
    pause_cause: str = ""  # edge | bleed | inventory | tape | intent | operator | ""


@dataclass(frozen=True)
class LayerTrace:
    """Compact per-cycle layer snapshot for solo diagnostics and tests."""

    book_mode: BookMode
    drift_band: DriftBand
    intent: QuoteIntent
    bid_edge_viable: bool
    ask_edge_viable: bool
    bid_capture_pct: float
    ask_capture_pct: float
    bid_pause_cause: str
    ask_pause_cause: str

    def compact(self) -> str:
        """One-line trace — intended for solo books or blocked sides only."""
        bid_e = "✓" if self.bid_edge_viable else "✗"
        ask_e = "✓" if self.ask_edge_viable else "✗"
        bid_p = self.bid_pause_cause or "—"
        ask_p = self.ask_pause_cause or "—"
        return (
            f"trace book={self.book_mode.value} drift={self.drift_band.value} "
            f"intent={self.intent.value} "
            f"bid_e={self.bid_capture_pct:.3f}%{bid_e} ask_e={self.ask_capture_pct:.3f}%{ask_e} "
            f"pause_bid={bid_p} pause_ask={ask_p}"
        )


@dataclass(frozen=True)
class LayerQuotingDecision:
    """Layer 5 output — sole authority on side permissions."""

    bid: SidePermission
    ask: SidePermission
    intent: QuoteIntent
    posture: Posture
    summary: str
    bid_pause_note: str = ""
    ask_pause_note: str = ""
    trace: Optional[LayerTrace] = None
    posture_ops_line: str = ""
