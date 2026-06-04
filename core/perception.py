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
    size_multiplier: float = 1.0
    aggression: float = 1.0
    inventory_skew_strength: float = 1.0
    min_spread_floor_pct: float = 0.08
    defensive_widen_mult: float = 1.0
    book_pressure_sensitivity: float = 1.0
    min_edge_mult: float = 1.0  # legacy; edge target is min_edge_pct
    min_edge_pct: float = 0.10  # profile-owned minimum L1 edge target (%)
    # Tier 2 execution — queue preservation and refresh cadence (profile-owned)
    order_keep_price_tolerance_pct: float = 0.10
    order_keep_size_tolerance_xrp: float = 0.75
    book_poll_interval_seconds: int = 15
    full_quote_refresh_seconds: int = 60
    toxic_refresh_pause_ratio: float = 0.40
    toxic_no_touch_ratio: float = 0.20
    toxic_no_touch_exit_ratio: float = 0.15  # hysteresis: exit off-book below this
    toxic_pause_side_ratio: float = 0.18
    toxic_min_fills_for_gates: int = 8  # off-book / pause-side need this many fills
    markout_toxic_threshold_pct: float = 0.04


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

    def recent_newest_first(self, limit: int = 50) -> List[DecisionEvent]:
        """Most recent events first (for GUI display)."""
        return list(reversed(self.recent(limit)))

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
        description=(
            "Capital-first default — wide floors, half size in stress, strong inventory skew, "
            "pauses vulnerable side when hostile."
        ),
        spread_multiplier=1.45,
        volatility_sensitivity=1.35,
        liquidity_sensitivity=1.30,
        risk_multiplier=0.70,
        size_multiplier=0.65,
        aggression=0.50,
        inventory_skew_strength=1.45,
        min_spread_floor_pct=0.16,
        defensive_widen_mult=1.15,
        book_pressure_sensitivity=1.25,
        min_edge_mult=1.15,
        min_edge_pct=0.12,
        order_keep_price_tolerance_pct=0.12,
        order_keep_size_tolerance_xrp=1.0,
        book_poll_interval_seconds=20,
        full_quote_refresh_seconds=60,
        toxic_refresh_pause_ratio=0.22,
        toxic_no_touch_ratio=0.20,
        toxic_no_touch_exit_ratio=0.15,
        toxic_pause_side_ratio=0.18,
        toxic_min_fills_for_gates=8,
        markout_toxic_threshold_pct=0.04,
    ),
    "high_volatility": Profile(
        name="high_volatility",
        description=(
            "Volatility shock mode — spreads widen fast, size cut sharply, momentum protection "
            "ramps early."
        ),
        spread_multiplier=1.65,
        volatility_sensitivity=1.75,
        liquidity_sensitivity=1.10,
        risk_multiplier=0.60,
        size_multiplier=0.50,
        aggression=0.40,
        inventory_skew_strength=1.30,
        min_spread_floor_pct=0.20,
        defensive_widen_mult=1.25,
        book_pressure_sensitivity=1.35,
        min_edge_mult=1.25,
        min_edge_pct=0.13,
        order_keep_price_tolerance_pct=0.14,
        order_keep_size_tolerance_xrp=1.25,
        book_poll_interval_seconds=20,
        full_quote_refresh_seconds=90,
        toxic_refresh_pause_ratio=0.28,
        toxic_no_touch_ratio=0.18,
        toxic_pause_side_ratio=0.18,
        toxic_min_fills_for_gates=8,
        markout_toxic_threshold_pct=0.035,
    ),
    "thin_liquidity": Profile(
        name="thin_liquidity",
        description=(
            "Thin-book defense — extra liquidity penalty, book-pressure sensitive, smaller clips "
            "to limit adverse selection."
        ),
        spread_multiplier=1.55,
        volatility_sensitivity=1.15,
        liquidity_sensitivity=1.85,
        risk_multiplier=0.65,
        size_multiplier=0.55,
        aggression=0.45,
        inventory_skew_strength=1.35,
        min_spread_floor_pct=0.18,
        defensive_widen_mult=1.20,
        book_pressure_sensitivity=1.50,
        min_edge_mult=1.20,
        min_edge_pct=0.11,
        order_keep_price_tolerance_pct=0.13,
        order_keep_size_tolerance_xrp=1.0,
        book_poll_interval_seconds=20,
        full_quote_refresh_seconds=75,
        toxic_refresh_pause_ratio=0.30,
        toxic_no_touch_ratio=0.18,
        toxic_pause_side_ratio=0.17,
        toxic_min_fills_for_gates=8,
        markout_toxic_threshold_pct=0.04,
    ),
    "tight_spread": Profile(
        name="tight_spread",
        description=(
            "Competitive only in favorable regimes — tight floors, larger size, lighter skew; "
            "still blocked by spread validation and edge guards on mainnet."
        ),
        spread_multiplier=0.72,
        volatility_sensitivity=0.75,
        liquidity_sensitivity=0.70,
        risk_multiplier=1.15,
        size_multiplier=1.15,
        aggression=1.35,
        inventory_skew_strength=0.75,
        min_spread_floor_pct=0.05,
        defensive_widen_mult=0.95,
        book_pressure_sensitivity=0.85,
        min_edge_mult=0.85,
        min_edge_pct=0.08,
        order_keep_price_tolerance_pct=0.07,
        order_keep_size_tolerance_xrp=0.50,
        book_poll_interval_seconds=15,
        full_quote_refresh_seconds=45,
        toxic_refresh_pause_ratio=0.45,
        toxic_no_touch_ratio=0.22,
        toxic_pause_side_ratio=0.20,
        toxic_min_fills_for_gates=6,
        markout_toxic_threshold_pct=0.05,
    ),
    "profit_mode": Profile(
        name="profit_mode",
        description=(
            "Growth-first in calm, liquid books — tightest spreads, largest clips, lowest edge "
            "floor; use only when volatility is low and the book is tight."
        ),
        spread_multiplier=0.58,
        volatility_sensitivity=0.65,
        liquidity_sensitivity=0.60,
        risk_multiplier=1.28,
        size_multiplier=1.35,
        aggression=1.55,
        inventory_skew_strength=0.90,
        min_spread_floor_pct=0.04,
        defensive_widen_mult=0.88,
        book_pressure_sensitivity=0.72,
        min_edge_mult=0.72,
        min_edge_pct=0.05,
        order_keep_price_tolerance_pct=0.06,
        order_keep_size_tolerance_xrp=0.40,
        book_poll_interval_seconds=15,
        full_quote_refresh_seconds=30,
        toxic_refresh_pause_ratio=0.50,
        toxic_no_touch_ratio=0.25,
        toxic_pause_side_ratio=0.22,
        toxic_min_fills_for_gates=5,
        markout_toxic_threshold_pct=0.06,
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
        level_spreads[level] = max(profile.min_spread_floor_pct, adjusted)
    return level_spreads


from core.profile_edge import profile_min_edge_pct  # noqa: F401 — re-export for callers
