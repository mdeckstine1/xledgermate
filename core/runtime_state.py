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
    active_profile: str = "safe"
    mid_price: Optional[float] = None
    volatility_pct: float = 0.0
    liquidity_score: float = 0.0
    effective_spreads_pct: Dict[int, float] = field(default_factory=dict)
    balance_xrp: float = 0.0
    open_offers_count: int = 0
    quote_intents: List[QuoteIntent] = field(default_factory=list)
    recent_decisions: List[Dict[str, str]] = field(default_factory=list)
    last_error: Optional[str] = None
    updated_utc: Optional[str] = None

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
            active_profile=data.get("active_profile", "safe"),
            mid_price=data.get("mid_price"),
            volatility_pct=float(data.get("volatility_pct", 0.0)),
            liquidity_score=float(data.get("liquidity_score", 0.0)),
            effective_spreads_pct={
                int(k): float(v) for k, v in (data.get("effective_spreads_pct") or {}).items()
            },
            balance_xrp=float(data.get("balance_xrp", 0.0)),
            open_offers_count=int(data.get("open_offers_count", 0)),
            quote_intents=intents,
            recent_decisions=list(data.get("recent_decisions", [])),
            last_error=data.get("last_error"),
            updated_utc=data.get("updated_utc"),
        )
