"""Swing harvest watch — trim extended XRP legs; bracketed re-entry on dip (accumulation overlay)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from alpha.decision.price_history import (
    PRICE_HISTORY_PATH,
    effective_sample_seconds,
    load_price_series,
    normalize_price_source,
)
from alpha.types import utc_now
from config.settings import BotConfig

if TYPE_CHECKING:
    from alpha.decision.structure import MarketStructureSnapshot
    from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
    from alpha.types import InventorySnapshot

logger = logging.getLogger(__name__)

_DEFAULT_SESSION_PATH = Path("logs/harvest_session.json")


@dataclass(frozen=True)
class RollingMoveSnapshot:
    move_pct: float
    ref_mid: float
    high: float
    pullback_pct: float
    samples_used: int
    hours: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "move_pct": round(self.move_pct, 3),
            "ref_mid": round(self.ref_mid, 6),
            "high": round(self.high, 6),
            "pullback_pct": round(self.pullback_pct, 3),
            "samples_used": self.samples_used,
            "hours": self.hours,
        }


@dataclass(frozen=True)
class HarvestKnobs:
    active: bool
    armed: bool
    execute: bool
    pause_accumulation_bids: bool
    bypass_ta_bullish_defer: bool
    trim_risk_pct: float
    sell_offset_pct: float
    reentry_enabled: bool
    reentry_buy_offset_pct: float
    max_pending_sells: int


@dataclass(frozen=True)
class HarvestWatchSnapshot:
    enabled: bool
    phase: str  # idle | watching | armed | executing
    headline: str
    detail: str
    entry_allowed: bool
    reason: str
    signals: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    rolling: Optional[RollingMoveSnapshot] = None
    release_streak: int = 0
    tranches_in_window: int = 0
    pending_reentry: bool = False
    skynet_nudge: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "enabled": self.enabled,
            "phase": self.phase,
            "headline": self.headline,
            "detail": self.detail,
            "entry_allowed": self.entry_allowed,
            "reason": self.reason,
            "signals": list(self.signals),
            "blockers": list(self.blockers),
            "release_streak": self.release_streak,
            "tranches_in_window": self.tranches_in_window,
            "pending_reentry": self.pending_reentry,
            "skynet_nudge": self.skynet_nudge,
        }
        if self.rolling is not None:
            out["rolling"] = self.rolling.to_dict()
        return out


class HarvestSessionTracker:
    """Rolling harvest tranches and post-fill re-entry queue."""

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
        return max(0.5, float(getattr(config, "alpha_accumulation_harvest_window_hours", 8.0)))

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
                "tranches": 0,
                "release_streak": 0,
                "pending_reentry": False,
                "last_accumulation_active_utc": self._state.get("last_accumulation_active_utc"),
            }
            self._save()

    def release_streak(self) -> int:
        return int(self._state.get("release_streak", 0))

    def set_release_streak(self, streak: int) -> None:
        self._state["release_streak"] = max(0, int(streak))
        self._save()

    def tranches_in_window(self, config: BotConfig | None = None) -> int:
        cfg = config or BotConfig()
        self._maybe_roll_window(cfg)
        return int(self._state.get("tranches", 0))

    def can_place_trim(self, config: BotConfig) -> bool:
        self._maybe_roll_window(config)
        cap = int(getattr(config, "alpha_accumulation_harvest_max_tranches_per_window", 2))
        return int(self._state.get("tranches", 0)) < cap

    def record_trim_placed(self) -> None:
        self._state["tranches"] = int(self._state.get("tranches", 0)) + 1
        self._save()

    def record_accumulation_active(self) -> None:
        self._state["last_accumulation_active_utc"] = utc_now().isoformat()
        self._save()

    def accumulation_recently_active(self, config: BotConfig, *, hours: float = 12.0) -> bool:
        raw = self._state.get("last_accumulation_active_utc")
        if not raw:
            return False
        try:
            ts = datetime.fromisoformat(str(raw))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return False
        return (utc_now() - ts).total_seconds() <= hours * 3600.0

    def set_pending_reentry(self, *, enabled: bool) -> None:
        self._state["pending_reentry"] = bool(enabled)
        self._save()

    def pending_reentry(self) -> bool:
        return bool(self._state.get("pending_reentry"))

    def consume_pending_reentry(self) -> bool:
        if not self.pending_reentry():
            return False
        self._state["pending_reentry"] = False
        self._save()
        return True


def rolling_move_snapshot(
    config: BotConfig,
    *,
    mid: float,
    hours: float = 24.0,
    price_source: str | None = None,
    price_history_path: Path | None = None,
) -> Optional[RollingMoveSnapshot]:
    if mid <= 0:
        return None
    src = normalize_price_source(
        price_source or str(getattr(config, "alpha_structure_price_source", "ask")),
        default="mid",
    )
    series = load_price_series(src, path=price_history_path or PRICE_HISTORY_PATH)
    if len(series) < 2:
        return None
    sample_sec = effective_sample_seconds(
        int(config.alpha_cycle_interval_seconds),
        int(config.alpha_price_sample_interval_seconds),
    )
    samples_back = max(2, int(hours * 3600.0 / sample_sec))
    if len(series) <= samples_back:
        ref = float(series[0])
        window = series
    else:
        ref = float(series[-samples_back - 1])
        window = series[-samples_back:]
    if ref <= 0:
        return None
    high = max(float(x) for x in window)
    move_pct = (mid - ref) / ref * 100.0
    pullback_pct = ((high - mid) / high * 100.0) if high > 0 and high > mid else 0.0
    return RollingMoveSnapshot(
        move_pct=move_pct,
        ref_mid=ref,
        high=high,
        pullback_pct=pullback_pct,
        samples_used=len(window),
        hours=hours,
    )


def harvest_knobs_from_snapshot(
    snap: HarvestWatchSnapshot,
    config: BotConfig,
) -> HarvestKnobs:
    execute = bool(getattr(config, "alpha_accumulation_harvest_execute_enabled", True))
    armed = snap.phase in ("armed", "executing") and execute
    pause = armed and bool(getattr(config, "alpha_accumulation_harvest_pause_accumulation_bids", True))
    return HarvestKnobs(
        active=snap.phase != "idle",
        armed=armed,
        execute=execute and snap.enabled,
        pause_accumulation_bids=pause,
        bypass_ta_bullish_defer=armed
        and bool(getattr(config, "alpha_accumulation_harvest_bypass_ta_bullish_defer", True)),
        trim_risk_pct=float(getattr(config, "alpha_accumulation_harvest_trim_risk_pct", 1.5)),
        sell_offset_pct=float(getattr(config, "alpha_accumulation_harvest_sell_offset_pct", 0.10)),
        reentry_enabled=bool(getattr(config, "alpha_accumulation_harvest_reentry_enabled", True)),
        reentry_buy_offset_pct=float(
            getattr(config, "alpha_accumulation_harvest_reentry_buy_offset_pct", 0.18)
        ),
        max_pending_sells=int(getattr(config, "alpha_accumulation_harvest_max_pending_sells", 1)),
    )


def evaluate_harvest_watch(
    config: BotConfig,
    *,
    inventory: "InventorySnapshot",
    mid: float,
    structure: Optional["MarketStructureSnapshot"],
    ta: Optional["TechnicalAnalysisSnapshot"],
    momentum_active: bool,
    early_arm: bool,
    accumulation_armed: bool,
    accumulation_executing: bool,
    pending_harvest_sells: int,
    decision_action: str = "hold",
    session: Optional[HarvestSessionTracker] = None,
    tape_active: bool = False,
    price_history_path: Path | None = None,
) -> HarvestWatchSnapshot:
    disabled = HarvestWatchSnapshot(
        enabled=False,
        phase="idle",
        headline="HARVEST IDLE",
        detail="alpha_accumulation_harvest_watch_enabled=false",
        entry_allowed=False,
        reason="disabled",
    )
    if not getattr(config, "alpha_accumulation_harvest_watch_enabled", True):
        return disabled

    sess = session or HarvestSessionTracker()
    if accumulation_armed or accumulation_executing:
        sess.record_accumulation_active()

    hours = float(getattr(config, "alpha_accumulation_harvest_move_hours", 24.0))
    rolling = rolling_move_snapshot(
        config,
        mid=mid,
        hours=hours,
        price_history_path=price_history_path,
    )
    if rolling is None:
        return HarvestWatchSnapshot(
            enabled=True,
            phase="idle",
            headline="HARVEST IDLE",
            detail="insufficient price history for rolling move",
            entry_allowed=False,
            reason="warming_up",
        )

    watch_pct = float(getattr(config, "alpha_accumulation_harvest_move_24h_watch_pct", 5.0))
    arm_move_pct = float(getattr(config, "alpha_accumulation_harvest_move_24h_arm_pct", 0.0))
    arm_move_floor = arm_move_pct if arm_move_pct > 0 else watch_pct
    pullback_arm = float(getattr(config, "alpha_accumulation_harvest_pullback_arm_pct", 1.0))
    pullback_release = float(getattr(config, "alpha_accumulation_harvest_pullback_release_pct", 0.3))
    release_cycles = max(1, int(getattr(config, "alpha_accumulation_harvest_release_cycles", 2)))
    strength_dev = float(config.alpha_strength_deviation)
    execute = bool(getattr(config, "alpha_accumulation_harvest_execute_enabled", True))

    release_signal = bool(
        momentum_active
        or early_arm
        or (structure is not None and structure.breakout_up and tape_active)
        or (
            ta is not None
            and getattr(ta, "breakout_confirmed", False)
            and getattr(ta, "bias", "") == "bullish"
        )
    )

    streak = sess.release_streak()
    if release_signal:
        streak += 1
    else:
        streak = 0
    sess.set_release_streak(streak)

    signals: list[str] = [
        f"move_{int(hours)}h={rolling.move_pct:+.2f}%",
        f"pullback={rolling.pullback_pct:.2f}%",
    ]
    if momentum_active:
        signals.append("momentum_active")
    if early_arm:
        signals.append("early_arm")
    if accumulation_armed:
        signals.append("accumulation_armed")

    blockers: list[str] = []
    if inventory.deviation < strength_dev:
        blockers.append(f"dev={inventory.deviation:+.3f}<{strength_dev:+.3f}")
    if inventory.pause_asks:
        blockers.append("pause_asks")
    acc_context = accumulation_armed or accumulation_executing or sess.accumulation_recently_active(config)
    if not acc_context:
        blockers.append("no_recent_accumulation_context")
    if not sess.can_place_trim(config):
        blockers.append("harvest_window_cap_reached")

    if streak >= release_cycles and release_signal:
        return HarvestWatchSnapshot(
            enabled=True,
            phase="idle",
            headline="HARVEST RELEASED — bull momentum resumed",
            detail=f"release_streak={streak} · {rolling.move_pct:+.2f}% over {hours:.0f}h",
            entry_allowed=False,
            reason="momentum_release",
            signals=tuple(signals),
            rolling=rolling,
            release_streak=streak,
            tranches_in_window=sess.tranches_in_window(),
            pending_reentry=sess.pending_reentry(),
            skynet_nudge="Harvest cleared — accumulation is primary again.",
        )

    if pending_harvest_sells > 0:
        return HarvestWatchSnapshot(
            enabled=True,
            phase="executing",
            headline="HARVESTING — swing trim live",
            detail=f"sell tranche · {rolling.move_pct:+.2f}% leg · pullback {rolling.pullback_pct:.2f}%",
            entry_allowed=execute,
            reason="executing",
            signals=tuple(signals),
            blockers=tuple(blockers),
            rolling=rolling,
            release_streak=streak,
            tranches_in_window=sess.tranches_in_window(),
            pending_reentry=sess.pending_reentry(),
            skynet_nudge="Harvest EXECUTING — trim into RLUSD; re-entry bid queues on fill.",
        )

    armed_ok = (
        not blockers
        and rolling.move_pct >= arm_move_floor
        and rolling.pullback_pct >= pullback_arm
        and not momentum_active
        and not early_arm
    )
    watching_ok = (
        rolling.move_pct >= watch_pct
        and inventory.deviation >= strength_dev
        and acc_context
        and not momentum_active
    )

    if armed_ok:
        phase = "armed"
        headline = "HARVEST ARMED — trim window on swing turn"
        detail = (
            f"{rolling.move_pct:+.2f}% over {hours:.0f}h · "
            f"−{rolling.pullback_pct:.2f}% from {hours:.0f}h high"
        )
        entry_allowed = execute and sess.can_place_trim(config)
        reason = "armed"
        nudge = (
            "Harvest ARMED — engine should place_ask harvest_trim (pause accumulation bids). "
            "On fill, bracketed re-entry bid below mid if enabled."
        )
    elif watching_ok:
        phase = "watching"
        headline = "HARVEST WATCHING — extended leg, await pullback"
        detail = (
            f"{rolling.move_pct:+.2f}% over {hours:.0f}h · need pullback ≥{pullback_arm:.1f}%"
        )
        entry_allowed = False
        reason = "watching"
        nudge = "Leg extended — harvest arms when pullback confirms and momentum pauses."
    else:
        phase = "idle"
        headline = "HARVEST IDLE"
        detail = f"{rolling.move_pct:+.2f}% over {hours:.0f}h · pullback {rolling.pullback_pct:.2f}%"
        entry_allowed = False
        reason = "idle"
        nudge = ""

    return HarvestWatchSnapshot(
        enabled=True,
        phase=phase,
        headline=headline,
        detail=detail,
        entry_allowed=entry_allowed,
        reason=reason,
        signals=tuple(signals),
        blockers=tuple(blockers),
        rolling=rolling,
        release_streak=streak,
        tranches_in_window=sess.tranches_in_window(),
        pending_reentry=sess.pending_reentry(),
        skynet_nudge=nudge,
    )


def compute_harvest_trim_size_xrp(
    config: BotConfig,
    *,
    portfolio_xrp_equiv: float,
    trim_risk_pct: float,
) -> float:
    if portfolio_xrp_equiv <= 0 or trim_risk_pct <= 0:
        return 0.0
    size = portfolio_xrp_equiv * (trim_risk_pct / 100.0)
    cap = float(getattr(config, "alpha_accumulation_harvest_max_sell_xrp", 0.0))
    if cap > 0:
        size = min(size, cap)
    return round(max(0.0, size), 4)
