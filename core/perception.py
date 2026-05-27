from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    spread_multiplier: float = 1.0
    volatility_sensitivity: float = 1.0
    liquidity_sensitivity: float = 1.0
    risk_multiplier: float = 1.0


@dataclass
class LiquidityMetrics:
    bid_depth_xrp: float = 0.0
    ask_depth_xrp: float = 0.0
    depth_imbalance: float = 0.0
    liquidity_score: float = 0.0
    estimated_time_to_fill_seconds: float = 0.0


@dataclass
class DecisionEvent:
    ts_utc: str
    category: str
    message: str


class DecisionLog:
    """Capped rolling decision log to keep memory bounded."""

    def __init__(self, max_entries: int = 200) -> None:
        self._entries: Deque[DecisionEvent] = deque(maxlen=max_entries)

    def add(self, category: str, message: str) -> None:
        event = DecisionEvent(
            ts_utc=datetime.now(tz=timezone.utc).isoformat(),
            category=category,
            message=message,
        )
        self._entries.append(event)

    def recent(self, limit: int = 20) -> List[DecisionEvent]:
        if limit <= 0:
            return []
        return list(self._entries)[-limit:]

    def __len__(self) -> int:
        return len(self._entries)


@dataclass
class BotPerception:
    active_profile: Profile
    risk_state: str = "normal"
    volatility_pct: float = 0.0
    liquidity: LiquidityMetrics = field(default_factory=LiquidityMetrics)
    effective_spreads_pct: Dict[int, float] = field(default_factory=dict)
    mid_price: Optional[float] = None
    last_updated_utc: Optional[str] = None

    def update_market_state(
        self,
        mid_price: float,
        volatility_pct: float,
        liquidity: LiquidityMetrics,
        effective_spreads_pct: Dict[int, float],
    ) -> None:
        self.mid_price = mid_price
        self.volatility_pct = max(0.0, volatility_pct)
        self.liquidity = liquidity
        self.effective_spreads_pct = dict(sorted(effective_spreads_pct.items()))
        self.last_updated_utc = datetime.now(tz=timezone.utc).isoformat()


BUILT_IN_PROFILES: Dict[str, Profile] = {
    "safe": Profile(
        name="safe",
        description="Conservative spreads with lower risk posture.",
        spread_multiplier=1.2,
        volatility_sensitivity=1.15,
        liquidity_sensitivity=1.15,
        risk_multiplier=0.9,
    ),
    "high_volatility": Profile(
        name="high_volatility",
        description="Aggressively widen spreads in unstable markets.",
        spread_multiplier=1.25,
        volatility_sensitivity=1.35,
        liquidity_sensitivity=1.0,
        risk_multiplier=0.8,
    ),
    "thin_liquidity": Profile(
        name="thin_liquidity",
        description="Protective widening when top-of-book depth is weak.",
        spread_multiplier=1.2,
        volatility_sensitivity=1.0,
        liquidity_sensitivity=1.4,
        risk_multiplier=0.85,
    ),
    "tight_spread": Profile(
        name="tight_spread",
        description="Tighter quoting for strong and stable conditions.",
        spread_multiplier=0.85,
        volatility_sensitivity=0.9,
        liquidity_sensitivity=0.85,
        risk_multiplier=1.15,
    ),
}


def get_profile(profile_name: str) -> Profile:
    key = (profile_name or "").strip().lower()
    return BUILT_IN_PROFILES.get(key, BUILT_IN_PROFILES["safe"])


def compute_effective_spreads_pct(
    *,
    base_spread_pct: float,
    level_spread_increment_pct: float,
    level_count: int,
    volatility_pct: float,
    liquidity_score: float,
    profile: Profile,
) -> Dict[int, float]:
    """
    Spread engine using base + volatility + liquidity + profile modifiers.
    Returns spreads as percentages by level (1-indexed).
    """
    liquidity_penalty = max(0.0, 1.0 - liquidity_score)
    volatility_component = volatility_pct * profile.volatility_sensitivity * 0.60
    liquidity_component = liquidity_penalty * profile.liquidity_sensitivity * 0.50

    level_spreads: Dict[int, float] = {}
    for level in range(1, level_count + 1):
        baseline = base_spread_pct + (level - 1) * level_spread_increment_pct
        adjusted = baseline * profile.spread_multiplier
        adjusted += volatility_component + liquidity_component
        level_spreads[level] = max(0.01, adjusted)
    return level_spreads
