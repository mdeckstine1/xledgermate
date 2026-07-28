"""Drawdown reload — sell-off lane that funds RLUSD acquisition ammo on confirmed drops.

Set-and-forget: staged XRP→RLUSD recycle when 24h price is already down.
Does not rewrite accumulation; hands powder to existing dip/accumulate bids.
Distinct from post-run chop reload (near highs) and harvest (UP-leg trim).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from alpha.decision.harvest_watch import RollingMoveSnapshot, rolling_move_snapshot
from alpha.types import utc_now
from config.settings import BotConfig

if TYPE_CHECKING:
    from alpha.types import BalanceSnapshot, InventorySnapshot

logger = logging.getLogger(__name__)

_DEFAULT_SESSION_PATH = Path("logs/drawdown_reload_session.json")


@dataclass(frozen=True)
class DrawdownReloadKnobs:
    active: bool
    armed: bool
    sell_offset_pct: float
    max_pending_sells: int
    min_edge_pct: float
    stage: int  # 1 or 2 when armed
    target_sell_xrp: float


@dataclass(frozen=True)
class DrawdownReloadSnapshot:
    enabled: bool
    active: bool
    armed: bool
    phase: str  # off | idle | watching | armed | executing | capped
    headline: str
    detail: str
    entry_allowed: bool
    reason: str
    signals: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    stage: int = 0
    move_pct: float = 0.0
    target_sell_xrp: float = 0.0
    xrp_sold_in_window: float = 0.0
    bag_pct_cap: float = 0.0
    skynet_nudge: str = ""
    rolling: Optional[RollingMoveSnapshot] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
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
            "stage": self.stage,
            "move_pct": round(self.move_pct, 3),
            "target_sell_xrp": round(self.target_sell_xrp, 4),
            "xrp_sold_in_window": round(self.xrp_sold_in_window, 4),
            "bag_pct_cap": round(self.bag_pct_cap, 2),
            "skynet_nudge": self.skynet_nudge,
        }
        if self.rolling is not None:
            out["rolling"] = self.rolling.to_dict()
        return out


class DrawdownReloadSessionTracker:
    """Multi-day event window for staged drawdown funding sells."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_SESSION_PATH
        self._state = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self._path.is_file():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def _window_hours(self, config: BotConfig) -> float:
        return max(1.0, float(getattr(config, "alpha_drawdown_reload_window_hours", 48.0)))

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
                "stage1_placed": False,
                "stage2_placed": False,
                "sells_placed": 0,
                "xrp_sold": 0.0,
                "rlusd_filled_xrp_equiv": 0.0,
                "event_ref_mid": 0.0,
            }
            self._save()

    def stage1_placed(self, config: BotConfig) -> bool:
        self._maybe_roll_window(config)
        return bool(self._state.get("stage1_placed"))

    def stage2_placed(self, config: BotConfig) -> bool:
        self._maybe_roll_window(config)
        return bool(self._state.get("stage2_placed"))

    def sells_placed(self, config: BotConfig) -> int:
        self._maybe_roll_window(config)
        return int(self._state.get("sells_placed", 0))

    def xrp_sold(self, config: BotConfig) -> float:
        self._maybe_roll_window(config)
        return float(self._state.get("xrp_sold", 0.0) or 0.0)

    def can_place_sell(self, config: BotConfig) -> bool:
        cap = int(getattr(config, "alpha_drawdown_reload_max_sells_per_window", 2))
        return self.sells_placed(config) < max(1, cap)

    def record_sell_placed(
        self,
        *,
        size_xrp: float,
        stage: int,
        mid: float,
        config: BotConfig | None = None,
    ) -> None:
        if config is not None:
            self._maybe_roll_window(config)
        if size_xrp <= 0:
            return
        self._state["sells_placed"] = int(self._state.get("sells_placed", 0)) + 1
        self._state["xrp_sold"] = float(self._state.get("xrp_sold", 0.0) or 0.0) + float(size_xrp)
        if stage <= 1:
            self._state["stage1_placed"] = True
        else:
            self._state["stage2_placed"] = True
            self._state["stage1_placed"] = True
        if mid > 0 and float(self._state.get("event_ref_mid") or 0) <= 0:
            self._state["event_ref_mid"] = float(mid)
        self._save()
        logger.info(
            "drawdown_reload_session | sell_placed | stage=%s size=%.4f sells=%s",
            stage,
            size_xrp,
            self._state.get("sells_placed"),
        )

    def record_fill(self, *, rlusd_xrp_equiv: float) -> None:
        if rlusd_xrp_equiv <= 0:
            return
        self._state["rlusd_filled_xrp_equiv"] = float(
            self._state.get("rlusd_filled_xrp_equiv", 0.0) or 0.0
        ) + rlusd_xrp_equiv
        self._save()


def _abs_drop_pct(move_pct: float) -> float:
    """Positive magnitude of a down move; 0 if flat/up."""
    if move_pct >= 0:
        return 0.0
    return abs(move_pct)


def compute_drawdown_sell_size_xrp(
    config: BotConfig,
    *,
    stage: int,
    portfolio_xrp_equiv: float,
    balances: "BalanceSnapshot",
    xrp_sold_in_window: float,
) -> float:
    if portfolio_xrp_equiv <= 0 or stage <= 0:
        return 0.0
    total_cap_pct = max(0.0, float(getattr(config, "alpha_drawdown_reload_total_bag_pct", 4.0)))
    stage1_pct = max(0.0, float(getattr(config, "alpha_drawdown_reload_stage1_bag_pct", 2.0)))
    stage2_pct = max(0.0, float(getattr(config, "alpha_drawdown_reload_stage2_bag_pct", 2.0)))
    stage_pct = stage1_pct if stage <= 1 else stage2_pct
    if stage_pct <= 0 or total_cap_pct <= 0:
        return 0.0

    stage_size = portfolio_xrp_equiv * (stage_pct / 100.0)
    total_budget = portfolio_xrp_equiv * (total_cap_pct / 100.0)
    remaining = max(0.0, total_budget - max(0.0, xrp_sold_in_window))
    desired = min(stage_size, remaining)

    hard_cap = float(getattr(config, "alpha_drawdown_reload_max_sell_xrp", 0.0))
    if hard_cap > 0:
        desired = min(desired, hard_cap)

    available = max(0.0, float(balances.xrp) - float(config.xrp_reserve))
    desired = min(desired, available)
    min_sz = float(config.min_order_size_xrp)
    if desired < min_sz * 0.5:
        return 0.0
    return round(max(0.0, desired), 4)


def drawdown_reload_knobs_from_snapshot(
    snap: DrawdownReloadSnapshot,
    config: BotConfig,
) -> DrawdownReloadKnobs:
    if not snap.armed:
        return DrawdownReloadKnobs(
            active=snap.active,
            armed=False,
            sell_offset_pct=float(
                config.alpha_sell_limit_offset_pct or config.alpha_ask_offset_pct
            ),
            max_pending_sells=int(config.alpha_max_pending_sells),
            min_edge_pct=float(config.alpha_min_edge_threshold_pct),
            stage=0,
            target_sell_xrp=0.0,
        )
    return DrawdownReloadKnobs(
        active=True,
        armed=True,
        sell_offset_pct=float(getattr(config, "alpha_drawdown_reload_sell_offset_pct", 0.08)),
        max_pending_sells=int(getattr(config, "alpha_drawdown_reload_max_pending_sells", 1)),
        min_edge_pct=float(getattr(config, "alpha_drawdown_reload_min_edge_pct", 0.05)),
        stage=max(1, int(snap.stage)),
        target_sell_xrp=float(snap.target_sell_xrp),
    )


def evaluate_drawdown_reload(
    config: BotConfig,
    *,
    inventory: "InventorySnapshot",
    mid: float,
    balances: Optional["BalanceSnapshot"] = None,
    pending_drawdown_sells: int = 0,
    decision_action: str = "hold",
    session: Optional[DrawdownReloadSessionTracker] = None,
    price_history_path: Path | None = None,
) -> DrawdownReloadSnapshot:
    disabled = DrawdownReloadSnapshot(
        enabled=False,
        active=False,
        armed=False,
        phase="off",
        headline="DRAWDOWN RELOAD OFF",
        detail="alpha_drawdown_reload_enabled=false",
        entry_allowed=False,
        reason="disabled",
    )
    if not getattr(config, "alpha_drawdown_reload_enabled", True):
        return disabled

    hours = float(getattr(config, "alpha_drawdown_reload_hours", 24.0))
    watch_pct = float(getattr(config, "alpha_drawdown_reload_watch_pct", 2.0))
    stage1_pct = float(getattr(config, "alpha_drawdown_reload_stage1_arm_pct", 2.5))
    stage2_pct = float(getattr(config, "alpha_drawdown_reload_stage2_arm_pct", 4.0))
    bag_cap = float(getattr(config, "alpha_drawdown_reload_total_bag_pct", 4.0))
    min_dev = float(getattr(config, "alpha_drawdown_reload_min_deviation", 0.0))
    min_xrp_ratio = float(getattr(config, "alpha_drawdown_reload_min_xrp_ratio", 0.65))

    rolling = rolling_move_snapshot(
        config,
        mid=mid,
        hours=hours,
        price_history_path=price_history_path,
    )
    if rolling is None:
        return DrawdownReloadSnapshot(
            enabled=True,
            active=False,
            armed=False,
            phase="idle",
            headline="DRAWDOWN IDLE",
            detail="insufficient price history for rolling move",
            entry_allowed=False,
            reason="warming_up",
            bag_pct_cap=bag_cap,
        )

    drop = _abs_drop_pct(rolling.move_pct)
    sess = session or DrawdownReloadSessionTracker()
    xrp_sold = sess.xrp_sold(config)
    signals: list[str] = [f"move_{int(hours)}h={rolling.move_pct:+.2f}%"]
    if drop > 0:
        signals.append(f"drop={drop:.2f}%")

    blockers: list[str] = []
    if inventory.pause_asks:
        blockers.append("pause_asks")
    if inventory.deviation < min_dev:
        blockers.append(f"dev={inventory.deviation:+.3f}<{min_dev:+.3f}")
    if float(inventory.xrp_ratio) < min_xrp_ratio:
        blockers.append(f"xrp_ratio={inventory.xrp_ratio:.3f}<{min_xrp_ratio:.3f}")
    if not sess.can_place_sell(config):
        blockers.append("drawdown_window_cap_reached")

    portfolio = float(inventory.portfolio_xrp_equiv or 0.0)
    if balances is not None and portfolio <= 0 and balances.mid_rlusd_per_xrp:
        mid_b = float(balances.mid_rlusd_per_xrp)
        if mid_b > 0:
            portfolio = float(balances.xrp) + float(balances.rlusd) / mid_b

    if pending_drawdown_sells > 0:
        stage = 2 if sess.stage1_placed(config) and drop >= stage2_pct else 1
        if not sess.stage1_placed(config):
            stage = 1
        return DrawdownReloadSnapshot(
            enabled=True,
            active=True,
            armed=True,
            phase="executing",
            headline="DRAWDOWN RELOADING — acquisition funding sell live",
            detail=f"stage={stage} · {rolling.move_pct:+.2f}% over {hours:.0f}h",
            entry_allowed=True,
            reason="executing",
            signals=tuple(signals),
            blockers=tuple(blockers),
            stage=stage,
            move_pct=rolling.move_pct,
            target_sell_xrp=0.0,
            xrp_sold_in_window=xrp_sold,
            bag_pct_cap=bag_cap,
            rolling=rolling,
            skynet_nudge="Drawdown funding ask live — powder feeds accumulate/dip buys over multi-day reclaim.",
        )

    if drop < watch_pct:
        return DrawdownReloadSnapshot(
            enabled=True,
            active=False,
            armed=False,
            phase="idle",
            headline="DRAWDOWN IDLE — no confirmed sell-off",
            detail=f"{rolling.move_pct:+.2f}% over {hours:.0f}h (watch at −{watch_pct:g}%)",
            entry_allowed=False,
            reason="no_drawdown",
            signals=tuple(signals),
            move_pct=rolling.move_pct,
            xrp_sold_in_window=xrp_sold,
            bag_pct_cap=bag_cap,
            rolling=rolling,
            skynet_nudge="No confirmed drawdown — accumulate lane unchanged.",
        )

    # Determine next stage
    stage = 0
    if drop >= stage1_pct and not sess.stage1_placed(config):
        stage = 1
    elif drop >= stage2_pct and sess.stage1_placed(config) and not sess.stage2_placed(config):
        stage = 2

    if stage == 0:
        if sess.stage1_placed(config) and sess.stage2_placed(config):
            return DrawdownReloadSnapshot(
                enabled=True,
                active=True,
                armed=False,
                phase="capped",
                headline="DRAWDOWN FUNDED — event stages complete",
                detail=(
                    f"{rolling.move_pct:+.2f}% · sold {xrp_sold:.1f} XRP this window "
                    f"(cap {bag_cap:g}% bag)"
                ),
                entry_allowed=False,
                reason="stages_complete",
                signals=tuple(signals),
                move_pct=rolling.move_pct,
                xrp_sold_in_window=xrp_sold,
                bag_pct_cap=bag_cap,
                rolling=rolling,
                skynet_nudge="Drawdown stages done — patient multi-day dip/accumulate redeploy with RLUSD.",
            )
        return DrawdownReloadSnapshot(
            enabled=True,
            active=True,
            armed=False,
            phase="watching",
            headline="DRAWDOWN WATCHING — sell-off forming",
            detail=(
                f"{rolling.move_pct:+.2f}% over {hours:.0f}h · "
                f"stage1 at −{stage1_pct:g}% · stage2 at −{stage2_pct:g}%"
            ),
            entry_allowed=False,
            reason="watching",
            signals=tuple(signals),
            move_pct=rolling.move_pct,
            xrp_sold_in_window=xrp_sold,
            bag_pct_cap=bag_cap,
            rolling=rolling,
            skynet_nudge=(
                "Confirmed weakness forming — staged acquisition funding arms at stage thresholds. "
                "Do not dump full bag; wait for stage arm."
            ),
        )

    target = 0.0
    if balances is not None:
        target = compute_drawdown_sell_size_xrp(
            config,
            stage=stage,
            portfolio_xrp_equiv=portfolio,
            balances=balances,
            xrp_sold_in_window=xrp_sold,
        )
    else:
        # Size estimate without balances (HUD probe)
        pct = float(
            getattr(config, "alpha_drawdown_reload_stage1_bag_pct", 2.0)
            if stage <= 1
            else getattr(config, "alpha_drawdown_reload_stage2_bag_pct", 2.0)
        )
        target = round(max(0.0, portfolio * (pct / 100.0)), 4)

    if target <= 0:
        blockers.append("size_below_min")

    if blockers:
        return DrawdownReloadSnapshot(
            enabled=True,
            active=True,
            armed=False,
            phase="watching",
            headline="DRAWDOWN BLOCKED — cannot fund yet",
            detail="; ".join(blockers),
            entry_allowed=False,
            reason="blocked",
            signals=tuple(signals),
            blockers=tuple(blockers),
            stage=stage,
            move_pct=rolling.move_pct,
            target_sell_xrp=target,
            xrp_sold_in_window=xrp_sold,
            bag_pct_cap=bag_cap,
            rolling=rolling,
            skynet_nudge="Drawdown threshold met but blockers prevent sell — check inventory/pause/caps.",
        )

    return DrawdownReloadSnapshot(
        enabled=True,
        active=True,
        armed=True,
        phase="armed",
        headline=f"DRAWDOWN ARMED — stage {stage} acquisition funding",
        detail=(
            f"{rolling.move_pct:+.2f}% over {hours:.0f}h · sell ~{target:.1f} XRP "
            f"(event cap {bag_cap:g}% bag)"
        ),
        entry_allowed=True,
        reason="armed",
        signals=tuple(signals) + (f"stage={stage}",),
        stage=stage,
        move_pct=rolling.move_pct,
        target_sell_xrp=target,
        xrp_sold_in_window=xrp_sold,
        bag_pct_cap=bag_cap,
        rolling=rolling,
        skynet_nudge=(
            f"Stage {stage} sell-off funding — recycle ~{target:.1f} XRP into RLUSD for dip buys. "
            "Reclaim may take days; keep accumulate/dip patient."
        ),
    )


def build_drawdown_reload_context_block(snap: Dict[str, Any]) -> str:
    if not snap:
        return "=== Drawdown reload (sell-off acquisition funding) ===\n(not evaluated)"
    roll = snap.get("rolling") or {}
    return "\n".join(
        [
            "=== Drawdown reload (sell-off lane → RLUSD acquisition ammo; set-and-forget) ===",
            f"phase={snap.get('phase')} armed={snap.get('armed')} entry_allowed={snap.get('entry_allowed')} "
            f"stage={snap.get('stage')}",
            f"headline={snap.get('headline')}",
            f"detail={snap.get('detail')}",
            f"move_pct={snap.get('move_pct')} target_sell_xrp={snap.get('target_sell_xrp')} "
            f"xrp_sold_window={snap.get('xrp_sold_in_window')} bag_cap_pct={snap.get('bag_pct_cap')}",
            f"rolling_high={roll.get('high')} rolling_low={roll.get('low')} bounce={roll.get('bounce_from_low_pct')}",
            f"signals={snap.get('signals')}",
            f"blockers={snap.get('blockers')}",
            f"skynet_nudge={snap.get('skynet_nudge') or ''}",
        ]
    )
