"""Shared dataclasses for Trading Bot Alpha."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class BalanceSnapshot:
    xrp: float
    rlusd: float
    mid_rlusd_per_xrp: Optional[float] = None
    portfolio_xrp_equiv: float = 0.0


@dataclass(frozen=True)
class TrustLineSnapshot:
    exists: bool
    balance: float = 0.0
    limit: float = 0.0
    no_ripple: bool = False
    issuer: str = ""


@dataclass(frozen=True)
class InventorySnapshot:
    xrp_ratio: float
    target_xrp_ratio: float
    deviation: float
    label: str
    pause_bids: bool
    pause_asks: bool
    summary: str
    portfolio_xrp_equiv: float = 0.0
    xrp_allocation_pct: float = 0.0
    rlusd_allocation_pct: float = 0.0
    buy_blocked_imbalance: bool = False
    sell_blocked_imbalance: bool = False


@dataclass(frozen=True)
class RiskSnapshot:
    kill_switch_active: bool
    kill_switch_reason: str
    drawdown_pct: float
    max_drawdown_pct: float
    preflight_ready: bool
    preflight_summary: str
    preflight_errors: List[str] = field(default_factory=list)
    preflight_warnings: List[str] = field(default_factory=list)
    session_pnl_xrp: float = 0.0
    trading_allowed: bool = True
    edge_validation_required: bool = True
    alerts: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class BookLevel:
    price: float
    size_xrp: float


@dataclass(frozen=True)
class OrderBookSnapshot:
    bids: Tuple[BookLevel, ...]
    asks: Tuple[BookLevel, ...]
    best_bid: Optional[float]
    best_ask: Optional[float]
    mid: Optional[float]
    spread: Optional[float]
    spread_pct: Optional[float]
    fetched_utc: datetime


@dataclass(frozen=True)
class LiquidityDepth:
    """XRP depth available within max_slippage_pct of touch."""

    max_slippage_pct: float
    bid_depth_xrp: float
    ask_depth_xrp: float
    best_bid: Optional[float]
    best_ask: Optional[float]
    mid: Optional[float]
    spread_pct: Optional[float]


@dataclass(frozen=True)
class AccountSnapshot:
    """Balances plus optional live book mid for one-cycle reporting."""

    xrp: float
    rlusd: float
    mid_rlusd_per_xrp: Optional[float]
    portfolio_xrp_equiv: float
    trust_line: TrustLineSnapshot
    book: Optional[OrderBookSnapshot] = None


@dataclass(frozen=True)
class LedgerOfferResult:
    """Outcome of a gated offer placement or cancel."""

    submitted: bool
    dry_run: bool
    action: str
    tx_hash: Optional[str] = None
    sequence: Optional[int] = None
    offer_resting: Optional[bool] = None


@dataclass(frozen=True)
class BracketStatusSummary:
    """Open bracket posture for operator reports."""

    total: int = 0
    pending_buys: int = 0
    active_fixed: int = 0
    active_sl_trailing: int = 0
    active_breakout_trailing: int = 0
    active_trailing: int = 0
    recent_events: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class CycleReportContext:
    """Full cycle context for rich Telegram / console reports."""

    snapshot: OperatorSnapshot
    bracket_summary: BracketStatusSummary
    decision_action: str = "hold"
    decision_reason: str = ""
    execution_summary: str = ""
    open_offers_count: int = 0
    structure_summary: str = ""
    operator_paused: bool = False


@dataclass(frozen=True)
class OperatorSnapshot:
    """Single-cycle operator view for reporting and Phase 2 hooks."""

    generated_utc: datetime
    alpha_version: str
    network: str
    dry_run: bool
    trading_enabled: bool
    account_address: str
    balances: BalanceSnapshot
    trust_line: TrustLineSnapshot
    inventory: InventorySnapshot
    risk: RiskSnapshot
