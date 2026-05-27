from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from core.perception import Profile, compute_effective_spreads_pct


@dataclass
class SpreadComputation:
    effective_spreads_pct: Dict[int, float]
    reason: str


class AvellanedaStrategy:
    """Custom spread engine for XRP/RLUSD market making."""

    def __init__(self, config) -> None:
        self.config = config

    def compute_spreads(
        self,
        *,
        volatility_pct: float,
        liquidity_score: float,
        profile: Profile,
    ) -> SpreadComputation:
        spreads = compute_effective_spreads_pct(
            base_spread_pct=self.config.base_spread * 100.0,
            level_spread_increment_pct=self.config.level_spread_increment * 100.0,
            level_count=self.config.order_levels,
            volatility_pct=volatility_pct,
            liquidity_score=liquidity_score,
            profile=profile,
        )
        reason = (
            f"Profile '{profile.name}' | vol={volatility_pct:.2f}% | "
            f"liq={liquidity_score:.2f} -> adjusted L1-L{self.config.order_levels}"
        )
        return SpreadComputation(effective_spreads_pct=spreads, reason=reason)
