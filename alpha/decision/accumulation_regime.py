"""Accumulation regime — first-class bull/breakout RLUSD deployment mode."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from alpha.decision.momentum_entry import evaluate_bull_run_entry
from alpha.decision.tape_participation import evaluate_tape_participation
from alpha.hud.operator_market_regime import normalize_market_regime
from alpha.types import utc_now
from config.settings import BotConfig

if TYPE_CHECKING:
    from alpha.decision.structure import MarketStructureSnapshot
    from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
    from alpha.types import InventorySnapshot

logger = logging.getLogger(__name__)

_DEFAULT_SESSION_PATH = Path("logs/accumulation_session.json")


@dataclass(frozen=True)
class AccumulationKnobs:
    """Effective trading params while accumulation regime is armed."""

    active: bool
    armed: bool
    buy_offset_pct: float
    stale_drift_pct: float
    max_pending_buys: int
    min_edge_pct: float
    risk_per_trade_pct: float
    ta_weight_factor: float
    bypass_reentry: bool
    bypass_reload_spacing: bool
    reload_spacing_cycles: int
    max_deviation: float


@dataclass(frozen=True)
class AccumulationRegimeSnapshot:
    enabled: bool
    active: bool
    armed: bool
    phase: str  # off | primed | armed | executing | blocked | budget_exhausted
    headline: str
    detail: str
    entry_allowed: bool
    reason: str
    signals: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    rlusd_budget_rlusd: float = 0.0
    rlusd_committed_rlusd: float = 0.0
    rlusd_remaining_rlusd: float = 0.0
    skynet_nudge: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "active": self.active,
            "armed": self.armed,
            "phase": self.phase,
            "headline": self.headline,
            "detail": self.detail,
            "entry_allowed": self.entry_allowed,
            "reason": self.reason,
            "signals": list(self.signals),
            "blockers": list(self.blockers),
            "rlusd_budget_rlusd": round(self.rlusd_budget_rlusd, 2),
            "rlusd_committed_rlusd": round(self.rlusd_committed_rlusd, 2),
            "rlusd_remaining_rlusd": round(self.rlusd_remaining_rlusd, 2),
            "skynet_nudge": self.skynet_nudge,
        }


class AccumulationSessionTracker:
    """Rolling RLUSD deployment budget for accumulation mode."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_SESSION_PATH
        self._state = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self._path.is_file():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def _window_hours(self, config: BotConfig) -> float:
        return max(0.5, float(getattr(config, "alpha_accumulation_budget_hours", 8.0)))

    def _maybe_roll_window(self, config: BotConfig) -> None:
        hours = self._window_hours(config)
        now = utc_now()
        try:
            start = datetime.fromisoformat(str(self._state.get("window_start_utc", "")))
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            start = None
        if start is None or (now - start).total_seconds() >= hours * 3600.0:
            self._state = {
                "window_start_utc": now.isoformat(),
                "committed_rlusd": 0.0,
                "filled_rlusd": 0.0,
            }
            self._save()

    def budget_rlusd(self, config: BotConfig, *, rlusd_balance: float) -> float:
        self._maybe_roll_window(config)
        pct = max(0.0, float(getattr(config, "alpha_accumulation_rlusd_budget_pct", 40.0)))
        if pct <= 0 or rlusd_balance <= 0:
            return 0.0
        return rlusd_balance * (pct / 100.0)

    def committed_rlusd(self) -> float:
        return float(self._state.get("committed_rlusd", 0.0))

    def remaining_rlusd(self, config: BotConfig, *, rlusd_balance: float) -> float:
        budget = self.budget_rlusd(config, rlusd_balance=rlusd_balance)
        return max(0.0, budget - self.committed_rlusd())

    def record_bid(self, *, size_xrp: float, price_rlusd_per_xrp: float) -> None:
        notional = max(0.0, size_xrp * price_rlusd_per_xrp)
        if notional <= 0:
            return
        self._state["committed_rlusd"] = self.committed_rlusd() + notional
        self._save()
        logger.info(
            "accumulation_session | bid_recorded | +%.2f RLUSD | committed=%.2f",
            notional,
            self.committed_rlusd(),
        )

    def record_fill(self, *, size_xrp: float, price_rlusd_per_xrp: float) -> None:
        notional = max(0.0, size_xrp * price_rlusd_per_xrp)
        if notional <= 0:
            return
        self._state["filled_rlusd"] = float(self._state.get("filled_rlusd", 0.0)) + notional
        self._save()

    def snapshot_dict(self) -> Dict[str, Any]:
        return dict(self._state)


def accumulation_knobs_from_snapshot(
    snap: AccumulationRegimeSnapshot,
    config: BotConfig,
) -> AccumulationKnobs:
    if not snap.armed:
        return AccumulationKnobs(
            active=snap.active,
            armed=False,
            buy_offset_pct=float(config.alpha_buy_limit_offset_pct or config.alpha_bid_offset_pct),
            stale_drift_pct=float(config.alpha_stale_pending_buy_max_drift_pct),
            max_pending_buys=int(config.alpha_max_pending_buys),
            min_edge_pct=float(config.alpha_min_edge_threshold_pct),
            risk_per_trade_pct=float(config.alpha_risk_per_trade_pct),
            ta_weight_factor=1.0,
            bypass_reentry=False,
            bypass_reload_spacing=False,
            reload_spacing_cycles=int(config.alpha_reentry_post_clear_buy_spacing_cycles),
            max_deviation=float(config.alpha_bull_run_max_deviation),
        )
    offset = float(getattr(config, "alpha_accumulation_buy_offset_pct", 0.06))
    drift = float(getattr(config, "alpha_accumulation_stale_drift_pct", 0.08))
    if getattr(config, "alpha_accumulation_chase_fills", True):
        drift = max(drift, offset)
    boost = max(1.0, float(getattr(config, "alpha_accumulation_risk_boost", 1.5)))
    return AccumulationKnobs(
        active=True,
        armed=True,
        buy_offset_pct=offset,
        stale_drift_pct=drift,
        max_pending_buys=int(getattr(config, "alpha_accumulation_max_pending_buys", 3)),
        min_edge_pct=float(getattr(config, "alpha_accumulation_min_edge_pct", 0.05)),
        risk_per_trade_pct=float(config.alpha_risk_per_trade_pct) * boost,
        ta_weight_factor=float(getattr(config, "alpha_accumulation_ta_weight_factor", 0.75)),
        bypass_reentry=bool(getattr(config, "alpha_accumulation_bypass_reentry", True)),
        bypass_reload_spacing=bool(getattr(config, "alpha_accumulation_bypass_reload_spacing", True)),
        reload_spacing_cycles=int(getattr(config, "alpha_accumulation_reload_spacing_cycles", 1)),
        max_deviation=float(getattr(config, "alpha_accumulation_max_deviation", 0.04)),
    )


def evaluate_accumulation_regime(
    config: BotConfig,
    *,
    inventory: "InventorySnapshot",
    mid: float,
    structure: Optional["MarketStructureSnapshot"],
    ta: Optional["TechnicalAnalysisSnapshot"],
    operator_market_regime: str = "neutral",
    pending_buys: int = 0,
    decision_action: str = "hold",
    rlusd_balance: float = 0.0,
    session: Optional[AccumulationSessionTracker] = None,
) -> AccumulationRegimeSnapshot:
    """Compute accumulation mode phase and whether RLUSD deployment is the job."""
    disabled = AccumulationRegimeSnapshot(
        enabled=False,
        active=False,
        armed=False,
        phase="off",
        headline="ACCUMULATION OFF",
        detail="alpha_accumulation_regime_enabled=false",
        entry_allowed=False,
        reason="disabled",
    )
    if not getattr(config, "alpha_accumulation_regime_enabled", True):
        return disabled

    regime = normalize_market_regime(operator_market_regime)
    tape = evaluate_tape_participation(config, mid=mid, structure=structure, ta=ta)
    widened = replace(
        config,
        alpha_bull_run_max_deviation=float(
            getattr(config, "alpha_accumulation_max_deviation", 0.04)
        ),
    )
    momentum = evaluate_bull_run_entry(
        widened,
        inventory=inventory,
        mid=mid,
        structure=structure,
        ta=ta,
    )

    signals: list[str] = []
    if momentum.active:
        signals.append(f"momentum:{momentum.reason}")
    if tape.active:
        signals.append(f"tape:{tape.reason or 'active'}")
    if regime == "bull":
        signals.append("operator_regime_bull")

    blockers: list[str] = []
    if inventory.pause_bids or inventory.buy_blocked_imbalance:
        blockers.append("inventory_blocked")
    if regime == "bear" and not tape.active:
        blockers.append("operator_regime_bear")

    max_dev = float(getattr(config, "alpha_accumulation_max_deviation", 0.04))
    if inventory.deviation > max_dev:
        blockers.append(f"dev={inventory.deviation:+.3f}>accum_max={max_dev:+.3f}")

    require_bull = bool(getattr(config, "alpha_accumulation_require_bull_regime", False))
    prime_on_tape = bool(getattr(config, "alpha_accumulation_prime_on_bull_tape", True))

    signal_ok = momentum.active or (tape.active and (not require_bull or regime == "bull"))
    primed = (
        not blockers
        and regime == "bull"
        and prime_on_tape
        and tape.active
        and not momentum.active
    )
    armed = not blockers and (momentum.active or (primed and tape.active))
    active = armed or primed or (regime == "bull" and tape.active and not blockers)

    sess = session or AccumulationSessionTracker()
    budget = sess.budget_rlusd(config, rlusd_balance=rlusd_balance)
    committed = sess.committed_rlusd()
    remaining = max(0.0, budget - committed)
    if armed and budget > 0 and remaining < config.min_order_size_xrp * max(mid, 0.01):
        blockers.append("accumulation_budget_exhausted")
        armed = False

    action = (decision_action or "hold").lower()
    if pending_buys > 0 or action == "place_bid":
        return AccumulationRegimeSnapshot(
            enabled=True,
            active=True,
            armed=True,
            phase="executing",
            headline="ACCUMULATING — deployment live",
            detail=momentum.reason or "Limit bids chasing tape",
            entry_allowed=True,
            reason="executing",
            signals=tuple(signals),
            blockers=tuple(blockers),
            rlusd_budget_rlusd=budget,
            rlusd_committed_rlusd=committed,
            rlusd_remaining_rlusd=remaining,
            skynet_nudge=(
                "Accumulation regime EXECUTING — summarize fill chase (offset/drift), "
                "pending ladder, and RLUSD budget remaining."
            ),
        )

    if blockers and (momentum.active or tape.active):
        return AccumulationRegimeSnapshot(
            enabled=True,
            active=active,
            armed=False,
            phase="blocked",
            headline="ACCUMULATION BLOCKED — opportunity present",
            detail=" | ".join(blockers[:4]),
            entry_allowed=False,
            reason="blocked",
            signals=tuple(signals),
            blockers=tuple(blockers),
            rlusd_budget_rlusd=budget,
            rlusd_committed_rlusd=committed,
            rlusd_remaining_rlusd=remaining,
            skynet_nudge=(
                f"Accumulation BLOCKED with signals {signals[:3]}. "
                "Give concrete fix (regime bull, budget, dev cap) — do not suggest dip-only patience."
            ),
        )

    if armed and signal_ok:
        return AccumulationRegimeSnapshot(
            enabled=True,
            active=True,
            armed=True,
            phase="armed",
            headline="ACCUMULATION ARMED — deploy RLUSD on tape",
            detail=momentum.reason or tape.reason or "Bull tape + regime",
            entry_allowed=True,
            reason="armed",
            signals=tuple(signals),
            rlusd_budget_rlusd=budget,
            rlusd_committed_rlusd=committed,
            rlusd_remaining_rlusd=remaining,
            skynet_nudge=(
                "Accumulation ARMED — engine should place_bid with chase offset/drift. "
                "If HOLD, read blockers (re-entry, TA, max_pending)."
            ),
        )

    if primed or (active and tape.active):
        return AccumulationRegimeSnapshot(
            enabled=True,
            active=True,
            armed=False,
            phase="primed",
            headline="ACCUMULATION PRIMED — bull tape building",
            detail="Waiting breakout/momentum confirm or next cycle",
            entry_allowed=False,
            reason="primed",
            signals=tuple(signals),
            rlusd_budget_rlusd=budget,
            rlusd_committed_rlusd=committed,
            rlusd_remaining_rlusd=remaining,
            skynet_nudge="Accumulation PRIMED — explain what signal upgrades to ARMED.",
        )

    return AccumulationRegimeSnapshot(
        enabled=True,
        active=False,
        armed=False,
        phase="off",
        headline="ACCUMULATION IDLE",
        detail="No bull/breakout deployment mandate",
        entry_allowed=False,
        reason="idle",
        signals=tuple(signals) if signals else (),
        rlusd_budget_rlusd=budget,
        rlusd_committed_rlusd=committed,
        rlusd_remaining_rlusd=remaining,
    )


def build_accumulation_context_block(snap: Dict[str, Any]) -> str:
    """SKYNET context section for accumulation regime."""
    if not snap:
        return "=== Accumulation regime ===\n(not evaluated)"
    lines = [
        "=== Accumulation regime (PRIMARY job in bull tape — deploy RLUSD → XRP) ===",
        f"phase={snap.get('phase')} armed={snap.get('armed')} entry_allowed={snap.get('entry_allowed')}",
        f"headline={snap.get('headline')}",
        f"detail={snap.get('detail')}",
        f"signals={snap.get('signals')}",
        f"blockers={snap.get('blockers')}",
        (
            f"rlusd_budget={snap.get('rlusd_budget_rlusd')} "
            f"committed={snap.get('rlusd_committed_rlusd')} "
            f"remaining={snap.get('rlusd_remaining_rlusd')}"
        ),
        "",
        "When ARMED/EXECUTING: favor accumulation knobs (tight offset, chase drift, max_pending 2–3, "
        "bypass re-entry weakness). Do NOT recommend dip-only patience or max_pending=1 unless operator asks defense.",
        f"skynet_nudge={snap.get('skynet_nudge') or ''}",
    ]
    return "\n".join(lines)
