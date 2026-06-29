"""Opportunity watch — surface bull/breakout readiness before the operator misses the move."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from alpha.decision.momentum_entry import evaluate_bull_run_entry
from alpha.decision.tape_participation import evaluate_tape_participation
from config.settings import BotConfig

if TYPE_CHECKING:
    from alpha.decision.structure import MarketStructureSnapshot
    from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
    from alpha.types import InventorySnapshot


@dataclass(frozen=True)
class OpportunityWatchSnapshot:
    """Operator-facing readiness — distinct from engine posture (patient/buying)."""

    state: str  # idle | watching | armed | executing | blocked
    headline: str
    detail: str
    signals: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()
    skynet_nudge: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "headline": self.headline,
            "detail": self.detail,
            "signals": list(self.signals),
            "blockers": list(self.blockers),
            "suggestions": list(self.suggestions),
            "skynet_nudge": self.skynet_nudge,
        }


def _collect_signals(
    structure: Optional["MarketStructureSnapshot"],
    ta: Optional["TechnicalAnalysisSnapshot"],
    *,
    momentum_active: bool,
    momentum_reason: str,
    tape_active: bool,
) -> List[str]:
    out: List[str] = []
    if structure is not None:
        if structure.breakout_up:
            out.append("structure_breakout_up")
        if structure.trend == "bullish":
            out.append("structure_bullish")
        elif structure.trend == "neutral":
            out.append("structure_neutral")
    if ta is not None and ta.enabled:
        if ta.breakout_confirmed:
            out.append("ta_breakout_confirmed")
        if ta.bias == "bullish":
            out.append(f"ta_bullish buy={ta.buy_score:.2f}")
        elif ta.bias == "bearish":
            out.append(f"ta_bearish buy={ta.buy_score:.2f} sell={ta.sell_score:.2f}")
    if momentum_active:
        out.append(f"momentum:{momentum_reason or 'bull_run'}")
    if tape_active:
        out.append("tape_participation")
    return out


def _parse_blockers(decision_reason: str) -> List[str]:
    reason = (decision_reason or "").lower()
    blockers: List[str] = []
    if "balanced dev" in reason:
        blockers.append("inventory_balanced_dip_only_gate")
    if "reentry_" in reason:
        blockers.append(decision_reason.split("|")[0].strip()[:120])
    if "ta_buy_blocked" in reason:
        blockers.append("ta_buy_gate")
    if "max_pending" in reason:
        blockers.append("max_pending_buys")
    if "edge_below" in reason:
        blockers.append("edge_below_threshold")
    if "insufficient_ask_depth" in reason:
        blockers.append("thin_ask_depth")
    if "pause_bids" in reason or "kill_switch" in reason:
        blockers.append("risk_pause")
    return blockers


def evaluate_opportunity_watch(
    config: BotConfig,
    *,
    inventory: "InventorySnapshot",
    mid: float,
    structure: Optional["MarketStructureSnapshot"],
    ta: Optional["TechnicalAnalysisSnapshot"],
    decision_action: str = "hold",
    decision_reason: str = "",
    pending_buys: int = 0,
    trading_enabled: bool = True,
    operator_paused: bool = False,
) -> OpportunityWatchSnapshot:
    """Compute ready / watch / blocked state for HUD + SKYNET."""
    action = (decision_action or "hold").lower()
    momentum = evaluate_bull_run_entry(
        config,
        inventory=inventory,
        mid=mid,
        structure=structure,
        ta=ta,
    )
    tape = evaluate_tape_participation(config, mid=mid, structure=structure, ta=ta)
    signals = _collect_signals(
        structure,
        ta,
        momentum_active=momentum.active,
        momentum_reason=momentum.reason,
        tape_active=tape.active,
    )
    weakness = float(config.alpha_weakness_deviation)
    dip_buy_ok = inventory.deviation <= -weakness

    if pending_buys > 0 or action == "place_bid":
        return OpportunityWatchSnapshot(
            state="executing",
            headline="ACCUMULATING — bid live or pending",
            detail=decision_reason or "Engine placing or waiting on limit buy",
            signals=tuple(signals),
            suggestions=(
                "Monitor fill on Brackets / Open offers — stale drift chases rips if configured.",
            ),
            skynet_nudge="Summarize open bid vs mid and whether stale settings will chase this breakout.",
        )

    blockers: List[str] = []
    if operator_paused:
        blockers.append("operator_paused")
    if not trading_enabled:
        blockers.append("trading_disabled")

    parsed = _parse_blockers(decision_reason)
    blockers.extend(parsed)

    bullish_tape = any(
        s.startswith(("structure_breakout", "structure_bullish", "ta_breakout", "ta_bullish", "momentum:"))
        for s in signals
    )

    if momentum.active and not blockers:
        return OpportunityWatchSnapshot(
            state="armed",
            headline="ARMED — bull/breakout accumulate",
            detail=momentum.reason,
            signals=tuple(signals),
            suggestions=(
                "Engine should place_bid this cycle — if HOLD persists, check Activity for executor errors.",
                "SKYNET regime Bull aligns with this path.",
            ),
            skynet_nudge=(
                "Opportunity watch is ARMED (bull_run). Confirm effective knobs for chase: "
                "bull_run offset, max_pending, stale drift. Explain any remaining HOLD."
            ),
        )

    if momentum.active and blockers:
        suggestions = [
            "Momentum ARMED but engine BLOCKED — read blockers below; do not assume the bot is participating.",
        ]
        if "inventory_balanced_dip_only_gate" in blockers:
            suggestions.append(
                "Balanced inventory used to skip all buys — bull_run path should override; if you still see this, deploy may be stale.",
            )
        if any("reentry" in b for b in blockers):
            suggestions.append(
                "Post-exit re-entry may block even on rips — momentum chase bypasses weakness only when bull_run fires.",
            )
        if "ta_buy_gate" in blockers:
            suggestions.append(
                "TA still blocking — tape participation waives bearish bias only inside the buy path.",
            )
        return OpportunityWatchSnapshot(
            state="blocked",
            headline="BLOCKED — opportunity present, engine idle",
            detail=" | ".join(blockers[:3]) or decision_reason,
            signals=tuple(signals),
            blockers=tuple(blockers),
            suggestions=tuple(suggestions),
            skynet_nudge=(
                f"Opportunity watch BLOCKED with signals {signals[:4]}. "
                f"Decision reason: {decision_reason}. Give concrete knob or wait guidance."
            ),
        )

    if bullish_tape or tape.active:
        watch_detail = []
        if ta is not None and ta.enabled and ta.bias == "bullish":
            watch_detail.append("TA bullish")
        if structure is not None and structure.trend == "neutral":
            watch_detail.append("structure neutral — need breakout or bull_run drift")
        if not dip_buy_ok and inventory.deviation > -weakness:
            watch_detail.append(f"inventory {inventory.label} dev={inventory.deviation:+.3f} (dip gate needs ≤{-weakness:+.3f})")
        suggestions_list = [
            "WATCHING — tape improving. Bot will ARM on bull_run/breakout signals; you do not need to be RLUSD-heavy.",
            "Use Live → Opportunity watch + SKYNET Ask if HOLD while chart rips.",
        ]
        if not dip_buy_ok:
            suggestions_list.append(
                "Classic dip-only mode would sit out here — bull_run_enabled should engage on breakout/TA confirm.",
            )
        return OpportunityWatchSnapshot(
            state="watching",
            headline="WATCHING — bull tape building",
            detail=" · ".join(watch_detail) or "Momentum forming",
            signals=tuple(signals),
            suggestions=tuple(suggestions_list),
            skynet_nudge=(
                "Opportunity watch WATCHING — bull tape building but not ARMED yet. "
                "Explain what signal is missing (breakout, drift, TA) and estimated patience."
            ),
        )

    if ta is not None and ta.enabled and ta.bias == "bearish" and structure is not None:
        if structure.trend != "bearish":
            return OpportunityWatchSnapshot(
                state="watching",
                headline="WATCHING — lagging TA bearish, tape mixed",
                detail=tape.reason or f"TA sell-heavy; structure {structure.trend}",
                signals=tuple(signals),
                suggestions=(
                    "Chart may rip while closed-bar TA stays bearish — tape participation can waive inside buy path.",
                    "Wait for ARMED or ask SKYNET to explain lag vs live mid.",
                ),
                skynet_nudge="TA bearish vs live tape — explain lag and when opportunity_watch will ARM.",
            )

    return OpportunityWatchSnapshot(
        state="idle",
        headline="IDLE — no bull/breakout opportunity flagged",
        detail=decision_reason or "Patient / range posture",
        signals=tuple(signals) if signals else (),
        suggestions=(),
        skynet_nudge="",
    )
