"""Accumulation regime — first-class bull/breakout RLUSD deployment mode."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from alpha.decision.momentum_entry import evaluate_bull_run_entry
from alpha.decision.price_history import normalize_price_source
from alpha.decision.tape_participation import (
    _short_term_slope_positive,
    evaluate_tape_participation,
)
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
    scorecard: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        out = {
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
        if self.scorecard:
            out["scorecard"] = self.scorecard
        return out


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
                "bids_placed": 0,
                "fills_count": 0,
                "chase_cancels": 0,
                "chase_count": 0,
                "window_mid_lo": 0.0,
                "window_mid_hi": 0.0,
                "minutes_armed": 0.0,
                "minutes_executing": 0.0,
                "minutes_blocked": 0.0,
                "minutes_tape_up_idle": 0.0,
                "ever_executed": False,
                "last_phase": "off",
                "last_tick_utc": now.isoformat(),
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
        self._state["bids_placed"] = int(self._state.get("bids_placed", 0)) + 1
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
        self._state["fills_count"] = int(self._state.get("fills_count", 0)) + 1
        self._state["chase_count"] = 0
        self._state["ever_executed"] = True
        self._save()
        logger.info(
            "accumulation_session | fill_recorded | +%.2f RLUSD | fills=%s",
            notional,
            self._state.get("fills_count"),
        )

    def chase_count(self) -> int:
        return int(self._state.get("chase_count", 0))

    def record_chase_cancel(self, reason: str) -> None:
        if "mid_passed" not in (reason or "").lower():
            return
        self._state["chase_cancels"] = int(self._state.get("chase_cancels", 0)) + 1
        self._state["chase_count"] = self.chase_count() + 1
        self._save()
        logger.info(
            "accumulation_session | chase_cancel | count=%s | %s",
            self.chase_count(),
            reason,
        )

    def record_cycle(
        self,
        *,
        phase: str,
        mid: float,
        armed: bool,
        tape_active: bool = False,
        cycle_seconds: float = 15.0,
    ) -> None:
        now = utc_now()
        try:
            last = datetime.fromisoformat(str(self._state.get("last_tick_utc", "")))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed_min = max(0.0, (now - last).total_seconds() / 60.0)
        except (TypeError, ValueError):
            elapsed_min = cycle_seconds / 60.0

        if mid > 0:
            lo = float(self._state.get("window_mid_lo") or 0.0)
            hi = float(self._state.get("window_mid_hi") or 0.0)
            if lo <= 0:
                lo = mid
            self._state["window_mid_lo"] = min(lo, mid)
            self._state["window_mid_hi"] = max(hi, mid)

        prev = str(self._state.get("last_phase") or "off")
        if prev == phase and elapsed_min > 0:
            key = {
                "armed": "minutes_armed",
                "executing": "minutes_executing",
                "blocked": "minutes_blocked",
            }.get(phase)
            if key:
                self._state[key] = float(self._state.get(key, 0.0)) + elapsed_min
            if tape_active and phase in ("off", "idle", "primed") and not armed:
                self._state["minutes_tape_up_idle"] = float(
                    self._state.get("minutes_tape_up_idle", 0.0)
                ) + elapsed_min

        self._state["last_phase"] = phase
        self._state["last_tick_utc"] = now.isoformat()
        self._save()

    def scorecard(self, config: BotConfig) -> Dict[str, Any]:
        self._maybe_roll_window(config)
        bids = int(self._state.get("bids_placed", 0))
        fills = int(self._state.get("fills_count", 0))
        lo = float(self._state.get("window_mid_lo") or 0.0)
        hi = float(self._state.get("window_mid_hi") or 0.0)
        move_pct = ((hi - lo) / lo * 100.0) if lo > 0 and hi > lo else 0.0
        missed_thresh = float(getattr(config, "alpha_accumulation_missed_move_pct", 0.30))
        ever_exec = bool(self._state.get("ever_executed"))
        tape_idle = float(self._state.get("minutes_tape_up_idle", 0.0))
        missed = (
            move_pct >= missed_thresh
            and not ever_exec
            and tape_idle >= 1.0
            and fills == 0
        )
        fill_rate = round(fills / bids * 100.0, 1) if bids > 0 else 0.0
        headline = "On track — fills landing" if fills > 0 else (
            "MISSING MOVE — tape up, no fills" if missed else "Watching — no rip fill yet"
        )
        return {
            "bids_placed": bids,
            "fills_count": fills,
            "chase_cancels": int(self._state.get("chase_cancels", 0)),
            "chase_count": self.chase_count(),
            "fill_rate_pct": fill_rate,
            "rlusd_filled_rlusd": round(float(self._state.get("filled_rlusd", 0.0)), 2),
            "rlusd_committed_rlusd": round(self.committed_rlusd(), 2),
            "phase_minutes": {
                "armed": round(float(self._state.get("minutes_armed", 0.0)), 1),
                "executing": round(float(self._state.get("minutes_executing", 0.0)), 1),
                "blocked": round(float(self._state.get("minutes_blocked", 0.0)), 1),
                "tape_up_idle": round(tape_idle, 1),
            },
            "window_mid_move_pct": round(move_pct, 3),
            "missed_opportunity": missed,
            "headline": headline,
        }

    def snapshot_dict(self) -> Dict[str, Any]:
        return dict(self._state)


def accumulation_knobs_from_snapshot(
    snap: AccumulationRegimeSnapshot,
    config: BotConfig,
    *,
    session: Optional[AccumulationSessionTracker] = None,
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
    step = float(getattr(config, "alpha_accumulation_chase_tighten_step_pct", 0.02))
    min_off = float(getattr(config, "alpha_accumulation_chase_min_offset_pct", 0.03))
    chase_n = session.chase_count() if session is not None else 0
    if chase_n > 0 and getattr(config, "alpha_accumulation_chase_fills", True):
        offset = max(min_off, offset - step * chase_n)
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
    early_enabled = bool(getattr(config, "alpha_accumulation_early_arm_enabled", True))

    slope_ok = _short_term_slope_positive(
        samples=int(getattr(config, "alpha_tape_slope_samples", 8)),
        price_source=normalize_price_source(
            str(getattr(config, "alpha_structure_price_source", "ask")),
            default="mid",
        ),
        min_lift_pct=float(getattr(config, "alpha_tape_slope_min_lift_pct", 0.04)),
    )
    if slope_ok:
        signals.append("slope_up")

    regime_ok = regime == "bull" or (regime == "neutral" and not require_bull)
    early_arm = (
        early_enabled
        and tape.active
        and slope_ok
        and regime_ok
        and regime != "bear"
    )
    if early_arm and not momentum.active:
        signals.append("early_arm_tape_slope")

    signal_ok = momentum.active or early_arm or (tape.active and (not require_bull or regime == "bull"))
    primed = (
        not blockers
        and not early_arm
        and not momentum.active
        and prime_on_tape
        and tape.active
        and regime_ok
    )
    armed = not blockers and (momentum.active or early_arm)
    active = armed or primed or (regime_ok and tape.active and not blockers)

    sess = session or AccumulationSessionTracker()
    scorecard = sess.scorecard(config)
    budget = sess.budget_rlusd(config, rlusd_balance=rlusd_balance)
    committed = sess.committed_rlusd()
    remaining = max(0.0, budget - committed)
    if armed and budget > 0 and remaining < config.min_order_size_xrp * max(mid, 0.01):
        blockers.append("accumulation_budget_exhausted")
        armed = False

    def _with_scorecard(snap: AccumulationRegimeSnapshot) -> AccumulationRegimeSnapshot:
        return AccumulationRegimeSnapshot(
            enabled=snap.enabled,
            active=snap.active,
            armed=snap.armed,
            phase=snap.phase,
            headline=snap.headline,
            detail=snap.detail,
            entry_allowed=snap.entry_allowed,
            reason=snap.reason,
            signals=snap.signals,
            blockers=snap.blockers,
            rlusd_budget_rlusd=snap.rlusd_budget_rlusd,
            rlusd_committed_rlusd=snap.rlusd_committed_rlusd,
            rlusd_remaining_rlusd=snap.rlusd_remaining_rlusd,
            skynet_nudge=snap.skynet_nudge,
            scorecard=scorecard,
        )

    action = (decision_action or "hold").lower()
    if pending_buys > 0 or action == "place_bid":
        return _with_scorecard(
            AccumulationRegimeSnapshot(
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
            ),
        )

    if blockers and (momentum.active or tape.active or early_arm):
        return _with_scorecard(
            AccumulationRegimeSnapshot(
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
            ),
        )

    if armed and signal_ok:
        detail = momentum.reason or (
            "early_arm tape+slope" if early_arm else (tape.reason or "Bull tape")
        )
        return _with_scorecard(
            AccumulationRegimeSnapshot(
                enabled=True,
                active=True,
                armed=True,
                phase="armed",
                headline="ACCUMULATION ARMED — deploy RLUSD on tape",
                detail=detail,
                entry_allowed=True,
                reason="armed",
                signals=tuple(signals),
                rlusd_budget_rlusd=budget,
                rlusd_committed_rlusd=committed,
                rlusd_remaining_rlusd=remaining,
                skynet_nudge=(
                    "Accumulation ARMED — engine should place_bid with chase offset/drift. "
                    "If HOLD, read blockers (re-entry, TA, max_pending). "
                    f"Scorecard: {scorecard.get('headline')}."
                ),
            )
        )

    if primed or (active and tape.active):
        return _with_scorecard(
            AccumulationRegimeSnapshot(
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
            ),
        )

    return _with_scorecard(
        AccumulationRegimeSnapshot(
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
        ),
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
    ]
    sc = snap.get("scorecard")
    if isinstance(sc, dict):
        from alpha.decision.accumulation_scorecard import build_accumulation_scorecard_block

        lines.append("")
        lines.extend(build_accumulation_scorecard_block(sc).splitlines())
    lines.extend(
        [
        "",
        "When ARMED/EXECUTING: favor accumulation knobs (tight offset, chase drift, max_pending 2–3, "
        "bypass re-entry weakness). Do NOT recommend dip-only patience or max_pending=1 unless operator asks defense.",
        f"skynet_nudge={snap.get('skynet_nudge') or ''}",
        ]
    )
    return "\n".join(lines)
