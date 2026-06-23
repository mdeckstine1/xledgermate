"""Decision engine — value accumulation entries (limit orders only)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

from alpha.types import (
    BalanceSnapshot,
    InventorySnapshot,
    LiquidityDepth,
    OperatorSnapshot,
    OrderBookSnapshot,
    RiskSnapshot,
)
from alpha.decision.reentry import ReentryGate
from config.settings import BotConfig

if TYPE_CHECKING:
    from alpha.decision.structure import MarketStructureSnapshot
    from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
    from alpha.inventory.manager import InventoryManager
    from alpha.risk.engine import RiskEngine

logger = logging.getLogger(__name__)


class DecisionAction(str, Enum):
    HOLD = "hold"
    PLACE_BID = "place_bid"
    PLACE_ASK = "place_ask"
    CANCEL = "cancel"


@dataclass(frozen=True)
class DecisionResult:
    action: DecisionAction
    reason: str
    side: Optional[str] = None
    size_xrp: Optional[float] = None
    price_rlusd_per_xrp: Optional[float] = None
    edge_pct: Optional[float] = None


class DecisionEngine:
    """
    Aggressive Bag Growth entry logic — deploy RLUSD on dips with TA confirmation.

    Limit buy below mid when inventory weakness + edge + depth + TA (if enabled) pass.
    Limit sell above mid on strength. Re-entry gate enforces patience after TP/SL exits.
    """

    def __init__(
        self,
        config: BotConfig,
        *,
        inventory: Optional["InventoryManager"] = None,
        risk: Optional["RiskEngine"] = None,
        reentry: Optional[ReentryGate] = None,
    ) -> None:
        self._config = config
        self._inventory = inventory
        self._risk = risk
        self._reentry = reentry

    def evaluate(
        self,
        *,
        inventory: InventorySnapshot,
        risk: RiskSnapshot,
        operator: Optional[OperatorSnapshot] = None,
        book: Optional[OrderBookSnapshot] = None,
        liquidity: Optional[LiquidityDepth] = None,
        pending_buy_count: int = 0,
        pending_sell_count: int = 0,
        balances: Optional[BalanceSnapshot] = None,
        ta: Optional["TechnicalAnalysisSnapshot"] = None,
        structure: Optional["MarketStructureSnapshot"] = None,
    ) -> DecisionResult:
        if not risk.trading_allowed:
            reason = "risk_trading_not_allowed"
            if risk.kill_switch_active:
                reason = f"kill_switch: {risk.kill_switch_reason or 'active'}"
            elif not risk.preflight_ready:
                reason = "preflight_not_ready"
            return DecisionResult(action=DecisionAction.HOLD, reason=reason)

        if book is None or book.mid is None or book.mid <= 0:
            return DecisionResult(action=DecisionAction.HOLD, reason="no_book_mid")

        if self._inventory is not None and self._inventory.allows_buy(inventory):
            return self._build_bid(
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
                pending_buy_count=pending_buy_count,
                balances=balances or (operator.balances if operator else None),
                ta=ta,
                structure=structure,
            )
        elif (
            self._inventory is None
            and inventory.deviation <= -self._config.alpha_weakness_deviation
            and not inventory.pause_bids
            and not inventory.buy_blocked_imbalance
        ):
            return self._build_bid(
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
                pending_buy_count=pending_buy_count,
                balances=balances or (operator.balances if operator else None),
                ta=ta,
                structure=structure,
            )

        if inventory.buy_blocked_imbalance and inventory.deviation <= -self._config.alpha_weakness_deviation:
            logger.info(
                "decision_engine | buy_blocked_imbalance | dev=%+.3f",
                inventory.deviation,
            )
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason=f"buy_blocked_imbalance dev={inventory.deviation:+.3f}",
            )

        if inventory.pause_bids and inventory.deviation <= -self._config.alpha_weakness_deviation:
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason=f"pause_bids dev={inventory.deviation:+.3f}",
            )

        if inventory.sell_blocked_imbalance and inventory.deviation >= self._config.alpha_strength_deviation:
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason=f"sell_blocked_imbalance dev={inventory.deviation:+.3f}",
            )

        if inventory.pause_asks and inventory.deviation >= self._config.alpha_strength_deviation:
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason=f"pause_asks dev={inventory.deviation:+.3f}",
            )

        if self._inventory is not None and self._inventory.allows_sell(inventory):
            return self._build_ask(
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
                pending_sell_count=pending_sell_count,
                balances=balances or (operator.balances if operator else None),
                ta=ta,
            )
        elif (
            self._inventory is None
            and inventory.deviation >= self._config.alpha_strength_deviation
            and not inventory.pause_asks
        ):
            return self._build_ask(
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
                pending_sell_count=pending_sell_count,
                balances=balances or (operator.balances if operator else None),
                ta=ta,
            )

        logger.info(
            "decision_engine | action=HOLD | dev=%+.3f | label=%s",
            inventory.deviation,
            inventory.label,
        )
        return DecisionResult(
            action=DecisionAction.HOLD,
            reason=f"balanced dev={inventory.deviation:+.3f}",
        )

    def _buy_limit_price(self, book: OrderBookSnapshot) -> Optional[float]:
        mid = book.mid
        if mid is None or mid <= 0:
            return None
        offset_pct = self._effective_buy_offset_pct()
        return round(mid * (1.0 - offset_pct / 100.0), 6)

    def _effective_buy_offset_pct(self) -> float:
        explicit = getattr(self._config, "alpha_buy_limit_offset_pct", 0.0)
        if explicit > 0:
            return explicit
        return self._config.alpha_bid_offset_pct

    def _buy_edge_pct(self, *, mid: float, limit_price: float) -> float:
        if mid <= 0:
            return 0.0
        return max(0.0, ((mid - limit_price) / mid) * 100.0)

    def _sell_edge_pct(self, *, mid: float, limit_price: float) -> float:
        if mid <= 0:
            return 0.0
        return max(0.0, ((limit_price - mid) / mid) * 100.0)

    def _cap_size_xrp(
        self,
        *,
        desired: float,
        depth_cap: float,
        mid: float,
        portfolio_xrp_equiv: float,
        side: str,
        inventory: InventorySnapshot,
        balances: Optional[BalanceSnapshot],
    ) -> float:
        min_size = self._config.min_order_size_xrp
        capital_xrp = self._config.effective_risk_capital_xrp(mid)
        leg_cap = capital_xrp * self._config.max_leg_size_pct_of_capital
        risk_cap = 0.0
        if portfolio_xrp_equiv > 0 and self._config.alpha_risk_per_trade_pct > 0:
            risk_cap = portfolio_xrp_equiv * (self._config.alpha_risk_per_trade_pct / 100.0)
        caps = [desired, depth_cap, leg_cap]
        if risk_cap > 0:
            caps.append(risk_cap)
        capped = min(c for c in caps if c > 0) if any(c > 0 for c in caps) else 0.0

        if self._inventory is not None and balances is not None:
            capped = self._inventory.cap_entry_size_xrp(
                side=side,
                size_xrp=capped,
                balances=balances,
                inventory=inventory,
            )

        if capped < min_size:
            return 0.0
        return round(capped, 4)

    def _ta_effective_min_buy(self) -> float:
        """Scale buy gate by alpha_ta_weight (0=advisory only, 1=full min_buy_score)."""
        cfg = self._config.alpha_technical_analysis
        weight = max(0.0, min(1.0, getattr(self._config, "alpha_ta_weight", 1.0)))
        if weight <= 0:
            return 0.0
        return cfg.min_buy_score * weight

    def _ta_blocks_buy(self, ta: Optional["TechnicalAnalysisSnapshot"]) -> Optional[str]:
        cfg = self._config.alpha_technical_analysis
        weight = getattr(self._config, "alpha_ta_weight", 1.0)
        if not cfg.enabled or weight <= 0:
            return None
        if ta is None or not ta.enabled:
            return "ta_warming_up — insufficient price history for buy gate"
        effective_min = self._ta_effective_min_buy()
        if ta.buy_score < effective_min:
            return (
                f"ta_buy_blocked score={ta.buy_score:.2f}<{effective_min:.2f} "
                f"weight={weight:.2f} sell={ta.sell_score:.2f} bias={ta.bias}"
            )
        return None

    def _ta_blocks_sell(self, ta: Optional["TechnicalAnalysisSnapshot"]) -> Optional[str]:
        cfg = self._config.alpha_technical_analysis
        if not cfg.enabled or ta is None or not ta.enabled:
            return None
        if not ta.entry_sell_allowed:
            return (
                f"ta_sell_blocked score={ta.sell_score:.2f}<{cfg.min_sell_score} "
                f"buy={ta.buy_score:.2f} bias={ta.bias}"
            )
        return None

    def _effective_sell_offset_pct(self) -> float:
        explicit = getattr(self._config, "alpha_sell_limit_offset_pct", 0.0)
        if explicit > 0:
            return explicit
        return self._config.alpha_ask_offset_pct

    def _sell_limit_price(self, book: OrderBookSnapshot) -> Optional[float]:
        mid = book.mid
        if mid is None or mid <= 0:
            return None
        offset_pct = self._effective_sell_offset_pct()
        return round(mid * (1.0 + offset_pct / 100.0), 6)

    def _build_bid(
        self,
        *,
        inventory: InventorySnapshot,
        risk: RiskSnapshot,
        book: OrderBookSnapshot,
        liquidity: Optional[LiquidityDepth],
        pending_buy_count: int = 0,
        balances: Optional[BalanceSnapshot],
        ta: Optional["TechnicalAnalysisSnapshot"] = None,
        structure: Optional["MarketStructureSnapshot"] = None,
    ) -> DecisionResult:
        if pending_buy_count >= self._config.alpha_max_pending_buys:
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason=f"max_pending_buys={self._config.alpha_max_pending_buys}",
            )

        mid = book.mid
        if self._reentry is not None and mid is not None and mid > 0:
            blocked = self._reentry.blocks_buy(
                inventory=inventory,
                mid=mid,
                ta=ta,
                structure=structure,
            )
            if blocked:
                return DecisionResult(action=DecisionAction.HOLD, reason=blocked)

        blocked = self._ta_blocks_buy(ta)
        if blocked:
            return DecisionResult(action=DecisionAction.HOLD, reason=blocked)
        mid = book.mid
        assert mid is not None
        price = self._buy_limit_price(book)
        if price is None or price <= 0:
            return DecisionResult(action=DecisionAction.HOLD, reason="invalid_buy_price")

        edge = self._buy_edge_pct(mid=mid, limit_price=price)
        if self._risk is not None:
            ok, msg = self._risk.validate_entry(risk, edge_pct=edge)
            if not ok:
                return DecisionResult(
                    action=DecisionAction.HOLD,
                    reason=msg,
                    edge_pct=edge,
                )
        elif edge < self._config.alpha_min_edge_threshold_pct:
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason=f"edge_below_threshold edge={edge:.3f}%",
                edge_pct=edge,
            )

        depth_cap = liquidity.ask_depth_xrp if liquidity else self._config.alpha_base_order_size_xrp
        if depth_cap < self._config.min_order_size_xrp:
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason=f"insufficient_ask_depth depth={depth_cap:.2f}",
                edge_pct=edge,
            )

        portfolio = inventory.portfolio_xrp_equiv or (balances.portfolio_xrp_equiv if balances else 0.0)
        desired = self._config.alpha_base_order_size_xrp * (1.0 + abs(inventory.deviation) * 2.0)
        size = self._cap_size_xrp(
            desired=desired,
            depth_cap=depth_cap,
            mid=mid,
            portfolio_xrp_equiv=portfolio,
            side="bid",
            inventory=inventory,
            balances=balances,
        )
        if size <= 0:
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason="bid_size_below_min_after_caps",
                edge_pct=edge,
            )

        reason = (
            f"weakness dev={inventory.deviation:+.3f} edge={edge:.3f}% "
            f"depth_cap={depth_cap:.2f} alloc_xrp={inventory.xrp_allocation_pct:.1f}%"
        )
        if ta is not None and ta.enabled:
            reason += f" ta_buy={ta.buy_score:.2f}"
        logger.info(
            "decision_engine | action=PLACE_BID | size=%.4f | price=%.6f | %s",
            size,
            price,
            reason,
        )
        return DecisionResult(
            action=DecisionAction.PLACE_BID,
            reason=reason,
            side="bid",
            size_xrp=size,
            price_rlusd_per_xrp=price,
            edge_pct=edge,
        )

    def _build_ask(
        self,
        *,
        inventory: InventorySnapshot,
        risk: RiskSnapshot,
        book: OrderBookSnapshot,
        liquidity: Optional[LiquidityDepth],
        pending_sell_count: int = 0,
        balances: Optional[BalanceSnapshot],
        ta: Optional["TechnicalAnalysisSnapshot"] = None,
    ) -> DecisionResult:
        if pending_sell_count >= self._config.alpha_max_pending_sells:
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason=f"max_pending_sells={self._config.alpha_max_pending_sells}",
            )
        blocked = self._ta_blocks_sell(ta)
        if blocked:
            return DecisionResult(action=DecisionAction.HOLD, reason=blocked)
        mid = book.mid
        assert mid is not None
        price = self._sell_limit_price(book)
        if price is None or price <= 0:
            return DecisionResult(action=DecisionAction.HOLD, reason="invalid_sell_price")

        edge = self._sell_edge_pct(mid=mid, limit_price=price)
        if self._risk is not None:
            ok, msg = self._risk.validate_entry(risk, edge_pct=edge)
            if not ok:
                return DecisionResult(
                    action=DecisionAction.HOLD,
                    reason=msg,
                    edge_pct=edge,
                )
        elif edge < self._config.alpha_min_edge_threshold_pct:
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason=f"edge_below_threshold edge={edge:.3f}%",
                edge_pct=edge,
            )

        depth_cap = liquidity.bid_depth_xrp if liquidity else self._config.alpha_base_order_size_xrp
        if depth_cap < self._config.min_order_size_xrp:
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason=f"insufficient_bid_depth depth={depth_cap:.2f}",
                edge_pct=edge,
            )

        portfolio = inventory.portfolio_xrp_equiv or (balances.portfolio_xrp_equiv if balances else 0.0)
        desired = self._config.alpha_base_order_size_xrp * (1.0 + abs(inventory.deviation) * 2.0)
        size = self._cap_size_xrp(
            desired=desired,
            depth_cap=depth_cap,
            mid=mid,
            portfolio_xrp_equiv=portfolio,
            side="ask",
            inventory=inventory,
            balances=balances,
        )
        if size <= 0:
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason="ask_size_below_min_after_caps",
                edge_pct=edge,
            )

        reason = (
            f"strength dev={inventory.deviation:+.3f} edge={edge:.3f}% "
            f"depth_cap={depth_cap:.2f} alloc_xrp={inventory.xrp_allocation_pct:.1f}%"
        )
        if ta is not None and ta.enabled:
            reason += f" ta_sell={ta.sell_score:.2f}"
        logger.info(
            "decision_engine | action=PLACE_ASK | size=%.4f | price=%.6f | %s",
            size,
            price,
            reason,
        )
        return DecisionResult(
            action=DecisionAction.PLACE_ASK,
            reason=reason,
            side="ask",
            size_xrp=size,
            price_rlusd_per_xrp=price,
            edge_pct=edge,
        )
