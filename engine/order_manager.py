from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from config.settings import BotConfig
from core.quote_caps import effective_max_worse_than_touch_pct
from core.runtime_state import QuoteIntent
from risk.inventory_limits import cap_leg_size_for_inventory
from strategy.quote_decision import QuoteAdjustments

# Hard cap per side (percent of mid) so inventory skew cannot post absurd quotes.
_MAX_SIDE_SPREAD_PCT = 2.5


# Stay slightly inside spread-validation touch limits (fp + book drift between cycles).
_TOUCH_CLAMP_BUFFER_PCT = 0.03


def _clamp_quote_price(
    *,
    side: str,
    price: float,
    mid_price: float,
    best_bid: float | None,
    best_ask: float | None,
    max_worse_than_touch_pct: float,
    max_improve_touch_pct: float,
    max_half_spread_from_mid_pct: float,
) -> float:
    """Keep planned quotes inside spread-validation limits vs live book touch."""
    if price <= 0 or mid_price <= 0:
        return price

    half_cap = max_half_spread_from_mid_pct / 100.0
    if side == "ask":
        floor_mid = mid_price * (1.0 + 1e-9)
        ceiling_mid = mid_price * (1.0 + half_cap)
        price = min(max(price, floor_mid), ceiling_mid)
        if best_ask is not None and best_ask > 0:
            improve = max_improve_touch_pct / 100.0
            worse = max(0.0, max_worse_than_touch_pct - _TOUCH_CLAMP_BUFFER_PCT) / 100.0
            lo = best_ask * (1.0 - improve)
            hi = best_ask * (1.0 + worse)
            price = min(max(price, lo), hi)
        return price

    ceiling_mid = mid_price * (1.0 - 1e-9)
    floor_mid = mid_price * (1.0 - half_cap)
    price = max(min(price, ceiling_mid), floor_mid)
    if best_bid is not None and best_bid > 0:
        improve = max_improve_touch_pct / 100.0
        worse = max(0.0, max_worse_than_touch_pct - _TOUCH_CLAMP_BUFFER_PCT) / 100.0
        hi = best_bid * (1.0 + improve)
        lo = best_bid * (1.0 - worse)
        price = max(min(price, hi), lo)
    return price


@dataclass
class QuotePlan:
    intents: List[QuoteIntent]
    reason: str


class OrderManager:
    """Build layered bid/ask quote targets from mid price and effective spreads."""

    def __init__(self, config: BotConfig) -> None:
        self.config = config

    def build_quotes(
        self,
        *,
        mid_price: float,
        spreads_pct: dict[int, float],
        xrp_balance: float,
        rlusd_balance: float,
        adjustments: Optional[QuoteAdjustments] = None,
        best_bid: float | None = None,
        best_ask: float | None = None,
    ) -> QuotePlan:
        if mid_price <= 0:
            return QuotePlan(intents=[], reason="No valid mid price; skipping quote generation.")

        adj = adjustments or QuoteAdjustments()
        spendable_xrp = max(0.0, xrp_balance - self.config.xrp_reserve)
        min_size = max(0.0, self.config.min_order_size_xrp)
        risk_cap = max(min_size, self.config.effective_risk_capital_xrp(mid_price))

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

            spread_base = spreads_pct.get(level, self.config.base_spread * 100.0) / 100.0
            side_scale = 1.0 / max(1, level)
            bid_spread = min(
                _MAX_SIDE_SPREAD_PCT / 100.0,
                spread_base + (adj.bid_spread_add_pct * side_scale) / 100.0,
            )
            ask_spread = min(
                _MAX_SIDE_SPREAD_PCT / 100.0,
                spread_base + (adj.ask_spread_add_pct * side_scale) / 100.0,
            )

            size = min(configured_size, risk_cap) * adj.size_multiplier
            max_leg_pct = float(getattr(self.config, "max_leg_size_pct_of_capital", 0.12))
            if max_leg_pct > 0:
                size = min(size, max(risk_cap * max_leg_pct, min_size))
            bid_size = size * adj.bid_size_multiplier
            ask_size = size * adj.ask_size_multiplier

            overshoot_slack = float(getattr(self.config, "inventory_overshoot_slack", 0.03))
            inv_cap_kwargs = dict(
                xrp_balance=xrp_balance,
                rlusd_balance=rlusd_balance,
                mid_price=mid_price,
                target_xrp_ratio=float(self.config.inventory_target_xrp_ratio),
                xrp_reserve=float(self.config.xrp_reserve),
                inventory_mode=str(getattr(self.config, "inventory_mode", "market_make")),
                overshoot_slack=overshoot_slack,
                pause_bids=adj.pause_bids,
                pause_asks=adj.pause_asks,
                min_size=min_size,
            )
            bid_size = cap_leg_size_for_inventory(side="bid", size_xrp=bid_size, **inv_cap_kwargs)
            ask_size = cap_leg_size_for_inventory(side="ask", size_xrp=ask_size, **inv_cap_kwargs)

            bid_anchor = mid_price * (1.0 + adj.bid_anchor_shift_pct / 100.0)
            ask_anchor = mid_price * (1.0 + adj.ask_anchor_shift_pct / 100.0)
            bid_price = bid_anchor * (1.0 - bid_spread)
            ask_price = ask_anchor * (1.0 + ask_spread)

            if adj.join_touch and level == 1:
                backoff = max(0.0, adj.touch_backoff_pct) / 100.0
                if best_bid is not None and best_bid > 0:
                    bid_price = best_bid * (1.0 - backoff)
                if best_ask is not None and best_ask > 0:
                    ask_price = best_ask * (1.0 + backoff)

            max_worse = effective_max_worse_than_touch_pct(
                join_touch=adj.join_touch and level == 1,
                policy_cap_pct=float(getattr(adj, "max_worse_than_touch_pct", 0.0) or 0.0),
                max_quote_worse_than_touch_pct=float(
                    getattr(self.config, "max_quote_worse_than_touch_pct", 0.50)
                ),
                competitive_off_touch_max_worse_pct=float(
                    getattr(self.config, "competitive_off_touch_max_worse_pct", 0.12)
                ),
            )
            clamp_kwargs = dict(
                mid_price=mid_price,
                best_bid=best_bid,
                best_ask=best_ask,
                max_worse_than_touch_pct=max_worse,
                max_improve_touch_pct=float(
                    getattr(self.config, "max_quote_improve_touch_pct", 0.15)
                ),
                max_half_spread_from_mid_pct=float(
                    getattr(self.config, "max_half_spread_from_mid_pct", 1.0)
                ),
            )
            bid_price = _clamp_quote_price(side="bid", price=bid_price, **clamp_kwargs)
            ask_price = _clamp_quote_price(side="ask", price=ask_price, **clamp_kwargs)

            if quote_bids and not adj.pause_bids and bid_size >= min_size:
                bid_rlusd_needed = bid_size * bid_price
                if bid_rlusd_needed <= bid_budget_rlusd:
                    intents.append(
                        QuoteIntent(level=level, side="bid", price=bid_price, size_xrp=bid_size)
                    )
                    bid_budget_rlusd -= bid_rlusd_needed
                    bid_levels += 1
                else:
                    skipped += 1
            elif quote_bids and not adj.pause_bids:
                skipped += 1
            elif quote_bids and adj.pause_bids:
                skipped += 1
            else:
                skipped += 1

            if not adj.pause_asks and ask_size >= min_size:
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
            elif adj.pause_asks:
                skipped += 1
            else:
                skipped += 1

        mode = "XRP-funded (asks/sell XRP)" if self.config.fund_with_xrp_only else "two-sided"
        note = (
            f"Generated {len(intents)} quotes ({mode}) from mid={mid_price:.6f} "
            f"RLUSD/XRP | inventory={adj.inventory_label}"
        )
        if adj.decision_summary:
            note += f" | {adj.decision_summary}"
        if skipped:
            note += f" ({skipped} legs skipped: size/balance/reserve/pause)"
        if self.config.fund_with_xrp_only and bid_levels == 0 and ask_levels > 0:
            note += " | bids off until you hold RLUSD"
        if adj.join_touch:
            note += " | join-touch L1 (queue at best bid/ask)"
        elif not adj.min_edge_met:
            note += " | min-edge guard active"

        return QuotePlan(intents=intents, reason=note)
