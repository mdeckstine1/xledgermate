from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

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

        spendable_xrp = max(0.0, xrp_balance - self.config.xrp_reserve)
        min_size = max(0.0, self.config.min_order_size_xrp)
        risk_cap = max(min_size, self.config.risk_capital_xrp)

        total_value = xrp_balance + (rlusd_balance / mid_price if mid_price > 0 else 0.0)
        xrp_ratio = xrp_balance / total_value if total_value > 0 else 1.0
        skew = self.inventory_skew.get_skew_factor(xrp_ratio)

        # Bids buy XRP (lock RLUSD). Asks sell XRP (lock XRP).
        bid_budget_rlusd = rlusd_balance
        ask_budget_xrp = min(spendable_xrp, risk_cap)
        quote_bids = not self.config.fund_with_xrp_only or rlusd_balance > min_size

        intents: List[QuoteIntent] = []
        skipped = 0
        bid_levels = 0
        ask_levels = 0

        for level in range(1, self.config.order_levels + 1):
            configured_size = self.config.order_sizes[level - 1]
            if configured_size <= 0:
                skipped += 1
                continue

            spread = spreads_pct.get(level, self.config.base_spread * 100.0) / 100.0
            size = min(configured_size, risk_cap)

            bid_size = size * skew if self.inventory_skew.should_increase_ask_size(xrp_ratio) else size
            ask_size = size / skew if not self.inventory_skew.should_increase_ask_size(xrp_ratio) else size

            bid_price = mid_price * (1.0 - spread)
            ask_price = mid_price * (1.0 + spread)

            if quote_bids and bid_size >= min_size:
                bid_rlusd_needed = bid_size * bid_price
                if bid_rlusd_needed <= bid_budget_rlusd:
                    intents.append(
                        QuoteIntent(level=level, side="bid", price=bid_price, size_xrp=bid_size)
                    )
                    bid_budget_rlusd -= bid_rlusd_needed
                    bid_levels += 1
                else:
                    skipped += 1
            elif quote_bids:
                skipped += 1
            else:
                skipped += 1

            if ask_size >= min_size:
                remaining_asks = max(1, self.config.order_levels - ask_levels)
                capped_ask = min(ask_size, ask_budget_xrp / remaining_asks)
                if capped_ask >= min_size:
                    intents.append(
                        QuoteIntent(level=level, side="ask", price=ask_price, size_xrp=capped_ask)
                    )
                    ask_budget_xrp -= capped_ask
                    ask_levels += 1
                else:
                    skipped += 1
            else:
                skipped += 1

        mode = "XRP-funded (asks/sell XRP)" if self.config.fund_with_xrp_only else "two-sided"
        note = (
            f"Generated {len(intents)} quotes ({mode}) from mid={mid_price:.6f} "
            f"RLUSD/XRP skew={skew:.3f}"
        )
        if skipped:
            note += f" ({skipped} legs skipped: size/balance/reserve)"
        if self.config.fund_with_xrp_only and bid_levels == 0 and ask_levels > 0:
            note += " | bids off until you hold RLUSD"

        return QuotePlan(intents=intents, reason=note)
