"""Rich Telegram and console reporting for Trading Bot Alpha."""

from __future__ import annotations

import logging

from alpha.orders.types import BracketLifecycleState, BracketMode
from alpha.types import BracketStatusSummary, CycleReportContext, OperatorSnapshot
from config.settings import BotConfig
from monitoring.telegram_alerts import TelegramAlerts

logger = logging.getLogger(__name__)


def bracket_summary_from_store(store: object) -> BracketStatusSummary:
    """Build bracket posture summary from BracketStateStore."""
    from alpha.orders.state import BracketStateStore

    if not isinstance(store, BracketStateStore):
        return BracketStatusSummary()

    pending = 0
    fixed = 0
    sl_trailing = 0
    breakout_trailing = 0
    labels: list[str] = []

    for record in store.all_records():
        state = record.state
        if state in (
            BracketLifecycleState.PENDING_BUY,
            BracketLifecycleState.BRACKET_ACTIVE,
            BracketLifecycleState.TRAILING_PLACEHOLDER,
        ):
            if record.breakout_confirmed or record.mode == BracketMode.BREAKOUT_TRAILING:
                mode_label = "breakout_trail"
            elif record.breakeven_passed:
                mode_label = "sl_trail"
            else:
                mode_label = "fixed"
            labels.append(f"{record.bracket_id[:8]}:{state.value}:{mode_label}")

        if state == BracketLifecycleState.PENDING_BUY:
            pending += 1
        elif state == BracketLifecycleState.BRACKET_ACTIVE:
            if record.breakout_confirmed or record.mode == BracketMode.BREAKOUT_TRAILING:
                breakout_trailing += 1
            elif record.breakeven_passed:
                sl_trailing += 1
            else:
                fixed += 1
        elif state == BracketLifecycleState.TRAILING_PLACEHOLDER:
            breakout_trailing += 1

    return BracketStatusSummary(
        total=len(store.all_records()),
        pending_buys=pending,
        active_fixed=fixed,
        active_sl_trailing=sl_trailing,
        active_breakout_trailing=breakout_trailing,
        active_trailing=sl_trailing + breakout_trailing,
        labels=tuple(labels[:8]),
    )


def format_operator_report(snap: OperatorSnapshot) -> str:
    """Legacy short report (still used for minimal status)."""
    return format_rich_report(
        CycleReportContext(
            snapshot=snap,
            bracket_summary=BracketStatusSummary(),
        )
    )


def format_rich_report(ctx: CycleReportContext) -> str:
    snap = ctx.snapshot
    mode = "DRY-RUN" if snap.dry_run else "LIVE"
    net = snap.network
    mid = snap.balances.mid_rlusd_per_xrp
    mid_s = f"{mid:.6f}" if mid is not None else "n/a"
    inv = snap.inventory
    risk = snap.risk
    brackets = ctx.bracket_summary

    lines = [
        f"xLedgerMate Alpha v{snap.alpha_version}",
        f"{'—' * 32}",
        f"Mode: {mode} | Network: {net}",
        f"Trading: {'on' if snap.trading_enabled else 'off'} | "
        f"Risk trading: {'allowed' if risk.trading_allowed else 'BLOCKED'}",
        f"Account: {snap.account_address[:10]}…{snap.account_address[-6:]}",
        "",
        "Portfolio",
        f"  XRP: {snap.balances.xrp:.4f} ({inv.xrp_allocation_pct:.1f}%)",
        f"  RLUSD: {snap.balances.rlusd:.4f} ({inv.rlusd_allocation_pct:.1f}%)",
        f"  Mid: {mid_s} RLUSD/XRP",
        f"  Total (XRP equiv): {snap.balances.portfolio_xrp_equiv:.4f}",
        f"  Session P&L: {risk.session_pnl_xrp:+.4f} XRP",
        "",
        "Inventory posture",
        f"  Target XRP: {inv.target_xrp_ratio:.0%} | Actual: {inv.xrp_ratio:.0%}",
        f"  Deviation: {inv.deviation:+.3f} ({inv.label})",
        f"  Buy imbalance block: {inv.buy_blocked_imbalance} | "
        f"Sell imbalance block: {inv.sell_blocked_imbalance}",
        "",
        "Open brackets",
        f"  Pending buys: {brackets.pending_buys} | Fixed TP/SL: {brackets.active_fixed} | "
        f"SL trail: {brackets.active_sl_trailing} | Breakout trail: {brackets.active_breakout_trailing}",
        f"  Open offers (ledger): {ctx.open_offers_count}",
    ]
    if brackets.labels:
        lines.append("  Active: " + ", ".join(brackets.labels[:4]))

    lines.extend(
        [
            "",
            "Risk & alerts",
            f"  Kill switch: {'ACTIVE' if risk.kill_switch_active else 'off'}",
            f"  Daily drawdown: {risk.drawdown_pct:.2f}% / {risk.max_drawdown_pct:.2f}%",
            f"  Preflight: {risk.preflight_summary}",
        ]
    )
    if risk.kill_switch_active and risk.kill_switch_reason:
        lines.append(f"  Kill reason: {risk.kill_switch_reason}")
    if risk.alerts:
        lines.append("  Alerts:")
        for alert in risk.alerts[:5]:
            lines.append(f"    • {alert}")

    if ctx.structure_summary:
        lines.extend(["", "Market structure", f"  {ctx.structure_summary}"])
    if ctx.operator_paused:
        lines.append("  Operator pause: ACTIVE")

    if ctx.decision_action != "hold" or ctx.decision_reason:
        lines.extend(
            [
                "",
                "Last decision",
                f"  Action: {ctx.decision_action}",
                f"  Reason: {ctx.decision_reason}",
            ]
        )
    if ctx.execution_summary:
        lines.append(f"  Execution: {ctx.execution_summary}")

    return "\n".join(lines)


class ReportingService:
    """Wraps TelegramAlerts; never logs tokens."""

    def __init__(self, config: BotConfig) -> None:
        self._config = config
        self._telegram = TelegramAlerts(
            token=config.telegram_token,
            chat_id=config.telegram_chat_id,
            enabled=config.telegram_enabled,
        )

    @property
    def telegram_configured(self) -> bool:
        return self._telegram.is_configured()

    def publish_cycle(self, ctx: CycleReportContext, *, to_telegram: bool = True) -> str:
        text = format_rich_report(ctx)
        logger.info("alpha_cycle_report\n%s", text)
        if to_telegram and self._telegram.is_configured():
            if not self._telegram.send_message(text):
                logger.warning("Telegram cycle report failed")
        elif to_telegram and self._config.telegram_enabled:
            logger.warning("Telegram enabled but not fully configured")
        return text

    def publish_status(self, snap: OperatorSnapshot, *, to_telegram: bool = True) -> str:
        return self.publish_cycle(
            CycleReportContext(snapshot=snap, bracket_summary=BracketStatusSummary()),
            to_telegram=to_telegram,
        )

    def send_startup(self, *, dry_run: bool, network: str) -> None:
        mode = "DRY-RUN" if dry_run else "LIVE"
        msg = f"xLedgerMate Alpha started | {mode} | {network} | v1.0.0"
        logger.info(msg)
        if self._telegram.is_configured():
            self._telegram.send_message(msg)

    def send_kill_alert(self, reason: str) -> None:
        msg = f"xLedgerMate Alpha KILL SWITCH\n{reason}"
        logger.critical(msg)
        if self._config.telegram_kill_alerts_enabled and self._telegram.is_configured():
            self._telegram.send_message(msg)
