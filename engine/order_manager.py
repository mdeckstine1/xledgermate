from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from config.settings import BotConfig
from core.runtime_state import QuoteIntent
from risk.inventory import InventorySkew


@dataclass
class QuotePlan:
    intents: List[QuoteIntent]
    reason: str


class OrderManager:
    """Build layered bid/ask quote targets from mid price and effective spreads."""

    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.inventory_skew = InventorySkew(target_xrp_ratio=config.inventory_target_xrp_ratio)

    def build_quotes(
        self,
        *,
        mid_price: float,
        spreads_pct: Dict[int, float],
        xrp_balance: float,
        rlusd_balance: float,
    ) -> QuotePlan:
        if mid_price <= 0:
            return QuotePlan(intents=[], reason="No valid mid price; skipping quote generation.")

        total_value = xrp_balance + (rlusd_balance / mid_price if mid_price > 0 else 0.0)
        xrp_ratio = xrp_balance / total_value if total_value > 0 else 0.5
        skew = self.inventory_skew.get_skew_factor(xrp_ratio)

        intents: List[QuoteIntent] = []
        for level in range(1, self.config.order_levels + 1):
            spread = spreads_pct.get(level, self.config.base_spread * 100.0) / 100.0
            size = self.config.order_sizes[level - 1]
            bid_size = size * skew if self.inventory_skew.should_increase_ask_size(xrp_ratio) else size
            ask_size = size / skew if not self.inventory_skew.should_increase_ask_size(xrp_ratio) else size

            bid_price = mid_price * (1.0 - spread)
            ask_price = mid_price * (1.0 + spread)
            intents.append(QuoteIntent(level=level, side="bid", price=bid_price, size_xrp=bid_size))
            intents.append(QuoteIntent(level=level, side="ask", price=ask_price, size_xrp=ask_size))

        return QuotePlan(
            intents=intents,
            reason=(
                f"Generated {len(intents)} quotes from mid={mid_price:.6f} "
                f"with inventory skew={skew:.3f}"
            ),
        )
