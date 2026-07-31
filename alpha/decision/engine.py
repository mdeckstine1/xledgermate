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
from alpha.precision import price_decimals, round_rlusd_price
from config.settings import BotConfig

if TYPE_CHECKING:
    from alpha.decision.accumulation_regime import AccumulationKnobs, AccumulationRegimeSnapshot
    from alpha.decision.harvest_watch import HarvestKnobs, HarvestWatchSnapshot, DipDeployKnobs, DipDeploySnapshot
    from alpha.decision.reload_regime import ReloadKnobs, ReloadRegimeSnapshot
    from alpha.decision.drawdown_reload import DrawdownReloadKnobs, DrawdownReloadSnapshot
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
        self._accumulation: Optional["AccumulationRegimeSnapshot"] = None
        self._accumulation_knobs: Optional["AccumulationKnobs"] = None
        self._reload: Optional["ReloadRegimeSnapshot"] = None
        self._reload_knobs: Optional["ReloadKnobs"] = None
        self._harvest: Optional["HarvestWatchSnapshot"] = None
        self._harvest_knobs: Optional["HarvestKnobs"] = None
        self._harvest_reentry_pending: bool = False
        self._dip: Optional["DipDeploySnapshot"] = None
        self._dip_knobs: Optional["DipDeployKnobs"] = None
        self._drawdown: Optional["DrawdownReloadSnapshot"] = None
        self._drawdown_knobs: Optional["DrawdownReloadKnobs"] = None

    def set_accumulation(
        self,
        snapshot: Optional["AccumulationRegimeSnapshot"],
        knobs: Optional["AccumulationKnobs"],
    ) -> None:
        self._accumulation = snapshot
        self._accumulation_knobs = knobs

    def set_reload(
        self,
        snapshot: Optional["ReloadRegimeSnapshot"],
        knobs: Optional["ReloadKnobs"],
    ) -> None:
        self._reload = snapshot
        self._reload_knobs = knobs

    def set_harvest(
        self,
        snapshot: Optional["HarvestWatchSnapshot"],
        knobs: Optional["HarvestKnobs"],
        *,
        reentry_pending: bool = False,
    ) -> None:
        self._harvest = snapshot
        self._harvest_knobs = knobs
        self._harvest_reentry_pending = reentry_pending

    def set_dip_deploy(
        self,
        snapshot: Optional["DipDeploySnapshot"],
        knobs: Optional["DipDeployKnobs"],
    ) -> None:
        self._dip = snapshot
        self._dip_knobs = knobs

    def set_drawdown_reload(
        self,
        snapshot: Optional["DrawdownReloadSnapshot"],
        knobs: Optional["DrawdownReloadKnobs"],
    ) -> None:
        self._drawdown = snapshot
        self._drawdown_knobs = knobs

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

        bal = balances or (operator.balances if operator else None)
        reload_reason = self._reload_funding_allowed(
            inventory=inventory,
            book=book,
            balances=bal,
            pending_sell_count=pending_sell_count,
        )
        if reload_reason is not None:
            return self._build_ask(
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
                pending_sell_count=pending_sell_count,
                balances=bal,
                ta=ta,
                entry_mode="reload_funding",
                entry_reason=reload_reason,
            )

        drawdown_reason = self._drawdown_reload_allowed(
            inventory=inventory,
            book=book,
            balances=bal,
            pending_sell_count=pending_sell_count,
        )
        if drawdown_reason is not None:
            return self._build_ask(
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
                pending_sell_count=pending_sell_count,
                balances=bal,
                ta=ta,
                entry_mode="drawdown_reload",
                entry_reason=drawdown_reason,
            )

        reload_blocks = self._reload_blocks_accumulation(bal, book, pending_sell_count)

        reentry_reason = self._harvest_reentry_allowed(
            inventory=inventory,
            book=book,
            pending_buy_count=pending_buy_count,
        )
        if reentry_reason is not None:
            return self._build_bid(
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
                pending_buy_count=pending_buy_count,
                balances=balances or (operator.balances if operator else None),
                ta=ta,
                structure=structure,
                entry_mode="harvest_reentry",
                entry_reason=reentry_reason,
            )

        dip_reason = self._dip_deploy_allowed(
            inventory=inventory,
            book=book,
            pending_buy_count=pending_buy_count,
            balances=balances or (operator.balances if operator else None),
        )
        if dip_reason is not None:
            return self._build_bid(
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
                pending_buy_count=pending_buy_count,
                balances=balances or (operator.balances if operator else None),
                ta=ta,
                structure=structure,
                entry_mode="dip_deploy",
                entry_reason=dip_reason,
            )

        harvest_reason = self._harvest_trim_allowed(
            inventory=inventory,
            pending_sell_count=pending_sell_count,
        )
        if harvest_reason is not None:
            return self._build_ask(
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
                pending_sell_count=pending_sell_count,
                balances=bal,
                ta=ta,
                entry_mode="harvest_trim",
                entry_reason=harvest_reason,
            )

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
                entry_mode="weakness",
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
                entry_mode="weakness",
            )

        # P0: while heavy, trim/harvest before chase buys (bull_run / accum on a full bag).
        heavy_trim = self._try_strength_trim(
            inventory=inventory,
            risk=risk,
            book=book,
            liquidity=liquidity,
            pending_sell_count=pending_sell_count,
            balances=bal,
            ta=ta,
        )
        if heavy_trim is not None:
            return heavy_trim

        accumulation_reason = None if reload_blocks else self._accumulation_entry_allowed(
            inventory=inventory,
            book=book,
            ta=ta,
            structure=structure,
        )
        if accumulation_reason is not None:
            bid = self._build_bid(
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
                pending_buy_count=pending_buy_count,
                balances=balances or (operator.balances if operator else None),
                ta=ta,
                structure=structure,
                entry_mode="accumulation",
                entry_reason=accumulation_reason,
            )
            resolved = self._resolve_failed_bid(
                bid,
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
                pending_sell_count=pending_sell_count,
                balances=bal,
                ta=ta,
            )
            if resolved is not None:
                return resolved

        bull_run = None if reload_blocks else self._bull_run_entry_allowed(
            inventory=inventory,
            book=book,
            ta=ta,
            structure=structure,
        )
        if bull_run is not None:
            bid = self._build_bid(
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
                pending_buy_count=pending_buy_count,
                balances=balances or (operator.balances if operator else None),
                ta=ta,
                structure=structure,
                entry_mode="bull_run",
                entry_reason=bull_run,
            )
            resolved = self._resolve_failed_bid(
                bid,
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
                pending_sell_count=pending_sell_count,
                balances=bal,
                ta=ta,
            )
            if resolved is not None:
                return resolved

        if reload_blocks and self._accumulation is not None and self._accumulation.armed:
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason=(
                    f"reload_await_funding floor={getattr(self._reload, 'deploy_floor_xrp_equiv', 0):.0f} "
                    f"rlusd_xrp_equiv={getattr(self._reload, 'rlusd_xrp_equiv', 0):.1f}"
                ),
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

        # Stranded bag: overweight XRP + RLUSD below deploy floor must never look "balanced".
        # Force funding/strength asks so harvest-maximize loop can rebuild powder.
        stranded = self._stranded_powder_reason(
            inventory=inventory,
            book=book,
            balances=bal,
            pending_sell_count=pending_sell_count,
        )
        if stranded is not None:
            if stranded.startswith("stranded_await"):
                return DecisionResult(action=DecisionAction.HOLD, reason=stranded)
            return self._build_ask(
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
                pending_sell_count=pending_sell_count,
                balances=bal,
                ta=ta,
                entry_mode="reload_funding",
                entry_reason=stranded,
            )

        logger.info(
            "decision_engine | action=HOLD | dev=%+.3f | label=%s",
            inventory.deviation,
            inventory.label,
        )
        # Honest label: only call balanced when not powder-starved and not heavily long.
        reason = f"balanced dev={inventory.deviation:+.3f}"
        if inventory.deviation >= self._config.alpha_strength_deviation * 0.5:
            reason = f"hold_heavy dev={inventory.deviation:+.3f}"
        return DecisionResult(
            action=DecisionAction.HOLD,
            reason=reason,
        )

    def _is_inventory_heavy(self, inventory: InventorySnapshot) -> bool:
        return inventory.deviation >= self._config.alpha_strength_deviation

    def _try_strength_trim(
        self,
        *,
        inventory: InventorySnapshot,
        risk: RiskSnapshot,
        book: OrderBookSnapshot,
        liquidity: Optional[LiquidityDepth],
        pending_sell_count: int,
        balances: Optional[BalanceSnapshot],
        ta: Optional["TechnicalAnalysisSnapshot"],
    ) -> Optional[DecisionResult]:
        """When overweight, place strength asks before bull_run/accum chase buys."""
        if not self._is_inventory_heavy(inventory):
            return None
        if inventory.pause_asks or inventory.sell_blocked_imbalance:
            return None
        allows = False
        if self._inventory is not None:
            allows = self._inventory.allows_sell(inventory)
        else:
            allows = inventory.deviation >= self._config.alpha_strength_deviation
        if not allows:
            return None
        return self._build_ask(
            inventory=inventory,
            risk=risk,
            book=book,
            liquidity=liquidity,
            pending_sell_count=pending_sell_count,
            balances=balances,
            ta=ta,
            entry_mode="inventory_trim",
            entry_reason=f"heavy_prefer_trim dev={inventory.deviation:+.3f}",
        )

    def _resolve_failed_bid(
        self,
        bid: DecisionResult,
        *,
        inventory: InventorySnapshot,
        risk: RiskSnapshot,
        book: OrderBookSnapshot,
        liquidity: Optional[LiquidityDepth],
        pending_sell_count: int,
        balances: Optional[BalanceSnapshot],
        ta: Optional["TechnicalAnalysisSnapshot"],
    ) -> DecisionResult:
        """
        If a bid was built successfully, return it.
        If size/caps kill the bid while heavy, fall through to strength trim or honest hold.
        """
        if bid.action == DecisionAction.PLACE_BID:
            return bid
        reason = bid.reason or ""
        size_fail = reason in (
            "bid_size_below_min_after_caps",
            "insufficient_ask_depth",
        ) or reason.startswith("bid_size_below_min")
        if size_fail and self._is_inventory_heavy(inventory):
            trim = self._try_strength_trim(
                inventory=inventory,
                risk=risk,
                book=book,
                liquidity=liquidity,
                pending_sell_count=pending_sell_count,
                balances=balances,
                ta=ta,
            )
            if trim is not None and trim.action == DecisionAction.PLACE_ASK:
                trim_reason = (
                    f"heavy_no_bid_room→trim | was={reason} | "
                    f"dev={inventory.deviation:+.3f}"
                )
                return DecisionResult(
                    action=trim.action,
                    reason=trim_reason if not trim.reason else f"{trim_reason} | {trim.reason}",
                    side=trim.side,
                    size_xrp=trim.size_xrp,
                    price_rlusd_per_xrp=trim.price_rlusd_per_xrp,
                    edge_pct=trim.edge_pct,
                )
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason=(
                    f"heavy_no_bid_room dev={inventory.deviation:+.3f} "
                    f"bid_blocked={reason}"
                ),
                edge_pct=bid.edge_pct,
            )
        return bid

    def _stranded_powder_reason(
        self,
        *,
        inventory: InventorySnapshot,
        book: OrderBookSnapshot,
        balances: Optional[BalanceSnapshot],
        pending_sell_count: int,
    ) -> Optional[str]:
        """
        Overweight XRP with RLUSD under deploy floor → recover powder (never silent hold).

        Returns entry_reason for an ask, or stranded_await_* hold reason, or None if not stranded.
        """
        if balances is None or book.mid is None or book.mid <= 0:
            return None
        if inventory.pause_asks or inventory.sell_blocked_imbalance:
            return None
        # Only when at/above target (bag growth long, not RLUSD-heavy recovery buys).
        if inventory.deviation < 0:
            return None
        from alpha.decision.reload_regime import (
            deploy_floor_xrp_equiv,
            rlusd_deploy_xrp_equiv,
        )

        rlusd_xeq = rlusd_deploy_xrp_equiv(balances.rlusd, book.mid)
        floor = deploy_floor_xrp_equiv(self._config)
        if floor <= 0 or rlusd_xeq + 1e-9 >= floor:
            return None
        max_sells = max(1, int(self._config.alpha_max_pending_sells))
        shortfall = floor - rlusd_xeq
        if pending_sell_count >= max_sells:
            return (
                f"stranded_await_sell_fill rlusd_xeq={rlusd_xeq:.1f}<floor={floor:.0f} "
                f"pending_sells={pending_sell_count}"
            )
        return (
            f"stranded_powder rlusd_xeq={rlusd_xeq:.1f}<floor={floor:.0f} "
            f"shortfall={shortfall:.1f} dev={inventory.deviation:+.3f}"
        )

    def _bull_run_entry_allowed(
        self,
        *,
        inventory: InventorySnapshot,
        book: OrderBookSnapshot,
        ta: Optional["TechnicalAnalysisSnapshot"],
        structure: Optional["MarketStructureSnapshot"],
    ) -> Optional[str]:
        from alpha.decision.momentum_entry import evaluate_bull_run_entry

        mid = book.mid
        if mid is None or mid <= 0:
            return None
        snap = evaluate_bull_run_entry(
            self._config,
            inventory=inventory,
            mid=mid,
            structure=structure,
            ta=ta,
        )
        if snap.active and (self._harvest_pause_bids() or (self._dip_knobs is not None and self._dip_knobs.armed)):
            return None
        return snap.reason if snap.active else None

    def _reload_blocks_accumulation(
        self,
        balances: Optional[BalanceSnapshot],
        book: OrderBookSnapshot,
        pending_sell_count: int,
    ) -> bool:
        # Explicit off switch wins over snapshot hard-blocks (Maximize / Unassed).
        if not getattr(self._config, "alpha_reload_block_accumulation_until_funded", True):
            return False
        snap = self._reload
        if snap is not None and snap.blocks_accumulation:
            return True
        if balances is None or book.mid is None or book.mid <= 0:
            return False
        from alpha.decision.reload_regime import reload_blocks_accumulation_bids

        return reload_blocks_accumulation_bids(
            self._config,
            rlusd_balance=balances.rlusd,
            mid=book.mid,
            pending_funding_sells=pending_sell_count,
        )

    def _reload_funding_allowed(
        self,
        *,
        inventory: InventorySnapshot,
        book: OrderBookSnapshot,
        balances: Optional[BalanceSnapshot],
        pending_sell_count: int,
    ) -> Optional[str]:
        snap = self._reload
        knobs = self._reload_knobs
        if snap is None or knobs is None or not snap.entry_allowed or not knobs.armed:
            return None
        if inventory.pause_asks:
            return None
        if pending_sell_count >= knobs.max_pending_sells:
            return None
        if balances is None or book.mid is None or book.mid <= 0:
            return None
        reason = snap.reason or snap.detail or "reload_armed"
        if snap.signals:
            reason = f"reload_funding {'+'.join(snap.signals[:3])} | {reason}"
        logger.info("reload_regime | entry | %s", reason)
        return reason

    def _drawdown_reload_allowed(
        self,
        *,
        inventory: InventorySnapshot,
        book: OrderBookSnapshot,
        balances: Optional[BalanceSnapshot],
        pending_sell_count: int,
    ) -> Optional[str]:
        snap = self._drawdown
        knobs = self._drawdown_knobs
        if snap is None or knobs is None or not snap.entry_allowed or not knobs.armed:
            return None
        if inventory.pause_asks:
            return None
        if pending_sell_count >= knobs.max_pending_sells:
            return None
        if balances is None or book.mid is None or book.mid <= 0:
            return None
        if knobs.target_sell_xrp < self._config.min_order_size_xrp * 0.5:
            return None
        reason = snap.reason or snap.detail or "drawdown_armed"
        if snap.signals:
            reason = f"drawdown_reload {'+'.join(snap.signals[:3])} | {reason}"
        logger.info("drawdown_reload | entry | %s", reason)
        return reason

    def _harvest_pause_bids(self) -> bool:
        knobs = self._harvest_knobs
        return knobs is not None and knobs.pause_accumulation_bids

    def _harvest_trim_allowed(
        self,
        *,
        inventory: InventorySnapshot,
        pending_sell_count: int,
    ) -> Optional[str]:
        snap = self._harvest
        knobs = self._harvest_knobs
        if snap is None or knobs is None or not knobs.execute or not knobs.armed:
            return None
        if snap.phase not in ("armed", "executing") or not snap.entry_allowed:
            return None
        if inventory.pause_asks:
            return None
        if pending_sell_count >= knobs.max_pending_sells:
            return None
        reason = snap.reason or snap.detail or "harvest_armed"
        if snap.signals:
            reason = f"harvest_trim {'+'.join(snap.signals[:3])} | {reason}"
        logger.info("harvest_watch | entry | %s", reason)
        return reason

    def _harvest_reentry_allowed(
        self,
        *,
        inventory: InventorySnapshot,
        book: OrderBookSnapshot,
        pending_buy_count: int,
    ) -> Optional[str]:
        knobs = self._harvest_knobs
        if not self._harvest_reentry_pending or knobs is None or not knobs.reentry_enabled:
            return None
        if inventory.pause_bids or inventory.buy_blocked_imbalance:
            return None
        max_pending = int(self._config.alpha_max_pending_buys)
        if pending_buy_count >= max_pending:
            return None
        mid = book.mid
        if mid is None or mid <= 0:
            return None
        reason = "harvest_reentry bracketed buy after trim fill"
        logger.info("harvest_watch | reentry | %s", reason)
        return reason

    def _dip_deploy_allowed(
        self,
        *,
        inventory: InventorySnapshot,
        book: OrderBookSnapshot,
        pending_buy_count: int,
        balances: Optional[BalanceSnapshot],
    ) -> Optional[str]:
        snap = self._dip
        knobs = self._dip_knobs
        if snap is None or knobs is None or not knobs.execute or not knobs.armed:
            return None
        if snap.phase != "armed" or not snap.entry_allowed:
            return None
        if inventory.pause_bids or inventory.buy_blocked_imbalance:
            return None
        if balances is None or balances.rlusd <= 0:
            return None
        max_pending = int(self._config.alpha_max_pending_buys)
        if pending_buy_count >= max_pending:
            return None
        mid = book.mid
        if mid is None or mid <= 0:
            return None
        reason = snap.reason or snap.detail or "dip_armed"
        if snap.signals:
            reason = f"dip_deploy {'+'.join(snap.signals[:3])} | {reason}"
        logger.info("dip_deploy | entry | %s", reason)
        return reason

    def _accumulation_entry_allowed(
        self,
        *,
        inventory: InventorySnapshot,
        book: OrderBookSnapshot,
        ta: Optional["TechnicalAnalysisSnapshot"],
        structure: Optional["MarketStructureSnapshot"],
    ) -> Optional[str]:
        snap = self._accumulation
        knobs = self._accumulation_knobs
        if snap is None or knobs is None or not snap.entry_allowed or not knobs.armed:
            return None
        if self._harvest_pause_bids():
            return None
        if self._dip_knobs is not None and self._dip_knobs.armed:
            return None
        if inventory.pause_bids or inventory.buy_blocked_imbalance:
            return None
        if inventory.deviation > knobs.max_deviation:
            return None
        mid = book.mid
        if mid is None or mid <= 0:
            return None
        reason = snap.reason or snap.detail or "accumulation_armed"
        if snap.signals:
            reason = f"accumulation {'+'.join(snap.signals[:3])} | {reason}"
        logger.info("accumulation_regime | entry | %s", reason)
        return reason

    def _buy_limit_price(
        self,
        book: OrderBookSnapshot,
        *,
        entry_mode: str = "weakness",
    ) -> Optional[float]:
        mid = book.mid
        if mid is None or mid <= 0:
            return None
        if entry_mode == "bull_run":
            from alpha.decision.momentum_entry import bull_run_buy_offset_pct

            offset_pct = bull_run_buy_offset_pct(self._config)
        elif entry_mode == "accumulation" and self._accumulation_knobs is not None:
            offset_pct = self._accumulation_knobs.buy_offset_pct
        elif entry_mode == "harvest_reentry" and self._harvest_knobs is not None:
            offset_pct = self._harvest_knobs.reentry_buy_offset_pct
        elif entry_mode == "dip_deploy" and self._dip_knobs is not None:
            offset_pct = self._dip_knobs.buy_offset_pct
        else:
            offset_pct = self._effective_buy_offset_pct()
        dec = price_decimals(self._config)
        raw = mid * (1.0 - offset_pct / 100.0)
        return round_rlusd_price(raw, dec, direction="down")

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
        risk_per_trade_pct: float | None = None,
        skip_inventory_cap: bool = False,
    ) -> float:
        min_size = self._config.min_order_size_xrp
        capital_xrp = self._config.effective_risk_capital_xrp(
            mid,
            portfolio_xrp_equiv=portfolio_xrp_equiv,
        )
        leg_cap = capital_xrp * self._config.max_leg_size_pct_of_capital
        risk_cap = 0.0
        pct = risk_per_trade_pct if risk_per_trade_pct is not None else self._config.alpha_risk_per_trade_pct
        if portfolio_xrp_equiv > 0 and pct > 0:
            risk_cap = portfolio_xrp_equiv * (pct / 100.0)
        caps = [desired, depth_cap, leg_cap]
        if risk_cap > 0:
            caps.append(risk_cap)
        capped = min(c for c in caps if c > 0) if any(c > 0 for c in caps) else 0.0

        if self._inventory is not None and balances is not None and not skip_inventory_cap:
            capped = self._inventory.cap_entry_size_xrp(
                side=side,
                size_xrp=capped,
                balances=balances,
                inventory=inventory,
                risk_per_trade_pct=pct if risk_per_trade_pct is not None else None,
            )

        if capped < min_size:
            return 0.0
        return round(capped, 4)

    def _ta_effective_min_buy(self, *, entry_mode: str = "weakness") -> float:
        """Scale buy gate by alpha_ta_weight (0=advisory only, 1=full min_buy_score)."""
        cfg = self._config.alpha_technical_analysis
        weight = max(0.0, min(1.0, getattr(self._config, "alpha_ta_weight", 1.0)))
        knobs = self._accumulation_knobs
        if entry_mode == "accumulation" and knobs is not None and knobs.armed:
            weight *= max(0.0, min(1.0, knobs.ta_weight_factor))
        if entry_mode == "dip_deploy" and self._dip_knobs is not None and self._dip_knobs.armed:
            weight *= max(0.0, min(1.0, self._dip_knobs.ta_weight_factor))
        if weight <= 0:
            return 0.0
        return cfg.min_buy_score * weight

    def _ta_effective_min_sell(self) -> float:
        """Scale sell gate by alpha_ta_weight (0=advisory only, 1=full min_sell_score)."""
        cfg = self._config.alpha_technical_analysis
        weight = max(0.0, min(1.0, getattr(self._config, "alpha_ta_weight", 1.0)))
        if weight <= 0:
            return 0.0
        return cfg.min_sell_score * weight

    def _ta_blocks_buy(
        self,
        ta: Optional["TechnicalAnalysisSnapshot"],
        *,
        mid: Optional[float] = None,
        structure: Optional["MarketStructureSnapshot"] = None,
        entry_mode: str = "weakness",
    ) -> Optional[str]:
        cfg = self._config.alpha_technical_analysis
        weight = getattr(self._config, "alpha_ta_weight", 1.0)
        if not cfg.enabled or weight <= 0:
            return None
        if ta is None or not ta.enabled:
            return "ta_warming_up — insufficient price history for buy gate"
        effective_min = self._ta_effective_min_buy(entry_mode=entry_mode)
        if ta.buy_score < effective_min:
            return (
                f"ta_buy_blocked score={ta.buy_score:.2f}<{effective_min:.2f} "
                f"weight={weight:.2f} sell={ta.sell_score:.2f} bias={ta.bias}"
            )
        if ta.bias == "bearish":
            from alpha.decision.tape_participation import tape_participation_waives_bearish_buy_block

            ref_mid = mid if mid is not None else (structure.mid if structure else 0.0)
            if tape_participation_waives_bearish_buy_block(
                self._config,
                mid=ref_mid,
                structure=structure,
                ta=ta,
            ):
                return None
            return (
                f"ta_buy_blocked bearish bias={ta.bias} "
                f"buy={ta.buy_score:.2f} sell={ta.sell_score:.2f}"
            )
        return None

    def _ta_blocks_sell(
        self,
        ta: Optional["TechnicalAnalysisSnapshot"],
        *,
        entry_mode: str = "strength",
    ) -> Optional[str]:
        if (
            entry_mode == "harvest_trim"
            and self._harvest_knobs is not None
            and self._harvest_knobs.bypass_ta_bullish_defer
        ):
            return None
        # Inventory rebalance toward target must not stall forever on bullish TA.
        if entry_mode == "inventory_trim":
            return None
        cfg = self._config.alpha_technical_analysis
        weight = getattr(self._config, "alpha_ta_weight", 1.0)
        if not cfg.enabled or weight <= 0:
            return None
        if ta is None or not ta.enabled:
            return None
        effective_min = self._ta_effective_min_sell()
        if ta.sell_score < effective_min:
            return (
                f"ta_sell_blocked score={ta.sell_score:.2f}<{effective_min:.2f} "
                f"weight={weight:.2f} buy={ta.buy_score:.2f} bias={ta.bias}"
            )
        if ta.bias == "bullish" and ta.buy_score >= effective_min:
            if entry_mode == "reload_funding" and getattr(
                self._config, "alpha_reload_bypass_ta_bullish_defer", True
            ):
                return None
            if entry_mode == "drawdown_reload" and getattr(
                self._config, "alpha_drawdown_reload_bypass_ta_bullish_defer", True
            ):
                return None
            if (
                entry_mode == "harvest_trim"
                and self._harvest_knobs is not None
                and self._harvest_knobs.bypass_ta_bullish_defer
            ):
                return None
            return (
                f"ta_sell_deferred bullish bias={ta.bias} "
                f"buy={ta.buy_score:.2f}>={effective_min:.2f} — hold XRP strength"
            )
        return None

    def _sell_limit_price(
        self,
        book: OrderBookSnapshot,
        *,
        entry_mode: str = "strength",
    ) -> Optional[float]:
        mid = book.mid
        if mid is None or mid <= 0:
            return None
        if entry_mode == "reload_funding" and self._reload_knobs is not None:
            offset_pct = self._reload_knobs.sell_offset_pct
        elif entry_mode == "drawdown_reload" and self._drawdown_knobs is not None:
            offset_pct = self._drawdown_knobs.sell_offset_pct
        elif entry_mode == "harvest_trim" and self._harvest_knobs is not None:
            offset_pct = self._harvest_knobs.sell_offset_pct
        else:
            offset_pct = self._effective_sell_offset_pct()
        dec = price_decimals(self._config)
        raw = mid * (1.0 + offset_pct / 100.0)
        return round_rlusd_price(raw, dec, direction="up")

    def _effective_sell_offset_pct(self) -> float:
        explicit = getattr(self._config, "alpha_sell_limit_offset_pct", 0.0)
        if explicit > 0:
            return explicit
        return self._config.alpha_ask_offset_pct

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
        entry_mode: str = "weakness",
        entry_reason: str = "",
    ) -> DecisionResult:
        knobs = self._accumulation_knobs
        max_pending = (
            knobs.max_pending_buys
            if entry_mode == "accumulation" and knobs is not None and knobs.armed
            else self._config.alpha_max_pending_buys
        )
        if pending_buy_count >= max_pending:
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason=f"max_pending_buys={max_pending}",
            )

        mid = book.mid
        if self._reentry is not None and mid is not None and mid > 0:
            blocked = self._reentry.blocks_buy(
                inventory=inventory,
                mid=mid,
                ta=ta,
                structure=structure,
                momentum_chase=(entry_mode == "bull_run"),
                accumulation_chase=entry_mode in ("accumulation", "harvest_reentry", "dip_deploy"),
            )
            if blocked:
                return DecisionResult(action=DecisionAction.HOLD, reason=blocked)

        blocked = self._ta_blocks_buy(ta, mid=mid, structure=structure, entry_mode=entry_mode)
        if blocked:
            return DecisionResult(action=DecisionAction.HOLD, reason=blocked)
        mid = book.mid
        assert mid is not None
        price = self._buy_limit_price(book, entry_mode=entry_mode)
        if price is None or price <= 0:
            return DecisionResult(action=DecisionAction.HOLD, reason="invalid_buy_price")

        edge = self._buy_edge_pct(mid=mid, limit_price=price)
        min_edge = self._config.alpha_min_edge_threshold_pct
        if entry_mode == "accumulation" and knobs is not None and knobs.armed:
            min_edge = min(min_edge, knobs.min_edge_pct)
        elif entry_mode == "harvest_reentry" and self._accumulation_knobs is not None:
            min_edge = min(min_edge, self._accumulation_knobs.min_edge_pct)
        elif entry_mode == "dip_deploy":
            min_edge = min(min_edge, float(self._config.alpha_min_edge_threshold_pct) * 0.75)
        if self._risk is not None:
            ok, msg = self._risk.validate_entry(risk, edge_pct=edge)
            if not ok:
                return DecisionResult(
                    action=DecisionAction.HOLD,
                    reason=msg,
                    edge_pct=edge,
                )
        elif edge < min_edge:
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
        risk_pct = self._config.alpha_risk_per_trade_pct
        if entry_mode == "accumulation" and knobs is not None and knobs.armed:
            risk_pct = knobs.risk_per_trade_pct
        elif entry_mode == "dip_deploy" and self._dip_knobs is not None:
            risk_pct = self._dip_knobs.risk_per_trade_pct
        size = self._cap_size_xrp(
            desired=desired,
            depth_cap=depth_cap,
            mid=mid,
            portfolio_xrp_equiv=portfolio,
            side="bid",
            inventory=inventory,
            balances=balances,
            risk_per_trade_pct=risk_pct,
            skip_inventory_cap=(entry_mode in ("harvest_reentry", "dip_deploy")),
        )
        if size <= 0:
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason="bid_size_below_min_after_caps",
                edge_pct=edge,
            )

        reason = (
            f"{entry_mode} dev={inventory.deviation:+.3f} edge={edge:.3f}% "
            f"depth_cap={depth_cap:.2f} alloc_xrp={inventory.xrp_allocation_pct:.1f}%"
        )
        if entry_reason:
            reason = f"{entry_reason} | {reason}"
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
        entry_mode: str = "strength",
        entry_reason: str = "",
    ) -> DecisionResult:
        rknobs = self._reload_knobs
        hknobs = self._harvest_knobs
        dknobs = self._drawdown_knobs
        if entry_mode == "reload_funding" and rknobs is not None and rknobs.armed:
            max_pending = rknobs.max_pending_sells
        elif entry_mode == "drawdown_reload" and dknobs is not None and dknobs.armed:
            max_pending = dknobs.max_pending_sells
        elif entry_mode == "harvest_trim" and hknobs is not None:
            max_pending = hknobs.max_pending_sells
        else:
            max_pending = self._config.alpha_max_pending_sells
        if pending_sell_count >= max_pending:
            return DecisionResult(
                action=DecisionAction.HOLD,
                reason=f"max_pending_sells={max_pending}",
            )
        blocked = self._ta_blocks_sell(ta, entry_mode=entry_mode)
        if blocked:
            return DecisionResult(action=DecisionAction.HOLD, reason=blocked)
        mid = book.mid
        assert mid is not None
        price = self._sell_limit_price(book, entry_mode=entry_mode)
        if price is None or price <= 0:
            return DecisionResult(action=DecisionAction.HOLD, reason="invalid_sell_price")

        edge = self._sell_edge_pct(mid=mid, limit_price=price)
        min_edge = self._config.alpha_min_edge_threshold_pct
        if entry_mode == "reload_funding" and rknobs is not None and rknobs.armed:
            min_edge = min(min_edge, rknobs.min_edge_pct)
        elif entry_mode == "drawdown_reload" and dknobs is not None and dknobs.armed:
            min_edge = min(min_edge, dknobs.min_edge_pct)
        if self._risk is not None:
            ok, msg = self._risk.validate_entry(risk, edge_pct=edge)
            if not ok:
                return DecisionResult(
                    action=DecisionAction.HOLD,
                    reason=msg,
                    edge_pct=edge,
                )
        elif edge < min_edge:
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
        if entry_mode == "reload_funding" and balances is not None and self._reload is not None:
            from alpha.decision.reload_regime import compute_reload_sell_size_xrp

            desired = compute_reload_sell_size_xrp(
                self._config,
                shortfall_xrp_equiv=self._reload.shortfall_xrp_equiv,
                balances=balances,
                inventory=inventory,
            )
        elif entry_mode == "drawdown_reload" and balances is not None and dknobs is not None:
            desired = float(dknobs.target_sell_xrp)
        elif entry_mode == "harvest_trim" and hknobs is not None:
            from alpha.decision.harvest_watch import compute_harvest_trim_size_xrp

            desired = compute_harvest_trim_size_xrp(
                self._config,
                portfolio_xrp_equiv=portfolio,
                trim_risk_pct=hknobs.trim_risk_pct,
            )
        else:
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
            f"{entry_mode} dev={inventory.deviation:+.3f} edge={edge:.3f}% "
            f"depth_cap={depth_cap:.2f} alloc_xrp={inventory.xrp_allocation_pct:.1f}%"
        )
        if entry_reason:
            reason = f"{entry_reason} | {reason}"
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
