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
from config.settings import BotConfig

if TYPE_CHECKING:
    from alpha.inventory.manager import InventoryManager
    from alpha.risk.engine import RiskEngine
    from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot

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
    MVP entry logic integrated with InventoryManager and RiskEngine.

    Limit buy below mid on weakness when edge, depth, and risk gates pass.
  """

    def __init__(
        self,
        config: BotConfig,
        *,
        inventory: Optional[InventoryManager] = None,
        risk: Optional[RiskEngine] = None,
    ) -> None:
        self._config = config
        self._inventory = inventory
        self._risk = risk

    def evaluate(
        self,
        *,
        inventory: InventorySnapshot,
        risk: RiskSnapshot,
        operator: Optional[OperatorSnapshot] = None,
        book: Optional[OrderBookSnapshot] = None,
        liquidity: Optional[LiquidityDepth] = None,
        pending_buy_count: int = 0,
        balances: Optional[BalanceSnapshot] = None,
        ta: Optional["TechnicalAnalysisSnapshot"] = None,
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

        if pending_buy_count >= self._config.alpha_max_pending_buys:
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason=f"max_pending_buys={self._config.alpha_max_pending_buys}",
            )

        if self._inventory is not None and self._inventory.allows_buy(inventory):
            return self._build_bid(
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
                balances=balances or (operator.balances if operator else None),
                ta=ta,
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
                balances=balances or (operator.balances if operator else None),
                ta=ta,
            )

        if inventory.buy_blocked_imbalance and inventory.deviation <= -self._config.alpha_weakness_deviation:
            logger.info(
                "decision_engine | buy_blocked_imbalance | dev=%+.3f",
                inventory.deviation,
            )

        if self._inventory is not None and self._inventory.allows_sell(inventory):
            return self._build_ask(
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
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

    def _edge_pct(self, *, mid: float, limit_price: float) -> float:
        if mid <= 0:
            return 0.0
        return max(0.0, ((mid - limit_price) / mid) * 100.0)

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

    def _ta_blocks_buy(self, ta: Optional["TechnicalAnalysisSnapshot"]) -> Optional[str]:
        cfg = self._config.alpha_technical_analysis
        if not cfg.enabled or ta is None or not ta.enabled:
            return None
        if not ta.entry_buy_allowed:
            return (
                f"ta_buy_blocked score={ta.buy_score:.2f}<{cfg.min_buy_score} "
                f"sell={ta.sell_score:.2f} bias={ta.bias}"
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

    def _build_bid(
        self,
        *,
        inventory: InventorySnapshot,
        risk: RiskSnapshot,
        book: OrderBookSnapshot,
        liquidity: Optional[LiquidityDepth],
        balances: Optional[BalanceSnapshot],
        ta: Optional["TechnicalAnalysisSnapshot"] = None,
    ) -> DecisionResult:
        blocked = self._ta_blocks_buy(ta)
        if blocked:
            return DecisionResult(action=DecisionAction.HOLD, reason=blocked)
        mid = book.mid
        assert mid is not None
        price = self._buy_limit_price(book)
        if price is None or price <= 0:
            return DecisionResult(action=DecisionAction.HOLD, reason="invalid_buy_price")

        edge = self._edge_pct(mid=mid, limit_price=price)
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
        balances: Optional[BalanceSnapshot],
        ta: Optional["TechnicalAnalysisSnapshot"] = None,
    ) -> DecisionResult:
        blocked = self._ta_blocks_sell(ta)
        if blocked:
            return DecisionResult(action=DecisionAction.HOLD, reason=blocked)
        if self._risk is not None:
            ok, msg = self._risk.validate_entry(risk)
            if not ok:
                return DecisionResult(action=DecisionAction.HOLD, reason=msg)

        mid = book.mid
        assert mid is not None
        best_ask = book.best_ask or mid
        offset = self._config.alpha_ask_offset_pct / 100.0
        price = round(best_ask * (1.0 + offset), 6)

        depth_cap = liquidity.bid_depth_xrp if liquidity else self._config.alpha_base_order_size_xrp
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
            return DecisionResult(action=DecisionAction.HOLD, reason="ask_size_below_min_after_caps")

        reason = (
            f"strength dev={inventory.deviation:+.3f} depth_cap={depth_cap:.2f} "
            f"alloc_xrp={inventory.xrp_allocation_pct:.1f}%"
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
        )
