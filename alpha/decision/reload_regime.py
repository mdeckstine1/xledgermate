"""RLUSD reload regime — fund accumulation by selling XRP in post-run chop (not into the rip)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

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
    from alpha.types import BalanceSnapshot, InventorySnapshot

logger = logging.getLogger(__name__)

_DEFAULT_SESSION_PATH = Path("logs/reload_session.json")


@dataclass(frozen=True)
class ReloadKnobs:
    active: bool
    armed: bool
    sell_offset_pct: float
    max_pending_sells: int
    min_edge_pct: float
    target_floor_xrp_equiv: float


@dataclass(frozen=True)
class ReloadRegimeSnapshot:
    enabled: bool
    active: bool
    armed: bool
    phase: str  # off | watching | armed | executing | funded | blocked
    headline: str
    detail: str
    entry_allowed: bool
    reason: str
    signals: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    rlusd_xrp_equiv: float = 0.0
    deploy_floor_xrp_equiv: float = 0.0
    shortfall_xrp_equiv: float = 0.0
    blocks_accumulation: bool = False
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
            "rlusd_xrp_equiv": round(self.rlusd_xrp_equiv, 2),
            "deploy_floor_xrp_equiv": round(self.deploy_floor_xrp_equiv, 2),
            "shortfall_xrp_equiv": round(self.shortfall_xrp_equiv, 2),
            "blocks_accumulation": self.blocks_accumulation,
            "skynet_nudge": self.skynet_nudge,
        }


class ReloadSessionTracker:
    """Rolling window for funding sells (chop reload tranches)."""

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
        return max(0.5, float(getattr(config, "alpha_reload_window_hours", 8.0)))

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
                "sells_placed": 0,
                "rlusd_filled_xrp_equiv": 0.0,
            }
            self._save()

    def sells_placed(self, config: BotConfig) -> int:
        self._maybe_roll_window(config)
        return int(self._state.get("sells_placed", 0))

    def can_place_sell(self, config: BotConfig) -> bool:
        cap = int(getattr(config, "alpha_reload_max_sells_per_window", 1))
        return self.sells_placed(config) < cap

    def record_sell_placed(self, *, size_xrp: float, mid: float, config: BotConfig | None = None) -> None:
        if config is not None:
            self._maybe_roll_window(config)
        if size_xrp <= 0 or mid <= 0:
            return
        self._state["sells_placed"] = int(self._state.get("sells_placed", 0)) + 1
        self._save()
        logger.info(
            "reload_session | sell_placed | sells=%s",
            self._state.get("sells_placed"),
        )

    def record_fill(self, *, rlusd_xrp_equiv: float) -> None:
        if rlusd_xrp_equiv <= 0:
            return
        self._state["rlusd_filled_xrp_equiv"] = float(
            self._state.get("rlusd_filled_xrp_equiv", 0.0)
        ) + rlusd_xrp_equiv
        self._save()


def rlusd_deploy_xrp_equiv(rlusd_balance: float, mid: float) -> float:
    if mid <= 0 or rlusd_balance <= 0:
        return 0.0
    return rlusd_balance / mid


def deploy_floor_xrp_equiv(config: BotConfig, portfolio_xrp_equiv: float = 0.0) -> float:
    """Powder floor in XRP-eq. % of bag wins when set so a bigger bag keeps a bigger floor."""
    pct = float(getattr(config, "alpha_reload_min_rlusd_deploy_pct", 0.0) or 0.0)
    if pct > 0 and portfolio_xrp_equiv > 0:
        return max(0.0, portfolio_xrp_equiv * (pct / 100.0))
    return max(0.0, float(getattr(config, "alpha_reload_min_rlusd_deploy_xrp_equiv", 45.0) or 0.0))


def powder_ceiling_xrp_equiv(config: BotConfig, portfolio_xrp_equiv: float = 0.0) -> float:
    """Idle-powder deploy trigger in XRP-eq. % of bag wins when set; 0 = off."""
    pct = float(getattr(config, "alpha_powder_ceiling_pct", 0.0) or 0.0)
    if pct > 0 and portfolio_xrp_equiv > 0:
        return max(0.0, portfolio_xrp_equiv * (pct / 100.0))
    return max(0.0, float(getattr(config, "alpha_powder_ceiling_xrp_equiv", 0.0) or 0.0))


def reload_shortfall_xrp_equiv(
    config: BotConfig,
    *,
    rlusd_balance: float,
    mid: float,
    portfolio_xrp_equiv: float = 0.0,
) -> float:
    if mid <= 0:
        return 0.0
    current = rlusd_deploy_xrp_equiv(rlusd_balance, mid)
    floor = deploy_floor_xrp_equiv(config, portfolio_xrp_equiv)
    return max(0.0, floor - current)


def reload_blocks_accumulation_bids(
    config: BotConfig,
    *,
    rlusd_balance: float,
    mid: float,
    pending_funding_sells: int = 0,
    portfolio_xrp_equiv: float = 0.0,
) -> bool:
    """Policy 4: no accumulation bids until deploy floor met (reload funds in chop)."""
    if not getattr(config, "alpha_reload_block_accumulation_until_funded", True):
        return False
    if not getattr(config, "alpha_reload_regime_enabled", True):
        return False
    if mid <= 0:
        return False
    if pending_funding_sells > 0:
        return True
    return reload_shortfall_xrp_equiv(
        config,
        rlusd_balance=rlusd_balance,
        mid=mid,
        portfolio_xrp_equiv=portfolio_xrp_equiv,
    ) > (
        config.min_order_size_xrp * 0.5
    )


def detect_post_run_consolidation(
    config: BotConfig,
    *,
    mid: float,
    structure: Optional["MarketStructureSnapshot"],
    tape_active: bool,
) -> tuple[bool, str]:
    """Chop-after-run: near highs, run proven, slope off — not active breakout."""
    if structure is None or mid <= 0:
        return False, "no_structure"
    if structure.breakout_down or structure.trend == "bearish":
        return False, "structure_bearish"

    min_run = float(getattr(config, "alpha_reload_post_run_min_move_pct", 0.25))
    if structure.recent_low > 0:
        run_pct = (mid - structure.recent_low) / structure.recent_low * 100.0
        if run_pct < min_run:
            return False, f"run_move={run_pct:.2f}%<{min_run:g}%"
    else:
        return False, "no_recent_low"

    near_pct = float(getattr(config, "alpha_reload_near_high_pct", 0.15))
    if structure.recent_high > 0 and mid < structure.recent_high * (1.0 - near_pct / 100.0):
        return False, "not_near_recent_high"

    if structure.breakout_up and tape_active:
        return False, "still_breaking_out"

    if getattr(config, "alpha_reload_require_slope_flat", True):
        slope_up = _short_term_slope_positive(
            samples=int(getattr(config, "alpha_tape_slope_samples", 8)),
            price_source=normalize_price_source(
                str(getattr(config, "alpha_structure_price_source", "ask")),
                default="mid",
            ),
            min_lift_pct=float(getattr(config, "alpha_tape_slope_min_lift_pct", 0.04)),
        )
        if slope_up and tape_active:
            return False, "slope_still_up_on_tape"

    if structure.trend == "neutral":
        return True, "post_run_chop_neutral"
    if structure.trend == "bullish" and not structure.breakout_up:
        return True, "post_run_digest_bullish"
    return False, f"trend={structure.trend}"


def reload_knobs_from_snapshot(
    snap: ReloadRegimeSnapshot,
    config: BotConfig,
) -> ReloadKnobs:
    if not snap.armed:
        return ReloadKnobs(
            active=snap.active,
            armed=False,
            sell_offset_pct=float(
                config.alpha_sell_limit_offset_pct or config.alpha_ask_offset_pct
            ),
            max_pending_sells=int(config.alpha_max_pending_sells),
            min_edge_pct=float(config.alpha_min_edge_threshold_pct),
            target_floor_xrp_equiv=float(snap.deploy_floor_xrp_equiv or 0.0),
        )
    return ReloadKnobs(
        active=True,
        armed=True,
        sell_offset_pct=float(getattr(config, "alpha_reload_sell_offset_pct", 0.06)),
        max_pending_sells=int(getattr(config, "alpha_reload_max_pending_sells", 1)),
        min_edge_pct=float(getattr(config, "alpha_reload_min_edge_pct", 0.05)),
        target_floor_xrp_equiv=float(snap.deploy_floor_xrp_equiv or 0.0),
    )


def evaluate_reload_regime(
    config: BotConfig,
    *,
    inventory: "InventorySnapshot",
    mid: float,
    structure: Optional["MarketStructureSnapshot"],
    ta: Optional["TechnicalAnalysisSnapshot"],
    operator_market_regime: str = "neutral",
    rlusd_balance: float = 0.0,
    pending_funding_sells: int = 0,
    decision_action: str = "hold",
    session: Optional[ReloadSessionTracker] = None,
) -> ReloadRegimeSnapshot:
    disabled = ReloadRegimeSnapshot(
        enabled=False,
        active=False,
        armed=False,
        phase="off",
        headline="RELOAD OFF",
        detail="alpha_reload_regime_enabled=false",
        entry_allowed=False,
        reason="disabled",
    )
    if not getattr(config, "alpha_reload_regime_enabled", True):
        return disabled

    regime = normalize_market_regime(operator_market_regime)
    portfolio = float(getattr(inventory, "portfolio_xrp_equiv", 0.0) or 0.0)
    floor = deploy_floor_xrp_equiv(config, portfolio)
    rlusd_xeq = rlusd_deploy_xrp_equiv(rlusd_balance, mid)
    shortfall = reload_shortfall_xrp_equiv(
        config,
        rlusd_balance=rlusd_balance,
        mid=mid,
        portfolio_xrp_equiv=portfolio,
    )
    blocks_acc = reload_blocks_accumulation_bids(
        config,
        rlusd_balance=rlusd_balance,
        mid=mid,
        pending_funding_sells=pending_funding_sells,
        portfolio_xrp_equiv=portfolio,
    )

    tape = evaluate_tape_participation(config, mid=mid, structure=structure, ta=ta)
    chop_ok, chop_reason = detect_post_run_consolidation(
        config,
        mid=mid,
        structure=structure,
        tape_active=tape.active,
    )

    signals: list[str] = []
    if chop_ok:
        signals.append(f"chop:{chop_reason}")
    if shortfall > 0:
        signals.append(f"shortfall={shortfall:.1f}xrp_equiv")
    if regime == "bull":
        signals.append("operator_regime_bull")

    blockers: list[str] = []
    if inventory.pause_asks:
        blockers.append("pause_asks")
    if regime == "bear":
        blockers.append("operator_regime_bear")
    min_dev = float(getattr(config, "alpha_reload_min_deviation", 0.0))
    if inventory.deviation < min_dev:
        blockers.append(f"dev={inventory.deviation:+.3f}<{min_dev:+.3f}")
    sess = session or ReloadSessionTracker()
    if not sess.can_place_sell(config):
        blockers.append("reload_window_cap_reached")

    if shortfall <= config.min_order_size_xrp * 0.25:
        return ReloadRegimeSnapshot(
            enabled=True,
            active=False,
            armed=False,
            phase="funded",
            headline="RELOAD FUNDED — deploy floor met",
            detail=f"rlusd_xrp_equiv={rlusd_xeq:.1f} floor={floor:.1f}",
            entry_allowed=False,
            reason="funded",
            signals=tuple(signals),
            blocks_accumulation=False,
            rlusd_xrp_equiv=rlusd_xeq,
            deploy_floor_xrp_equiv=floor,
            shortfall_xrp_equiv=0.0,
            skynet_nudge="Deploy floor met — accumulation may bid when tape arms.",
        )

    action = (decision_action or "hold").lower()
    if pending_funding_sells > 0 or action == "place_ask":
        return ReloadRegimeSnapshot(
            enabled=True,
            active=True,
            armed=True,
            phase="executing",
            headline="RELOADING — funding sell live",
            detail=chop_reason if chop_ok else "awaiting funding fill",
            entry_allowed=True,
            reason="executing",
            signals=tuple(signals),
            # Honor alpha_reload_block_accumulation_until_funded (do not hard-block when off).
            blocks_accumulation=blocks_acc,
            rlusd_xrp_equiv=rlusd_xeq,
            deploy_floor_xrp_equiv=floor,
            shortfall_xrp_equiv=shortfall,
            skynet_nudge=(
                "Funding sell pending — accumulation blocked until fill (policy 4)."
                if blocks_acc
                else "Funding sell pending — residual RLUSD may still bid when tape arms."
            ),
        )

    if not chop_ok and shortfall > 0:
        detail = chop_reason
        if tape.active:
            detail += " — waiting for post-run chop (not selling into rip)"
        return ReloadRegimeSnapshot(
            enabled=True,
            active=True,
            armed=False,
            phase="watching",
            headline="RELOAD WATCHING — RLUSD low, wait for chop",
            detail=detail,
            entry_allowed=False,
            reason="watching",
            signals=tuple(signals),
            blocks_accumulation=blocks_acc,
            rlusd_xrp_equiv=rlusd_xeq,
            deploy_floor_xrp_equiv=floor,
            shortfall_xrp_equiv=shortfall,
            skynet_nudge=(
                "RLUSD below deploy floor but post-run chop not confirmed — "
                "do NOT strength-sell into active rip; accumulation blocked until funded."
            ),
        )

    if chop_ok and not blockers:
        return ReloadRegimeSnapshot(
            enabled=True,
            active=True,
            armed=True,
            phase="armed",
            headline="RELOAD ARMED — sell XRP in chop to fund RLUSD",
            detail=chop_reason,
            entry_allowed=True,
            reason="armed",
            signals=tuple(signals),
            blocks_accumulation=blocks_acc,
            rlusd_xrp_equiv=rlusd_xeq,
            deploy_floor_xrp_equiv=floor,
            shortfall_xrp_equiv=shortfall,
            skynet_nudge=(
                f"Post-run chop — place funding ask for ~{shortfall:.1f} XRP-equiv to floor {floor:.1f}. "
                + (
                    "Accumulation bids blocked until funded."
                    if blocks_acc
                    else "Residual RLUSD may bid while funding completes."
                )
            ),
        )

    if blockers and shortfall > 0:
        return ReloadRegimeSnapshot(
            enabled=True,
            active=True,
            armed=False,
            phase="blocked",
            headline="RELOAD BLOCKED",
            detail=" | ".join(blockers[:4]),
            entry_allowed=False,
            reason="blocked",
            signals=tuple(signals),
            blockers=tuple(blockers),
            blocks_accumulation=blocks_acc,
            rlusd_xrp_equiv=rlusd_xeq,
            deploy_floor_xrp_equiv=floor,
            shortfall_xrp_equiv=shortfall,
        )

    return ReloadRegimeSnapshot(
        enabled=True,
        active=False,
        armed=False,
        phase="off",
        headline="RELOAD IDLE",
        detail="No funding needed",
        entry_allowed=False,
        reason="idle",
        rlusd_xrp_equiv=rlusd_xeq,
        deploy_floor_xrp_equiv=floor,
        shortfall_xrp_equiv=shortfall,
        blocks_accumulation=False,
    )


def compute_reload_sell_size_xrp(
    config: BotConfig,
    *,
    shortfall_xrp_equiv: float,
    balances: "BalanceSnapshot",
    inventory: "InventorySnapshot",
) -> float:
    """Size funding sell to close shortfall to deploy floor (capped)."""
    if shortfall_xrp_equiv <= 0:
        return 0.0
    mid = balances.mid_rlusd_per_xrp
    if mid is None or mid <= 0:
        return 0.0
    max_xrp = float(getattr(config, "alpha_reload_max_sell_xrp", 0.0))
    desired = shortfall_xrp_equiv
    if max_xrp > 0:
        desired = min(desired, max_xrp)
    available = max(0.0, balances.xrp - config.xrp_reserve)
    desired = min(desired, available)
    return round(max(0.0, desired), 4)


def build_reload_context_block(snap: Dict[str, Any]) -> str:
    if not snap:
        return "=== RLUSD reload regime ===\n(not evaluated)"
    return "\n".join(
        [
            "=== RLUSD reload regime (fund dry powder in post-run CHOP — not into rip) ===",
            f"phase={snap.get('phase')} armed={snap.get('armed')} entry_allowed={snap.get('entry_allowed')}",
            f"headline={snap.get('headline')}",
            f"detail={snap.get('detail')}",
            f"rlusd_xrp_equiv={snap.get('rlusd_xrp_equiv')} floor={snap.get('deploy_floor_xrp_equiv')} "
            f"shortfall={snap.get('shortfall_xrp_equiv')}",
            f"blocks_accumulation={snap.get('blocks_accumulation')}",
            f"signals={snap.get('signals')}",
            f"skynet_nudge={snap.get('skynet_nudge') or ''}",
        ]
    )
