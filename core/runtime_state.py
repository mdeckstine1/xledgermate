from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class QuoteIntent:
    level: int
    side: str
    price: float
    size_xrp: float


@dataclass
class RuntimeState:
    version: str = "1.0.0"
    network: str = "testnet"
    rpc_url: str = ""
    dry_run: bool = True
    trading_enabled: bool = True
    kill_switch_active: bool = False
    kill_switch_reason: str = ""
    preflight_ready: bool = False
    preflight_summary: str = ""
    preflight_errors: List[str] = field(default_factory=list)
    preflight_warnings: List[str] = field(default_factory=list)
    portfolio_value_xrp: float = 0.0
    drawdown_pct: float = 0.0
    active_profile: str = "safe"
    mid_price: Optional[float] = None
    best_bid_rlusd_per_xrp: Optional[float] = None
    best_ask_rlusd_per_xrp: Optional[float] = None
    price_is_testnet_book: bool = True
    volatility_pct: float = 0.0
    liquidity_score: float = 0.0
    effective_spreads_pct: Dict[int, float] = field(default_factory=dict)
    balance_xrp: float = 0.0
    balance_rlusd: float = 0.0
    open_offers_count: int = 0
    open_offers: List[Dict[str, Any]] = field(default_factory=list)
    cycle_count: int = 0
    offers_placed_last_cycle: int = 0
    last_execution_summary: str = ""
    session_baseline_xrp: Optional[float] = None
    session_baseline_rlusd: Optional[float] = None
    session_baseline_mid: Optional[float] = None
    session_baseline_portfolio_xrp: Optional[float] = None
    session_pnl_mtm_xrp: float = 0.0
    session_pnl_balance_xrp: float = 0.0
    session_pnl_xrp_estimate: float = 0.0
    quote_intents: List[QuoteIntent] = field(default_factory=list)
    recent_decisions: List[Dict[str, str]] = field(default_factory=list)
    last_error: Optional[str] = None
    updated_utc: Optional[str] = None
    engine_pid: Optional[int] = None
    price_source: str = "xrpl_book_offers"
    price_history: List[Dict[str, Any]] = field(default_factory=list)
    # Market conditions + decision transparency
    market_condition: str = "neutral"
    market_condition_label: str = "Neutral"
    volatility_level: str = "moderate"
    liquidity_level: str = "moderate"
    book_spread_pct: float = 0.0
    book_spread_status: str = "unknown"
    market_health_score: float = 0.0
    recommended_profile: str = "safe"
    recommendation_reason: str = ""
    quote_decision_summary: str = ""
    quoting_policy_label: str = ""
    quoting_touch_mode: str = ""
    inventory_label: str = "balanced"
    mid_momentum_pct: float = 0.0
    spread_validation_ok: bool = False
    spread_validation_summary: str = ""
    spread_validation_errors: List[str] = field(default_factory=list)
    spread_validation_lines: List[Dict[str, Any]] = field(default_factory=list)
    # Defensive MM transparency
    adverse_selection_tier: str = "none"
    book_pressure_label: str = "balanced"
    market_edge_met: bool = True
    market_edge_pct: float = 0.0
    fill_quality_score: float = 100.0
    fill_quality_summary: str = ""
    rebalance_action: str = ""
    rebalance_summary: str = ""
    pause_bids: bool = False
    pause_asks: bool = False
    inventory_mode: str = "market_make"
    effective_min_edge_pct: float = 0.0
    edge_resolution_summary: str = ""
    dynamic_min_edge_enabled: bool = False
    edge_strictness: float = 1.0
    # Tier 2 execution metrics
    toxic_fill_ratio: float = 0.0
    toxic_fill_ratio_30s: float = 0.0
    mean_markout_30s_pct: float = 0.0
    g2_size_mult: float = 1.0
    g2_spread_mult: float = 1.0
    g2_grade: str = "neutral"
    g2_active: bool = False
    g2_summary: str = ""
    g4_size_mult: float = 1.0
    g4_grade: str = "neutral"
    g4_active: bool = False
    g4_summary: str = ""
    competitor_intel: Dict[str, Any] = field(default_factory=dict)

    # WS + pure A-S (committed future path) — optional, for compatibility + new views
    ws_as_version: str = ""
    as_mode: str = "off"  # "pure" | "hybrid" | "off"
    as_reservation: Optional[float] = None
    as_optimal_spread_pct: Optional[float] = None
    as_gamma: Optional[float] = None
    as_kappa: Optional[float] = None
    ws_book_age_s: Optional[float] = None
    ws_message_count: int = 0
    as_presence_pct: Optional[float] = None  # session or window presence under A-S
    as_protected: bool = False  # true when A-S math (reservation inside book) is the decider
    offers_cancelled_session: int = 0
    offers_kept_session: int = 0
    fills_session: int = 0
    cancel_per_fill: float = 0.0
    book_poll_interval_seconds: int = 15
    full_quote_refresh_seconds: int = 60
    last_cycle_full_refresh: bool = True
    join_touch_active: bool = False
    quotes_at_touch: bool = True
    worst_vs_touch_bps: float = 0.0
    quote_visibility_summary: str = ""

    def touch(self) -> None:
        self.updated_utc = datetime.now(tz=timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _load_session_pnl_mtm(data: Dict[str, Any]) -> float:
    if "session_pnl_mtm_xrp" in data:
        return float(data["session_pnl_mtm_xrp"])
    baseline_port = data.get("session_baseline_portfolio_xrp")
    port = data.get("portfolio_value_xrp")
    if baseline_port is not None and port is not None:
        return float(port) - float(baseline_port)
    return float(data.get("session_pnl_xrp_estimate", 0.0))


class RuntimeStateStore:
    def __init__(self, path: str = "logs/runtime_state.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, state: RuntimeState) -> None:
        state.touch()
        payload = state.to_dict()
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load(self) -> Optional[RuntimeState]:
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        intents = [QuoteIntent(**item) for item in data.get("quote_intents", [])]
        return RuntimeState(
            version=data.get("version", "1.0.0"),
            network=data.get("network", "testnet"),
            rpc_url=data.get("rpc_url", ""),
            dry_run=data.get("dry_run", True),
            trading_enabled=data.get("trading_enabled", True),
            kill_switch_active=data.get("kill_switch_active", False),
            kill_switch_reason=str(data.get("kill_switch_reason", "")),
            preflight_ready=bool(data.get("preflight_ready", False)),
            preflight_summary=str(data.get("preflight_summary", "")),
            preflight_errors=list(data.get("preflight_errors", [])),
            preflight_warnings=list(data.get("preflight_warnings", [])),
            portfolio_value_xrp=float(data.get("portfolio_value_xrp", 0.0)),
            drawdown_pct=float(data.get("drawdown_pct", 0.0)),
            active_profile=data.get("active_profile", "safe"),
            mid_price=data.get("mid_price"),
            best_bid_rlusd_per_xrp=data.get("best_bid_rlusd_per_xrp"),
            best_ask_rlusd_per_xrp=data.get("best_ask_rlusd_per_xrp"),
            price_is_testnet_book=bool(data.get("price_is_testnet_book", True)),
            volatility_pct=float(data.get("volatility_pct", 0.0)),
            liquidity_score=float(data.get("liquidity_score", 0.0)),
            effective_spreads_pct={
                int(k): float(v) for k, v in (data.get("effective_spreads_pct") or {}).items()
            },
            balance_xrp=float(data.get("balance_xrp", 0.0)),
            balance_rlusd=float(data.get("balance_rlusd", 0.0)),
            open_offers_count=int(data.get("open_offers_count", 0)),
            open_offers=list(data.get("open_offers", [])),
            cycle_count=int(data.get("cycle_count", 0)),
            offers_placed_last_cycle=int(data.get("offers_placed_last_cycle", 0)),
            last_execution_summary=str(data.get("last_execution_summary", "")),
            session_baseline_xrp=data.get("session_baseline_xrp"),
            session_baseline_rlusd=data.get("session_baseline_rlusd"),
            session_baseline_mid=data.get("session_baseline_mid"),
            session_baseline_portfolio_xrp=data.get("session_baseline_portfolio_xrp"),
            session_pnl_mtm_xrp=_load_session_pnl_mtm(data),
            session_pnl_balance_xrp=float(
                data.get(
                    "session_pnl_balance_xrp",
                    data.get("session_pnl_xrp_estimate", 0.0),
                )
            ),
            session_pnl_xrp_estimate=float(
                data.get("session_pnl_xrp_estimate", _load_session_pnl_mtm(data))
            ),
            quote_intents=intents,
            engine_pid=data.get("engine_pid"),
            price_source=str(data.get("price_source", "xrpl_book_offers")),
            price_history=list(data.get("price_history", [])),
            market_condition=str(data.get("market_condition", "neutral")),
            market_condition_label=str(data.get("market_condition_label", "Neutral")),
            volatility_level=str(data.get("volatility_level", "moderate")),
            liquidity_level=str(data.get("liquidity_level", "moderate")),
            book_spread_pct=float(data.get("book_spread_pct", 0.0)),
            book_spread_status=str(data.get("book_spread_status", "unknown")),
            market_health_score=float(data.get("market_health_score", 0.0)),
            recommended_profile=str(data.get("recommended_profile", "safe")),
            recommendation_reason=str(data.get("recommendation_reason", "")),
            quote_decision_summary=str(data.get("quote_decision_summary", "")),
            inventory_label=str(data.get("inventory_label", "balanced")),
            mid_momentum_pct=float(data.get("mid_momentum_pct", 0.0)),
            spread_validation_ok=bool(data.get("spread_validation_ok", False)),
            spread_validation_summary=str(data.get("spread_validation_summary", "")),
            spread_validation_errors=list(data.get("spread_validation_errors", [])),
            spread_validation_lines=list(data.get("spread_validation_lines", [])),
            adverse_selection_tier=str(data.get("adverse_selection_tier", "none")),
            book_pressure_label=str(data.get("book_pressure_label", "balanced")),
            market_edge_met=bool(data.get("market_edge_met", True)),
            market_edge_pct=float(data.get("market_edge_pct", 0.0)),
            fill_quality_score=float(data.get("fill_quality_score", 100.0)),
            fill_quality_summary=str(data.get("fill_quality_summary", "")),
            rebalance_action=str(data.get("rebalance_action", "")),
            rebalance_summary=str(data.get("rebalance_summary", "")),
            pause_bids=bool(data.get("pause_bids", False)),
            pause_asks=bool(data.get("pause_asks", False)),
            inventory_mode=str(data.get("inventory_mode", "market_make")),
            effective_min_edge_pct=float(data.get("effective_min_edge_pct", 0.0)),
            edge_resolution_summary=str(data.get("edge_resolution_summary", "")),
            dynamic_min_edge_enabled=bool(data.get("dynamic_min_edge_enabled", False)),
            edge_strictness=float(data.get("edge_strictness", 1.0)),
            recent_decisions=list(data.get("recent_decisions", [])),
            last_error=data.get("last_error"),
            updated_utc=data.get("updated_utc"),
            quoting_policy_label=str(data.get("quoting_policy_label", "")),
            quoting_touch_mode=str(data.get("quoting_touch_mode", "")),
            toxic_fill_ratio=float(data.get("toxic_fill_ratio", 0.0)),
            toxic_fill_ratio_30s=float(data.get("toxic_fill_ratio_30s", 0.0)),
            mean_markout_30s_pct=float(data.get("mean_markout_30s_pct", 0.0)),
            g2_size_mult=float(data.get("g2_size_mult", 1.0)),
            g2_spread_mult=float(data.get("g2_spread_mult", 1.0)),
            g2_grade=str(data.get("g2_grade", "neutral")),
            g2_active=bool(data.get("g2_active", False)),
            g2_summary=str(data.get("g2_summary", "")),
            g4_size_mult=float(data.get("g4_size_mult", 1.0)),
            g4_grade=str(data.get("g4_grade", "neutral")),
            g4_active=bool(data.get("g4_active", False)),
            g4_summary=str(data.get("g4_summary", "")),
            competitor_intel=dict(data.get("competitor_intel") or {}),
            ws_as_version=str(data.get("ws_as_version", "")),
            as_mode=str(data.get("as_mode", "off")),
            as_reservation=data.get("as_reservation"),
            as_optimal_spread_pct=data.get("as_optimal_spread_pct"),
            as_gamma=data.get("as_gamma"),
            as_kappa=data.get("as_kappa"),
            ws_book_age_s=data.get("ws_book_age_s"),
            ws_message_count=int(data.get("ws_message_count", 0)),
            as_presence_pct=data.get("as_presence_pct"),
            as_protected=bool(data.get("as_protected", False)),
            offers_cancelled_session=int(data.get("offers_cancelled_session", 0)),
            offers_kept_session=int(data.get("offers_kept_session", 0)),
            fills_session=int(data.get("fills_session", 0)),
            cancel_per_fill=float(data.get("cancel_per_fill", 0.0)),
            book_poll_interval_seconds=int(data.get("book_poll_interval_seconds", 15)),
            full_quote_refresh_seconds=int(data.get("full_quote_refresh_seconds", 60)),
            last_cycle_full_refresh=bool(data.get("last_cycle_full_refresh", True)),
            join_touch_active=bool(data.get("join_touch_active", False)),
            quotes_at_touch=bool(data.get("quotes_at_touch", True)),
            worst_vs_touch_bps=float(data.get("worst_vs_touch_bps", 0.0)),
            quote_visibility_summary=str(data.get("quote_visibility_summary", "")),
        )
