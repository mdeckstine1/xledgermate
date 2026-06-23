"""Order manager — application-level bracket (TP + SL) with OCO."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from alpha.decision.structure import CandleData

from alpha.dry_run import DryRunGuard
from alpha.ledger.interface import LedgerInterface
from alpha.orders.bracket import compute_bracket_prices, normalize_partial_fill_mode
from alpha.orders.state import BracketStateStore
from alpha.orders.trailing import TrailingEvalResult, evaluate_trailing
from alpha.orders.types import (
    BracketFillEvent,
    BracketLeg,
    BracketLegRole,
    BracketLifecycleState,
    BracketMode,
    BracketRecord,
)
from alpha.types import RiskSnapshot
from config.settings import BotConfig

logger = logging.getLogger(__name__)

_SIZE_EPS = 1e-6
_PRICE_EPS = 1e-6


def _default_bracket_path(state_dir: Optional[Path] = None) -> Path:
    base = state_dir or Path("logs")
    return base / "alpha_brackets.json"


@dataclass(frozen=True)
class OrderManagerState:
    open_offers: List[dict[str, Any]]
    bracket_count: int = 0
    active_brackets: int = 0
    pending_buys: int = 0
    bracket_states: tuple[str, ...] = ()
    recent_events: tuple[str, ...] = ()


class OrderManager:
    """
    Phase 3: register pending buys, place TP/SL after fill, OCO cancel opposing leg.

    All ledger writes go through ``LedgerInterface`` which enforces ``DryRunGuard``.
    """

    def __init__(
        self,
        ledger: LedgerInterface,
        dry_run_guard: DryRunGuard,
        config: BotConfig,
        *,
        risk_engine: object | None = None,
        state_dir: Path | None = None,
        structure: object | None = None,
    ) -> None:
        self._ledger = ledger
        self._guard = dry_run_guard
        self._config = config
        self._risk_engine = risk_engine
        self._structure = structure
        self._ta: object | None = None
        self._store = BracketStateStore(persist_path=_default_bracket_path(state_dir))
        self._partial_fill_mode = normalize_partial_fill_mode(config.partial_fill_mode)
        self._recent_events: List[str] = []
        self._last_risk: Optional[RiskSnapshot] = None

    def set_structure(self, structure: object | None) -> None:
        self._structure = structure

    def set_ta(self, ta: object | None) -> None:
        self._ta = ta

    @property
    def store(self) -> BracketStateStore:
        return self._store

    def pending_buy_count(self) -> int:
        return self._store.pending_buy_count()

    def count_strength_sells(self, open_offers: List[dict[str, Any]]) -> int:
        """Open ask offers that are not bracket TP/SL legs (inventory strength sells)."""
        leg_seqs = self._store.bracket_leg_sequences()
        count = 0
        for offer in open_offers:
            if offer.get("side") != "ask":
                continue
            seq = int(offer.get("sequence") or 0)
            if seq > 0 and seq not in leg_seqs:
                count += 1
        return count

    async def open_sequences(self) -> Set[int]:
        return await self._open_sequences()

    async def resolve_new_sequence(
        self,
        before: Set[int],
        *,
        side: str,
        price: float,
        size_xrp: float,
    ) -> Optional[int]:
        return await self._resolve_sequence(
            before,
            side=side,
            price=price,
            size_xrp=size_xrp,
            submitted=True,
        )

    def register_pending_buy(
        self,
        *,
        buy_sequence: int,
        size_xrp: float,
        entry_price_rlusd_per_xrp: float,
        bracket_id: Optional[str] = None,
    ) -> str:
        """Register a limit buy awaiting fill; bracket legs placed after fill."""
        bid = bracket_id or str(uuid.uuid4())
        record = BracketRecord(
            bracket_id=bid,
            state=BracketLifecycleState.PENDING_BUY,
            mode=BracketMode.BRACKET,
            buy_sequence=buy_sequence,
            entry_price_rlusd_per_xrp=entry_price_rlusd_per_xrp,
            target_size_xrp=size_xrp,
        )
        self._store.add(record)
        logger.info(
            "bracket_register | id=%s | buy_seq=%s | size=%.4f | entry=%.6f | mode=%s",
            bid,
            buy_sequence,
            size_xrp,
            entry_price_rlusd_per_xrp,
            self._partial_fill_mode,
        )
        return bid

    async def sync_state(self, *, risk: Optional[RiskSnapshot] = None) -> OrderManagerState:
        """Sync open offers and advance bracket lifecycle (alias for sync_brackets)."""
        return await self.sync_brackets(risk=risk)

    async def sync_brackets(self, *, risk: Optional[RiskSnapshot] = None) -> OrderManagerState:
        """Poll ledger offers, detect fills, place/cancel bracket legs."""
        self._last_risk = risk
        offers = await self._ledger.get_open_offers()
        open_map = _open_offer_map(offers)

        for record in list(self._store.iter_open()):
            if record.state == BracketLifecycleState.PENDING_BUY:
                await self._advance_pending_buy(record, open_map)
            elif record.state == BracketLifecycleState.BRACKET_ACTIVE:
                await self._advance_active_bracket(record, open_map)

        from alpha.decision.structure import CandleData, MarketStructureSnapshot, build_confirmation_candle

        structure = self._structure if isinstance(self._structure, MarketStructureSnapshot) else None
        current_price = structure.mid if structure and structure.mid > 0 else 0.0
        candle_data: Optional[CandleData] = None
        if structure and structure.confirmation_candle is not None:
            candle_data = structure.confirmation_candle
        elif current_price > 0:
            candle_data = build_confirmation_candle(
                current_price,
                timeframe=self._config.breakout_confirmation_tf,
                cycle_seconds=self._config.alpha_cycle_interval_seconds,
                sample_interval_seconds=self._config.alpha_price_sample_interval_seconds,
                price_source=self._config.alpha_structure_price_source,
            )

        if current_price > 0:
            await self.update_trailing_orders(current_price, candle_data, structure=structure)

        state = OrderManagerState(
            open_offers=offers,
            bracket_count=len(self._store.all_records()),
            active_brackets=self._store.active_bracket_count(),
            pending_buys=self._store.pending_buy_count(),
            bracket_states=self._store.state_labels(),
            recent_events=tuple(self._recent_events[-20:]),
        )
        logger.info(
            "order_manager_sync | open_offers=%d | brackets=%d | active=%d | pending_buys=%d | dry_run=%s",
            len(offers),
            state.bracket_count,
            state.active_brackets,
            state.pending_buys,
            self._guard.dry_run,
        )
        return state

    async def update_trailing_orders(
        self,
        current_price: float,
        candle_data: Optional["CandleData"] = None,
        *,
        structure: object | None = None,
    ) -> int:
        """
        Evaluate and apply trailing SL/TP updates for all active brackets.

        Trailing SL arms after breakeven; TP trails only after breakout confirmation
        on ``breakout_confirmation_tf``. Respects dry_run (logs without ledger writes).

        Returns the number of leg replacements performed (or simulated in dry_run).
        """
        from alpha.decision.structure import MarketStructureSnapshot

        if current_price <= 0:
            logger.warning("trailing_skip | reason=invalid_price | price=%.6f", current_price)
            return 0
        if not self._config.bracket_trailing_enabled:
            return 0

        snap = structure if isinstance(structure, MarketStructureSnapshot) else (
            self._structure if isinstance(self._structure, MarketStructureSnapshot) else None
        )
        if snap is None and candle_data is not None and current_price > 0:
            from alpha.decision.structure import recent_swing_high

            swing = recent_swing_high(
                [candle_data.open, candle_data.high, candle_data.low, candle_data.close],
                exclude_last=True,
            )
            snap = MarketStructureSnapshot(
                mid=current_price,
                sample_count=1,
                mean_mid=current_price,
                recent_high=candle_data.high,
                recent_low=candle_data.low,
                trend="neutral",
                breakout_up=False,
                breakout_down=False,
                summary="trailing_candle_context",
                swing_high=swing or candle_data.high,
                confirmation_candle=candle_data,
            )

        updates = 0
        for record in self._store.iter_open():
            if record.state != BracketLifecycleState.BRACKET_ACTIVE:
                continue

            result = evaluate_trailing(
                record,
                self._config,
                current_price=current_price,
                candle_data=candle_data,
                structure=snap,
                ta=self._ta,
            )
            changed = await self._apply_trailing_result(record, result)
            if changed:
                updates += 1
                record.touch()
                self._store.touch_persist()

        if updates:
            logger.info(
                "trailing_sync | price=%.6f | updates=%d | dry_run=%s",
                current_price,
                updates,
                self._guard.dry_run,
            )
        return updates

    async def _apply_trailing_result(
        self,
        record: BracketRecord,
        result: TrailingEvalResult,
    ) -> bool:
        """Cancel/replace bracket legs when trailing evaluation requests new prices."""
        changed = False
        if result.new_sl_price is not None:
            if await self._replace_leg(
                record,
                BracketLegRole.STOP_LOSS,
                result.new_sl_price,
                reason="sl_trail",
            ):
                changed = True
        if result.new_tp_price is not None:
            if await self._replace_leg(
                record,
                BracketLegRole.TAKE_PROFIT,
                result.new_tp_price,
                reason="tp_trail",
            ):
                changed = True
        return changed

    async def _replace_leg(
        self,
        record: BracketRecord,
        role: BracketLegRole,
        new_price: float,
        *,
        reason: str,
    ) -> bool:
        """Cancel an open leg and place a replacement at ``new_price``."""
        leg = record.tp_leg if role == BracketLegRole.TAKE_PROFIT else record.sl_leg
        if leg is None:
            return False
        if abs(new_price - leg.price_rlusd_per_xrp) < _PRICE_EPS:
            return False

        size_xrp = leg.remaining_xrp if leg.remaining_xrp > _SIZE_EPS else leg.size_xrp
        leg_name = role.value
        old_price = leg.price_rlusd_per_xrp
        old_seq = leg.sequence

        if not self._guard.require_live(f"trail_{leg_name}_{reason}"):
            logger.info(
                "bracket_trail_dry_run | id=%s | leg=%s | old=%.6f | new=%.6f | seq=%s | mode=%s",
                record.bracket_id,
                leg_name,
                old_price,
                new_price,
                old_seq,
                reason,
            )
            leg.price_rlusd_per_xrp = new_price
            return True

        if leg.sequence is not None:
            await self._ledger.cancel_offer(leg.sequence)
            self._store.unregister_leg_sequence(leg.sequence)

        before_seqs = await self._open_sequences()
        place_result = await self._ledger.place_limit_sell_xrp(
            size_xrp=size_xrp,
            price_rlusd_per_xrp=new_price,
        )
        new_seq = await self._resolve_sequence(
            before_seqs,
            side="ask",
            price=new_price,
            size_xrp=size_xrp,
            submitted=place_result.submitted,
        )

        leg.sequence = new_seq
        leg.price_rlusd_per_xrp = new_price
        if new_seq:
            self._store.register_leg_sequence(new_seq, record.bracket_id)

        logger.info(
            "bracket_trail_applied | id=%s | leg=%s | old=%.6f | new=%.6f | seq=%s→%s | mode=%s",
            record.bracket_id,
            leg_name,
            old_price,
            new_price,
            old_seq,
            new_seq,
            reason,
        )
        return True

    async def cancel_all(self) -> bool:
        """Cancel all open offers on ledger and clear tracked brackets."""
        offers = await self._ledger.get_open_offers()
        if not self._guard.require_live("cancel_all_offers"):
            logger.info(
                "bracket_cancel_all_dry_run | would_cancel=%d offers",
                len(offers),
            )
            return False

        if not offers:
            for record in list(self._store.all_records()):
                record.state = BracketLifecycleState.CANCELLED
                record.touch()
            return True

        for offer in offers:
            seq = int(offer.get("sequence", 0))
            if seq > 0:
                await self._ledger.cancel_offer(seq)

        for record in list(self._store.all_records()):
            record.state = BracketLifecycleState.CANCELLED
            record.touch()
        logger.info("bracket_cancel_all | cancelled_offers=%d", len(offers))
        return True

    def _resolve_bracket_id(self, bracket_id: str) -> Optional[str]:
        if self._store.get(bracket_id):
            return bracket_id
        matches = [
            r.bracket_id
            for r in self._store.all_records()
            if r.bracket_id.startswith(bracket_id)
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    async def adjust_bracket_leg(self, bracket_id: str, leg: str, new_price: float) -> bool:
        """Operator manual SL/TP adjust — cancel+replace like trailing; respects dry_run."""
        resolved = self._resolve_bracket_id(bracket_id)
        if not resolved:
            logger.warning("bracket_adjust_unknown | id=%s", bracket_id)
            return False
        record = self._store.get(resolved)
        if record is None or record.state != BracketLifecycleState.BRACKET_ACTIVE:
            logger.warning("bracket_adjust_inactive | id=%s | state=%s", bracket_id, getattr(record, "state", None))
            return False
        role = BracketLegRole.TAKE_PROFIT if leg == "tp" else BracketLegRole.STOP_LOSS
        return await self._replace_leg(record, role, new_price, reason="operator_adjust")

    async def _advance_pending_buy(
        self,
        record: BracketRecord,
        open_map: Dict[int, dict[str, Any]],
    ) -> None:
        buy_open = open_map.get(record.buy_sequence)
        if buy_open is not None:
            remaining = float(buy_open.get("size_xrp", 0.0))
            filled = max(0.0, record.target_size_xrp - remaining)
            if self._partial_fill_mode == "proportional" and filled > record.filled_xrp + _SIZE_EPS:
                delta = filled - record.filled_xrp
                record.filled_xrp = filled
                record.touch()
                await self._ensure_bracket_legs(record, size_xrp=filled, reason="buy_partial_fill")
                self._emit_event(
                    BracketFillEvent(
                        bracket_id=record.bracket_id,
                        leg="buy",
                        filled_xrp=delta,
                        price_rlusd_per_xrp=record.entry_price_rlusd_per_xrp,
                        partial=remaining > _SIZE_EPS,
                        new_state=record.state,
                    )
                )
            return

        if self._buy_offer_was_cancelled(record.buy_sequence):
            record.state = BracketLifecycleState.CANCELLED
            record.touch()
            self._store.touch_persist()
            logger.warning(
                "bracket_buy_cancelled | id=%s | buy_seq=%s | no_bracket_placed",
                record.bracket_id,
                record.buy_sequence,
            )
            self._emit_event(
                BracketFillEvent(
                    bracket_id=record.bracket_id,
                    leg="buy",
                    filled_xrp=0.0,
                    price_rlusd_per_xrp=record.entry_price_rlusd_per_xrp,
                    partial=False,
                    new_state=BracketLifecycleState.CANCELLED,
                )
            )
            return

        # Buy offer gone — treat as filled (WS cancel check passed)
        if (
            record.state == BracketLifecycleState.BRACKET_ACTIVE
            and record.bracketed_xrp + _SIZE_EPS >= record.filled_xrp
        ):
            return
        if record.filled_xrp <= _SIZE_EPS:
            record.filled_xrp = record.target_size_xrp
        record.touch()
        logger.info(
            "bracket_buy_filled | id=%s | filled=%.4f | entry=%.6f",
            record.bracket_id,
            record.filled_xrp,
            record.entry_price_rlusd_per_xrp,
        )
        await self._ensure_bracket_legs(record, size_xrp=record.filled_xrp, reason="buy_full_fill")
        self._emit_event(
            BracketFillEvent(
                bracket_id=record.bracket_id,
                leg="buy",
                filled_xrp=record.filled_xrp,
                price_rlusd_per_xrp=record.entry_price_rlusd_per_xrp,
                partial=False,
                new_state=record.state,
            )
        )

    def _buy_offer_was_cancelled(self, buy_sequence: int) -> bool:
        checker = getattr(self._ledger, "offer_cancel_seen", None)
        if callable(checker):
            return bool(checker(buy_sequence))
        return False

    async def _ensure_bracket_legs(
        self,
        record: BracketRecord,
        *,
        size_xrp: float,
        reason: str,
    ) -> None:
        if self._last_risk is not None and self._risk_engine is not None:
            from alpha.risk.engine import RiskEngine

            if isinstance(self._risk_engine, RiskEngine):
                ok, msg = self._risk_engine.validate_bracket_placement(self._last_risk)
                if not ok:
                    logger.warning(
                        "bracket_placement_blocked | id=%s | reason=%s",
                        record.bracket_id,
                        msg,
                    )
                    return

        if size_xrp < self._config.min_order_size_xrp:
            logger.info(
                "bracket_skip_small | id=%s | size=%.4f | min=%.4f",
                record.bracket_id,
                size_xrp,
                self._config.min_order_size_xrp,
            )
            return

        if abs(size_xrp - record.bracketed_xrp) < _SIZE_EPS and record.tp_leg and record.sl_leg:
            return

        if record.bracketed_xrp > _SIZE_EPS:
            await self._cancel_bracket_legs(record, reason=f"resize_{reason}")

        prices = compute_bracket_prices(record.entry_price_rlusd_per_xrp, self._config)
        logger.info(
            "bracket_place_legs | id=%s | reason=%s | size=%.4f | tp=%.6f | sl=%.6f | pricing=%s",
            record.bracket_id,
            reason,
            size_xrp,
            prices.take_profit_price,
            prices.stop_loss_price,
            prices.pricing_mode,
        )

        before_seqs = await self._open_sequences()
        tp_result = await self._ledger.place_limit_sell_xrp(
            size_xrp=size_xrp,
            price_rlusd_per_xrp=prices.take_profit_price,
        )
        tp_seq = await self._resolve_sequence(
            before_seqs,
            side="ask",
            price=prices.take_profit_price,
            size_xrp=size_xrp,
            submitted=tp_result.submitted,
        )
        if tp_seq:
            before_seqs.add(tp_seq)

        sl_result = await self._ledger.place_limit_sell_xrp(
            size_xrp=size_xrp,
            price_rlusd_per_xrp=prices.stop_loss_price,
        )
        sl_seq = await self._resolve_sequence(
            before_seqs,
            side="ask",
            price=prices.stop_loss_price,
            size_xrp=size_xrp,
            submitted=sl_result.submitted,
        )

        record.tp_leg = BracketLeg(
            role=BracketLegRole.TAKE_PROFIT,
            sequence=tp_seq,
            price_rlusd_per_xrp=prices.take_profit_price,
            size_xrp=size_xrp,
            remaining_xrp=size_xrp,
        )
        record.sl_leg = BracketLeg(
            role=BracketLegRole.STOP_LOSS,
            sequence=sl_seq,
            price_rlusd_per_xrp=prices.stop_loss_price,
            size_xrp=size_xrp,
            remaining_xrp=size_xrp,
        )
        if tp_seq:
            self._store.register_leg_sequence(tp_seq, record.bracket_id)
        if sl_seq:
            self._store.register_leg_sequence(sl_seq, record.bracket_id)

        record.bracketed_xrp = size_xrp
        record.state = BracketLifecycleState.BRACKET_ACTIVE
        record.touch()
        self._store.touch_persist()

    async def _advance_active_bracket(
        self,
        record: BracketRecord,
        open_map: Dict[int, dict[str, Any]],
    ) -> None:
        for role, leg in (
            (BracketLegRole.TAKE_PROFIT, record.tp_leg),
            (BracketLegRole.STOP_LOSS, record.sl_leg),
        ):
            if leg is None or leg.sequence is None:
                continue
            fill = _detect_leg_fill(leg, open_map)
            if fill is None or fill < self._config.min_fill_size_xrp_for_oco:
                continue
            await self._on_leg_fill(record, role, fill, open_map)

    async def _on_leg_fill(
        self,
        record: BracketRecord,
        role: BracketLegRole,
        filled_xrp: float,
        open_map: Dict[int, dict[str, Any]],
    ) -> None:
        leg = record.tp_leg if role == BracketLegRole.TAKE_PROFIT else record.sl_leg
        opposing = record.sl_leg if role == BracketLegRole.TAKE_PROFIT else record.tp_leg
        if leg is None:
            return

        partial = filled_xrp + _SIZE_EPS < leg.size_xrp
        leg.remaining_xrp = max(0.0, leg.remaining_xrp - filled_xrp)
        record.touch()

        leg_name = "tp" if role == BracketLegRole.TAKE_PROFIT else "sl"
        new_state = (
            BracketLifecycleState.TP_FILLED
            if role == BracketLegRole.TAKE_PROFIT
            else BracketLifecycleState.SL_FILLED
        )
        record.state = new_state

        logger.info(
            "bracket_leg_fill | id=%s | leg=%s | filled=%.4f | partial=%s | min_oco=%.4f",
            record.bracket_id,
            leg_name,
            filled_xrp,
            partial,
            self._config.min_fill_size_xrp_for_oco,
        )
        self._emit_event(
            BracketFillEvent(
                bracket_id=record.bracket_id,
                leg=leg_name,
                filled_xrp=filled_xrp,
                price_rlusd_per_xrp=leg.price_rlusd_per_xrp,
                partial=partial,
                new_state=new_state,
            )
        )

        if opposing is not None and opposing.sequence is not None:
            still_open = opposing.sequence in open_map
            if still_open:
                logger.info(
                    "bracket_oco_cancel | id=%s | cancel_leg=%s | seq=%s | trigger=%s_fill",
                    record.bracket_id,
                    opposing.role.value,
                    opposing.sequence,
                    leg_name,
                )
                await self._ledger.cancel_offer(opposing.sequence)
                self._store.unregister_leg_sequence(opposing.sequence)
                opposing.remaining_xrp = 0.0

    async def _cancel_bracket_legs(self, record: BracketRecord, *, reason: str) -> None:
        for leg in (record.tp_leg, record.sl_leg):
            if leg is None or leg.sequence is None:
                continue
            logger.info(
                "bracket_cancel_leg | id=%s | leg=%s | seq=%s | reason=%s",
                record.bracket_id,
                leg.role.value,
                leg.sequence,
                reason,
            )
            await self._ledger.cancel_offer(leg.sequence)
            self._store.unregister_leg_sequence(leg.sequence)
            leg.remaining_xrp = 0.0

    async def _open_sequences(self) -> Set[int]:
        offers = await self._ledger.get_open_offers()
        return {int(o["sequence"]) for o in offers if o.get("sequence")}

    async def _resolve_sequence(
        self,
        before: Set[int],
        *,
        side: str,
        price: float,
        size_xrp: float,
        submitted: bool,
    ) -> Optional[int]:
        if not submitted:
            return None
        offers = await self._ledger.get_open_offers()
        after = {int(o["sequence"]) for o in offers if o.get("sequence")}
        new_seqs = after - before
        if len(new_seqs) == 1:
            return next(iter(new_seqs))
        for offer in offers:
            if offer.get("side") != side:
                continue
            if abs(float(offer.get("price", 0.0)) - price) > 1e-5:
                continue
            if abs(float(offer.get("size_xrp", 0.0)) - size_xrp) > 0.05:
                continue
            return int(offer["sequence"])
        return None

    def _emit_event(self, event: BracketFillEvent) -> None:
        label = (
            f"{event.bracket_id}:{event.leg}:fill={event.filled_xrp:.4f}:"
            f"state={event.new_state.value}"
        )
        self._recent_events.append(label)
        logger.info("bracket_event | %s | partial=%s", label, event.partial)


def _open_offer_map(offers: List[dict[str, Any]]) -> Dict[int, dict[str, Any]]:
    out: Dict[int, dict[str, Any]] = {}
    for offer in offers:
        seq = offer.get("sequence")
        if seq is not None:
            out[int(seq)] = offer
    return out


def _detect_leg_fill(
    leg: BracketLeg,
    open_map: Dict[int, dict[str, Any]],
) -> Optional[float]:
    """Return XRP filled on this leg, or None if unchanged."""
    if leg.sequence is None:
        return None
    open_offer = open_map.get(leg.sequence)
    if open_offer is None:
        return leg.remaining_xrp if leg.remaining_xrp > _SIZE_EPS else leg.size_xrp

    remaining = float(open_offer.get("size_xrp", leg.remaining_xrp))
    if remaining + _SIZE_EPS < leg.remaining_xrp:
        return leg.remaining_xrp - remaining
    return None
