"""Post-exit re-entry gate — patient reload after TP/SL (Aggressive Bag Growth)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from alpha.types import InventorySnapshot, utc_now
from config.settings import BotConfig

if TYPE_CHECKING:
    from alpha.decision.structure import MarketStructureSnapshot
    from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path("logs/alpha_reentry.json")


class ReentryExitType(str, Enum):
    NONE = "none"
    TP = "tp"
    SL = "sl"


@dataclass
class ReentrySnapshot:
    active: bool
    exit_type: ReentryExitType
    exit_mid: float
    exit_utc: datetime
    bracket_id: str
    cycles_since_exit: int = 0
    cooldown_cycles_required: int = 0
    cooldown_cycles_remaining: int = 0
    cooldown_minutes_required: float = 0.0
    cooldown_minutes_remaining: float = 0.0
    in_cooldown: bool = False
    sl_tier: str = ""
    entry_price: float = 0.0
    buy_spacing_cycles_remaining: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active": self.active,
            "exit_type": self.exit_type.value,
            "exit_mid": self.exit_mid,
            "exit_utc": self.exit_utc.isoformat(),
            "bracket_id": self.bracket_id,
            "cycles_since_exit": self.cycles_since_exit,
            "cooldown_cycles_required": self.cooldown_cycles_required,
            "cooldown_cycles_remaining": self.cooldown_cycles_remaining,
            "cooldown_minutes_required": self.cooldown_minutes_required,
            "cooldown_minutes_remaining": round(self.cooldown_minutes_remaining, 2),
            "in_cooldown": self.in_cooldown,
            "sl_tier": self.sl_tier,
            "entry_price": self.entry_price,
            "buy_spacing_cycles_remaining": self.buy_spacing_cycles_remaining,
        }

    @classmethod
    def inactive(cls) -> ReentrySnapshot:
        return cls(
            active=False,
            exit_type=ReentryExitType.NONE,
            exit_mid=0.0,
            exit_utc=utc_now(),
            bracket_id="",
            cycles_since_exit=0,
        )


class ReentryGate:
    """
    Blocks new PLACE_BID after bracket exits until cooldown + dip (TP) or stabilization (SL).

    Cooldown runs first — inventory/TA cannot bypass post-exit wait unless recovery rules apply.
    """

    def __init__(
        self,
        config: BotConfig,
        *,
        persist_path: Path | None = None,
    ) -> None:
        self._config = config
        self._path = persist_path or _DEFAULT_PATH
        self._state = self._load()

    @property
    def snapshot(self) -> ReentrySnapshot:
        spacing = int(self._state.get("buy_spacing_cycles_remaining", 0))
        if not self._state.get("active"):
            return ReentrySnapshot(
                active=False,
                exit_type=ReentryExitType.NONE,
                exit_mid=0.0,
                exit_utc=utc_now(),
                bracket_id="",
                cycles_since_exit=0,
                buy_spacing_cycles_remaining=spacing,
            )
        try:
            exit_type = ReentryExitType(str(self._state.get("exit_type", "none")))
            exit_utc = datetime.fromisoformat(str(self._state["exit_utc"]))
            cycles = int(self._state.get("cycles_since_exit", 0))
            req_cycles, rem_cycles, req_min, rem_min, in_cd = self._cooldown_status(
                exit_type, cycles, exit_utc
            )
            return ReentrySnapshot(
                active=True,
                exit_type=exit_type,
                exit_mid=float(self._state.get("exit_mid", 0.0)),
                exit_utc=exit_utc,
                bracket_id=str(self._state.get("bracket_id", "")),
                cycles_since_exit=cycles,
                cooldown_cycles_required=req_cycles,
                cooldown_cycles_remaining=rem_cycles,
                cooldown_minutes_required=req_min,
                cooldown_minutes_remaining=rem_min,
                in_cooldown=in_cd,
                sl_tier=str(self._state.get("sl_tier", "") or ""),
                entry_price=float(self._state.get("entry_price", 0.0) or 0.0),
                buy_spacing_cycles_remaining=spacing,
            )
        except (KeyError, ValueError, TypeError):
            return ReentrySnapshot.inactive()

    def record_tp_exit(
        self,
        *,
        bracket_id: str,
        exit_mid: float,
    ) -> None:
        if not self._config.alpha_reentry_enabled:
            return
        if (
            self._state.get("active")
            and str(self._state.get("exit_type")) == ReentryExitType.TP.value
            and str(self._state.get("bracket_id", "")) == bracket_id
        ):
            return
        req = max(1, self._config.alpha_reentry_tp_cooldown_cycles)
        self._state = {
            "active": True,
            "exit_type": ReentryExitType.TP.value,
            "exit_mid": exit_mid,
            "exit_utc": utc_now().isoformat(),
            "bracket_id": bracket_id,
            "cycles_since_exit": 0,
            "cooldown_cycles_required": req,
            "buy_spacing_cycles_remaining": 0,
        }
        self._persist()
        logger.info(
            "reentry_gate | tp_exit | bracket=%s | exit_mid=%.6f | cooldown_cycles=%s",
            bracket_id,
            exit_mid,
            req,
        )

    def record_sl_exit(
        self,
        *,
        bracket_id: str,
        exit_mid: float,
        entry_price: float,
    ) -> None:
        if not self._config.alpha_reentry_enabled:
            return
        if (
            self._state.get("active")
            and str(self._state.get("exit_type")) == ReentryExitType.SL.value
            and str(self._state.get("bracket_id", "")) == bracket_id
        ):
            return

        entry = max(float(entry_price), 0.0)
        loss_pct = self._sl_loss_pct(entry, exit_mid) if entry > 0 else 100.0
        scratch_max = max(0.0, self._config.alpha_reentry_scratch_sl_max_loss_pct)
        is_scratch = entry > 0 and loss_pct <= scratch_max
        tier = "scratch" if is_scratch else "full"
        req = (
            max(1, self._config.alpha_reentry_scratch_sl_cooldown_cycles)
            if is_scratch
            else max(1, self._config.alpha_reentry_sl_cooldown_cycles)
        )

        if self._in_sl_cluster():
            cycles = int(self._state.get("cycles_since_exit", 0))
            old_exit = float(self._state.get("exit_mid", exit_mid))
            worst_exit = min(old_exit, exit_mid) if old_exit > 0 else exit_mid
            old_req = int(self._state.get("cooldown_cycles_required", req))
            new_req = min(old_req, req)
            self._state["exit_mid"] = worst_exit
            self._state["cooldown_cycles_required"] = new_req
            self._state["cluster_sl_count"] = int(self._state.get("cluster_sl_count", 1)) + 1
            if is_scratch:
                self._state["sl_tier"] = "scratch"
            self._persist()
            logger.info(
                "reentry_gate | sl_cluster_no_reset | bracket=%s | exit_mid=%.6f | "
                "cycles=%s | tier=%s | cluster_count=%s",
                bracket_id,
                worst_exit,
                cycles,
                self._state.get("sl_tier", tier),
                self._state.get("cluster_sl_count"),
            )
            return

        self._state = {
            "active": True,
            "exit_type": ReentryExitType.SL.value,
            "exit_mid": exit_mid,
            "exit_utc": utc_now().isoformat(),
            "bracket_id": bracket_id,
            "cycles_since_exit": 0,
            "cooldown_cycles_required": req,
            "entry_price": entry,
            "sl_tier": tier,
            "cluster_sl_count": 1,
            "buy_spacing_cycles_remaining": 0,
        }
        self._persist()
        logger.info(
            "reentry_gate | sl_exit | bracket=%s | exit_mid=%.6f | entry=%.6f | "
            "loss_pct=%.3f | tier=%s | cooldown_cycles=%s",
            bracket_id,
            exit_mid,
            entry,
            loss_pct,
            tier,
            req,
        )

    def clear(self, *, reason: str = "buy_placed") -> None:
        if not self._state.get("active"):
            return
        spacing = max(0, int(self._config.alpha_reentry_post_clear_buy_spacing_cycles))
        logger.info("reentry_gate | cleared | reason=%s | reload_spacing_cycles=%s", reason, spacing)
        self._state = {
            "active": False,
            "buy_spacing_cycles_remaining": spacing,
        }
        self._persist()

    def tick_cycle(self) -> None:
        """Increment cooldown counter each engine cycle while gate active."""
        if not self._state.get("active"):
            rem = int(self._state.get("buy_spacing_cycles_remaining", 0))
            if rem > 0:
                self._state["buy_spacing_cycles_remaining"] = rem - 1
                self._persist()
            return
        self._state["cycles_since_exit"] = int(self._state.get("cycles_since_exit", 0)) + 1
        self._persist()

    def blocks_buy(
        self,
        *,
        inventory: InventorySnapshot,
        mid: float,
        ta: Optional["TechnicalAnalysisSnapshot"] = None,
        structure: Optional["MarketStructureSnapshot"] = None,
        momentum_chase: bool = False,
    ) -> Optional[str]:
        """Return HOLD reason if re-entry gate blocks a new buy."""
        if not self._config.alpha_reentry_enabled:
            return None

        spacing = int(self._state.get("buy_spacing_cycles_remaining", 0))
        if spacing > 0:
            total = max(0, int(self._config.alpha_reentry_post_clear_buy_spacing_cycles))
            reason = (
                f"reentry_reload_spacing cycles={total - spacing}/{total}"
            )
            logger.info("reentry_gate | block | %s", reason)
            return reason

        snap = self.snapshot
        if not snap.active:
            return None

        from alpha.decision.tape_participation import evaluate_tape_participation

        participation = evaluate_tape_participation(
            self._config,
            mid=mid,
            structure=structure,
            ta=ta,
        )

        ta_cfg = self._config.alpha_technical_analysis
        ta_required = ta_cfg.enabled

        if snap.exit_type == ReentryExitType.TP:
            blocked = self._cooldown_blocked(snap, prefix="post_tp")
            if blocked:
                return blocked

            dip_pct = self._config.alpha_reentry_tp_dip_pct
            dip_target = snap.exit_mid * (1.0 - dip_pct / 100.0) if snap.exit_mid > 0 else 0.0
            if dip_target > 0 and mid > dip_target:
                reason = (
                    f"reentry_tp_await_dip mid={mid:.6f} need<={dip_target:.6f} "
                    f"({dip_pct:.2f}% below tp_exit={snap.exit_mid:.6f})"
                )
                logger.info("reentry_gate | block | %s", reason)
                return reason

            if not momentum_chase and not self._inventory_weak_enough(inventory):
                reason = f"reentry_tp_await_weakness dev={inventory.deviation:+.3f}"
                logger.info("reentry_gate | block | %s", reason)
                return reason

            if ta_required:
                blocked = self._ta_reentry_blocked(
                    ta, self._config.alpha_reentry_tp_min_ta_score, prefix="reentry_tp"
                )
                if blocked:
                    logger.info("reentry_gate | block | %s", blocked)
                    return blocked

            return None

        if snap.exit_type == ReentryExitType.SL:
            self._try_recovery_early_release(mid=mid, ta=ta, structure=structure)
            snap = self.snapshot

            blocked = self._cooldown_blocked(snap, prefix="post_sl")
            if blocked:
                return blocked

            is_scratch = str(self._state.get("sl_tier", "")) == "scratch"

            if not momentum_chase and not is_scratch and structure is not None:
                if structure.trend == "bearish" or structure.breakout_down:
                    reason = (
                        f"reentry_sl_await_stabilization trend={structure.trend} "
                        f"breakout_down={structure.breakout_down}"
                    )
                    logger.info("reentry_gate | block | %s", reason)
                    return reason
                recent_low = structure.recent_low
                if recent_low > 0 and mid > 0:
                    bounce_pct = self._config.alpha_reentry_sl_stabilization_pct
                    need_mid = recent_low * (1.0 + bounce_pct / 100.0)
                    if mid < need_mid:
                        reason = (
                            f"reentry_sl_await_bounce mid={mid:.6f} need>={need_mid:.6f} "
                            f"({bounce_pct:.2f}% above recent_low)"
                        )
                        logger.info("reentry_gate | block | %s", reason)
                        return reason

            if ta_required:
                min_score = (
                    self._config.alpha_reentry_tp_min_ta_score
                    if is_scratch
                    else self._config.alpha_reentry_sl_min_ta_score
                )
                blocked = self._ta_reentry_blocked(
                    ta,
                    min_score,
                    prefix="reentry_scratch" if is_scratch else "reentry_sl",
                    require_non_bearish=not is_scratch and not participation.active,
                )
                if blocked:
                    logger.info("reentry_gate | block | %s", blocked)
                    return blocked

            if not momentum_chase and not self._inventory_weak_enough(inventory):
                reason = f"reentry_sl_await_weakness dev={inventory.deviation:+.3f}"
                logger.info("reentry_gate | block | %s", reason)
                return reason

            return None

        return None

    def _sl_loss_pct(self, entry: float, exit_mid: float) -> float:
        """Positive = loss (sold below entry), negative = scratch above entry."""
        return (entry - exit_mid) / entry * 100.0

    def _in_sl_cluster(self) -> bool:
        if not self._state.get("active"):
            return False
        if str(self._state.get("exit_type")) != ReentryExitType.SL.value:
            return False
        window = max(0.0, self._config.alpha_reentry_sl_cluster_window_seconds)
        if window <= 0:
            return False
        try:
            exit_utc = datetime.fromisoformat(str(self._state["exit_utc"]))
        except (KeyError, ValueError, TypeError):
            return False
        elapsed = (utc_now() - exit_utc).total_seconds()
        return elapsed <= window

    def _try_recovery_early_release(
        self,
        *,
        mid: float,
        ta: Optional["TechnicalAnalysisSnapshot"],
        structure: Optional["MarketStructureSnapshot"] = None,
    ) -> bool:
        if not self._config.alpha_reentry_recovery_enabled:
            return False
        if not self._state.get("active"):
            return False
        if str(self._state.get("exit_type")) != ReentryExitType.SL.value:
            return False
        cycles = int(self._state.get("cycles_since_exit", 0))
        if cycles < max(0, int(self._config.alpha_reentry_recovery_min_cycles)):
            return False
        exit_mid = float(self._state.get("exit_mid", 0.0))
        if exit_mid <= 0 or mid <= 0:
            return False
        release_pct = max(0.0, self._config.alpha_reentry_recovery_release_pct)
        need = exit_mid * (1.0 + release_pct / 100.0)
        if mid < need:
            return False
        if ta is not None and ta.enabled and ta.bias == "bearish":
            from alpha.decision.tape_participation import tape_participation_waives_bearish_buy_block

            if not tape_participation_waives_bearish_buy_block(
                self._config,
                mid=mid,
                structure=structure,
                ta=ta,
            ):
                return False
        req = int(
            self._state.get(
                "cooldown_cycles_required",
                self._config.alpha_reentry_sl_cooldown_cycles,
            )
        )
        if cycles >= req:
            return False
        self._state["cycles_since_exit"] = req
        self._persist()
        logger.info(
            "reentry_gate | recovery_early_release | mid=%.6f | exit=%.6f | need=%.6f",
            mid,
            exit_mid,
            need,
        )
        return True

    def _cooldown_status(
        self,
        exit_type: ReentryExitType,
        cycles_since_exit: int,
        exit_utc: datetime,
    ) -> tuple[int, int, float, float, bool]:
        if exit_type == ReentryExitType.TP:
            req_cycles = max(1, self._config.alpha_reentry_tp_cooldown_cycles)
            req_min = max(0.0, self._config.alpha_reentry_tp_cooldown_minutes)
        else:
            stored = self._state.get("cooldown_cycles_required")
            req_cycles = max(1, int(stored)) if stored is not None else max(
                1, self._config.alpha_reentry_sl_cooldown_cycles
            )
            req_min = max(0.0, self._config.alpha_reentry_sl_cooldown_minutes)

        rem_cycles = max(0, req_cycles - cycles_since_exit)
        elapsed_min = (utc_now() - exit_utc).total_seconds() / 60.0
        rem_min = max(0.0, req_min - elapsed_min) if req_min > 0 else 0.0
        in_cd = rem_cycles > 0 or rem_min > 0
        return req_cycles, rem_cycles, req_min, rem_min, in_cd

    def _cooldown_blocked(self, snap: ReentrySnapshot, *, prefix: str) -> Optional[str]:
        """Hard block during post-exit cooldown — TA/inventory cannot override."""
        if snap.cycles_since_exit < snap.cooldown_cycles_required:
            tier = self._state.get("sl_tier", "")
            tier_note = f" tier={tier}" if tier else ""
            reason = (
                f"{prefix}_cooldown cycles={snap.cycles_since_exit}/"
                f"{snap.cooldown_cycles_required}{tier_note}"
            )
            logger.info("reentry_gate | block | %s", reason)
            return reason
        if snap.cooldown_minutes_required > 0 and snap.cooldown_minutes_remaining > 0:
            elapsed = snap.cooldown_minutes_required - snap.cooldown_minutes_remaining
            reason = (
                f"{prefix}_cooldown minutes={elapsed:.1f}/"
                f"{snap.cooldown_minutes_required:.1f}"
            )
            logger.info("reentry_gate | block | %s", reason)
            return reason
        return None

    def _ta_reentry_blocked(
        self,
        ta: Optional["TechnicalAnalysisSnapshot"],
        min_score: float,
        *,
        prefix: str,
        require_non_bearish: bool = False,
    ) -> Optional[str]:
        if ta is None or not ta.enabled:
            return f"{prefix}_ta_warming_up"
        if ta.buy_score < min_score:
            return f"{prefix}_ta_score={ta.buy_score:.2f}<{min_score:.2f}"
        if require_non_bearish and ta.bias == "bearish":
            return f"{prefix}_ta_bearish bias={ta.bias}"
        return None

    def _inventory_weak_enough(self, inventory: InventorySnapshot) -> bool:
        return inventory.deviation <= -self._config.alpha_weakness_deviation

    def _load(self) -> Dict[str, Any]:
        if not self._path.exists():
            return {"active": False}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"active": False}
        except (json.JSONDecodeError, OSError, ValueError):
            return {"active": False}

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
