"""Bracket order types and lifecycle enums."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from alpha.types import utc_now


class BracketLifecycleState(str, Enum):
    """Application-level bracket state machine."""

    PENDING_BUY = "pending_buy"
    BRACKET_ACTIVE = "bracket_active"
    TP_FILLED = "tp_filled"
    SL_FILLED = "sl_filled"
    CANCELLED = "cancelled"
    TRAILING_PLACEHOLDER = "trailing_placeholder"


class BracketMode(str, Enum):
    """Bracket management mode."""

    BRACKET = "bracket"  # Fixed TP; SL may trail after breakeven
    BREAKOUT_TRAILING = "breakout_trailing"  # TP trails after breakout confirmation


class BracketLegRole(str, Enum):
    TAKE_PROFIT = "tp"
    STOP_LOSS = "sl"


@dataclass
class BracketLeg:
    """One limit leg (TP or SL) tied to a bracket pair."""

    role: BracketLegRole
    sequence: Optional[int]
    price_rlusd_per_xrp: float
    size_xrp: float
    remaining_xrp: float


@dataclass
class BracketRecord:
    """Tracks one buy and its associated TP/SL pair."""

    bracket_id: str
    state: BracketLifecycleState
    mode: BracketMode
    buy_sequence: int
    entry_price_rlusd_per_xrp: float
    target_size_xrp: float
    filled_xrp: float = 0.0
    bracketed_xrp: float = 0.0
    tp_leg: Optional[BracketLeg] = None
    sl_leg: Optional[BracketLeg] = None
    breakeven_passed: bool = False
    breakout_confirmed: bool = False
    peak_mid_rlusd_per_xrp: float = 0.0
    last_sl_trail_anchor_mid: float = 0.0
    last_tp_trail_anchor_mid: float = 0.0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()


@dataclass(frozen=True)
class BracketFillEvent:
    """Emitted when a bracket leg or buy fill is detected."""

    bracket_id: str
    leg: str  # buy | tp | sl
    filled_xrp: float
    price_rlusd_per_xrp: float
    partial: bool
    new_state: BracketLifecycleState
