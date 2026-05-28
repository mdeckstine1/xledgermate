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
    cycle_count: int = 0
    offers_placed_last_cycle: int = 0
    last_execution_summary: str = ""
    session_baseline_xrp: Optional[float] = None
    session_baseline_rlusd: Optional[float] = None
    session_pnl_xrp_estimate: float = 0.0
    quote_intents: List[QuoteIntent] = field(default_factory=list)
    recent_decisions: List[Dict[str, str]] = field(default_factory=list)
    last_error: Optional[str] = None
    updated_utc: Optional[str] = None
    engine_pid: Optional[int] = None
    price_source: str = "xrpl_book_offers"
    price_history: List[Dict[str, Any]] = field(default_factory=list)

    def touch(self) -> None:
        self.updated_utc = datetime.now(tz=timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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
            cycle_count=int(data.get("cycle_count", 0)),
            offers_placed_last_cycle=int(data.get("offers_placed_last_cycle", 0)),
            last_execution_summary=str(data.get("last_execution_summary", "")),
            session_baseline_xrp=data.get("session_baseline_xrp"),
            session_baseline_rlusd=data.get("session_baseline_rlusd"),
            session_pnl_xrp_estimate=float(data.get("session_pnl_xrp_estimate", 0.0)),
            quote_intents=intents,
            engine_pid=data.get("engine_pid"),
            price_source=str(data.get("price_source", "xrpl_book_offers")),
            price_history=list(data.get("price_history", [])),
            recent_decisions=list(data.get("recent_decisions", [])),
            last_error=data.get("last_error"),
            updated_utc=data.get("updated_utc"),
        )
