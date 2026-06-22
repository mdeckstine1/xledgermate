"""Alpha application — status and trading cycles with full Phase 5 integration."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from alpha.config_validator import AlphaConfigValidation, load_validated_config
from alpha.decision.structure import MarketStructureSnapshot, analyze_structure, load_mid_history
from alpha.decision.technical_analysis import TechnicalAnalysis, TechnicalAnalysisSnapshot
from alpha.operator.activity import ActivityLog
from alpha.operator.controls import OperatorControlStore
from alpha.operator.runtime import OperatorRuntimeStore, apply_overrides, derive_posture
from alpha.decision.engine import DecisionEngine, DecisionResult
from alpha.dry_run import DryRunGuard
from alpha.inventory.manager import InventoryManager
from alpha.ledger.factory import build_ledger
from alpha.ledger.interface import LedgerInterface
from alpha.orders.manager import OrderManager, OrderManagerState
from alpha.reporting.service import ReportingService, bracket_summary_from_store
from alpha.risk.engine import RiskEngine
from alpha.runtime.executor import EntryExecutionResult, EntryExecutor
from alpha.types import BalanceSnapshot, CycleReportContext, OperatorSnapshot, OrderBookSnapshot, utc_now
from alpha.version import ALPHA_VERSION
from config.settings import BotConfig

logger = logging.getLogger(__name__)


@dataclass
class AlphaCycleResult:
    snapshot: OperatorSnapshot
    decision: DecisionResult
    orders: OrderManagerState
    execution: Optional[EntryExecutionResult]
    config_validation: AlphaConfigValidation
    report_text: str = ""


class AlphaApplication:
    """Wires config, ledger, inventory, risk, decision, orders, reporting, and execution."""

    def __init__(
        self,
        config: BotConfig,
        *,
        ledger: Optional[LedgerInterface] = None,
        state_dir: Path | None = None,
    ) -> None:
        self.config = config
        self._state_dir = state_dir or Path("logs")
        self._dry_run_guard = DryRunGuard(
            dry_run=config.dry_run,
            network="testnet" if config.testnet else "mainnet",
        )
        self._ledger = ledger or build_ledger(config, dry_run_guard=self._dry_run_guard)
        self._inventory = InventoryManager(config)
        self._risk = RiskEngine(config, state_dir=self._state_dir)
        self._reporting = ReportingService(config)
        self._controls = OperatorControlStore(path=self._state_dir / "alpha_controls.json")
        self._runtime = OperatorRuntimeStore(
            overrides_path=self._state_dir / "alpha_overrides.json",
            commands_path=self._state_dir / "alpha_commands.json",
        )
        self._activity = ActivityLog(path=self._state_dir / "alpha_activity.jsonl")
        self._orders = OrderManager(
            self._ledger,
            self._dry_run_guard,
            config,
            risk_engine=self._risk,
            state_dir=self._state_dir,
        )
        self._decision = DecisionEngine(config, inventory=self._inventory, risk=self._risk)
        self._executor = EntryExecutor(
            self._ledger,
            self._orders,
            self._dry_run_guard,
            config,
            risk=self._risk,
        )
        self._kill_was_active = False
        self._last_structure: Optional[MarketStructureSnapshot] = None
        self._last_ta: Optional[TechnicalAnalysisSnapshot] = None
        self._last_book: Optional[OrderBookSnapshot] = None
        self._ta = TechnicalAnalysis(config)

    @property
    def controls(self) -> OperatorControlStore:
        return self._controls

    @property
    def activity(self) -> ActivityLog:
        return self._activity

    @property
    def runtime(self) -> OperatorRuntimeStore:
        return self._runtime

    def _refresh_config(self, config: BotConfig) -> None:
        """Push effective config into subcomponents."""
        self.config = config
        network = "testnet" if config.testnet else "mainnet"
        if self._dry_run_guard.dry_run != config.dry_run or self._dry_run_guard.network != network:
            self._dry_run_guard = DryRunGuard(dry_run=config.dry_run, network=network)
        self._inventory._config = config  # noqa: SLF001
        self._risk._config = config  # noqa: SLF001
        self._reporting._config = config  # noqa: SLF001
        self._orders._config = config  # noqa: SLF001
        self._decision._config = config  # noqa: SLF001
        self._executor._config = config  # noqa: SLF001
        self._ta = TechnicalAnalysis(config)

    async def _sync_operator_runtime(self) -> None:
        """Reload overrides, apply effective config, process queued operator commands."""
        base = BotConfig.load()
        overrides = self._runtime.load_overrides()
        effective = apply_overrides(base, overrides)
        self._refresh_config(effective)

        for cmd in self._runtime.drain_commands():
            cmd_type = str(cmd.get("type", ""))
            if cmd_type == "config_reload":
                reloaded = BotConfig.load()
                effective = apply_overrides(reloaded, self._runtime.load_overrides())
                self._refresh_config(effective)
                self._activity.append("config_reload", dry_run=effective.dry_run)
                logger.info("alpha_config_reloaded | dry_run=%s", effective.dry_run)
            elif cmd_type == "cancel_all":
                cancelled = await self._orders.cancel_all()
                self._activity.append("cancel_all", executed=cancelled, dry_run=self.config.dry_run)
                logger.info("alpha_cancel_all_processed | executed=%s", cancelled)
            elif cmd_type == "bracket_adjust":
                ok = await self._orders.adjust_bracket_leg(
                    str(cmd.get("bracket_id", "")),
                    str(cmd.get("leg", "")),
                    float(cmd.get("new_price", 0)),
                )
                self._activity.append(
                    "bracket_adjust",
                    bracket_id=cmd.get("bracket_id"),
                    leg=cmd.get("leg"),
                    price=cmd.get("new_price"),
                    executed=ok,
                    dry_run=self.config.dry_run,
                )

    @classmethod
    def from_config_file(cls, *, state_dir: Path | None = None) -> tuple[AlphaApplication, AlphaConfigValidation]:
        config, validation = load_validated_config()
        return cls(config, state_dir=state_dir), validation

    async def _gather_cycle_context(self) -> tuple[
        OperatorSnapshot,
        AlphaConfigValidation,
        DecisionResult,
        OrderManagerState,
    ]:
        _, validation = load_validated_config()
        if not validation.ok:
            logger.error("config_validation_failed | %s", validation.summary())

        try:
            await self._ledger.connect()
            account = await self._ledger.get_account_snapshot()
        except Exception as exc:
            logger.error("ledger_snapshot_failed | error=%s", exc, exc_info=True)
            raise

        balances = BalanceSnapshot(
            xrp=account.xrp,
            rlusd=account.rlusd,
            mid_rlusd_per_xrp=account.mid_rlusd_per_xrp,
            portfolio_xrp_equiv=account.portfolio_xrp_equiv,
        )
        trust = account.trust_line
        book = account.book
        self._last_book = book

        try:
            liquidity = await self._ledger.get_liquidity_depth(self.config.alpha_max_slippage_pct)
        except Exception as exc:
            logger.warning("liquidity_depth_degraded | error=%s", exc)
            liquidity = None

        inventory = self._inventory.snapshot(balances)
        risk = self._risk.evaluate(balances=balances, trust_line=trust)

        structure = None
        if book and book.mid and book.mid > 0:
            structure = analyze_structure(
                book.mid,
                breakout_pct=self.config.alpha_breakout_pct,
                lookback=self.config.alpha_structure_lookback,
                breakout_tf=self.config.breakout_confirmation_tf,
                cycle_seconds=self.config.alpha_cycle_interval_seconds,
                path=self._state_dir / "alpha_mid_history.json",
            )
            self._last_structure = structure
            self._orders.set_structure(structure)

        ta_snapshot: Optional[TechnicalAnalysisSnapshot] = None
        if book and book.mid and book.mid > 0:
            mids = load_mid_history(self._state_dir / "alpha_mid_history.json")
            ta_snapshot = self._ta.analyze(mids, mid=book.mid)
            self._last_ta = ta_snapshot
            self._orders.set_ta(ta_snapshot)

        if risk.kill_switch_active and not self._kill_was_active:
            self._reporting.send_kill_alert(risk.kill_switch_reason or "Kill switch activated")
        self._kill_was_active = risk.kill_switch_active

        orders = await self._orders.sync_brackets(risk=risk)

        snap = OperatorSnapshot(
            generated_utc=utc_now(),
            alpha_version=ALPHA_VERSION,
            network="testnet" if self.config.testnet else "mainnet",
            dry_run=self.config.dry_run,
            trading_enabled=self.config.trading_enabled,
            account_address=self._ledger.account_address,
            balances=balances,
            trust_line=trust,
            inventory=inventory,
            risk=risk,
        )
        decision = self._decision.evaluate(
            inventory=inventory,
            risk=risk,
            operator=snap,
            book=book,
            liquidity=liquidity,
            pending_buy_count=self._orders.pending_buy_count(),
            balances=balances,
            ta=ta_snapshot,
        )
        return snap, validation, decision, orders

    def _build_report(
        self,
        snap: OperatorSnapshot,
        decision: DecisionResult,
        orders: OrderManagerState,
        execution: Optional[EntryExecutionResult],
    ) -> CycleReportContext:
        exec_summary = ""
        if execution is not None:
            if execution.executed:
                exec_summary = f"executed {execution.action} seq={execution.buy_sequence}"
            elif execution.dry_run:
                exec_summary = f"dry_run would {execution.action}: {execution.message}"
            else:
                exec_summary = execution.message

        structure_summary = self._last_structure.summary if self._last_structure else ""

        return CycleReportContext(
            snapshot=snap,
            bracket_summary=bracket_summary_from_store(self._orders.store),
            decision_action=decision.action.value,
            decision_reason=decision.reason,
            execution_summary=exec_summary,
            open_offers_count=len(orders.open_offers),
            structure_summary=structure_summary,
            operator_paused=self._controls.is_paused(),
        )

    def _publish_hud_state(
        self,
        snap: OperatorSnapshot,
        decision: DecisionResult,
        orders: OrderManagerState,
        execution: Optional[EntryExecutionResult],
        report_text: str,
    ) -> None:
        from alpha.hud.state_export import publish_cycle_to_hud
        from alpha.reporting.service import bracket_summary_from_store

        publish_cycle_to_hud(
            snapshot=snap,
            decision=decision,
            execution=execution,
            recent_events=orders.recent_events,
            path=self._state_dir / "alpha_runtime_state.json",
            book=self._last_book,
            structure=self._last_structure,
            ta=self._last_ta,
            bracket_summary=bracket_summary_from_store(self._orders.store),
            brackets=self._orders.store.all_records(),
            open_offers=orders.open_offers,
            activity_log=self._activity,
            controls=self._controls.load(),
            report_text=report_text,
            operator_overrides=self._runtime.load_overrides(),
            config_effective=self.config,
        )

    async def run_status_cycle(self, *, telegram: bool = True) -> AlphaCycleResult:
        """Read-only cycle: no entry execution."""
        await self._sync_operator_runtime()
        self._dry_run_guard.log_mode_banner()
        self._reporting.send_startup(
            dry_run=self.config.dry_run,
            network="testnet" if self.config.testnet else "mainnet",
        )
        snap, validation, decision, orders = await self._gather_cycle_context()
        ctx = self._build_report(snap, decision, orders, None)
        report_text = self._reporting.publish_cycle(ctx, to_telegram=telegram)
        self._publish_hud_state(snap, decision, orders, None, report_text)
        return AlphaCycleResult(
            snapshot=snap,
            decision=decision,
            orders=orders,
            execution=None,
            config_validation=validation,
            report_text=report_text,
        )

    async def run_trading_cycle(self, *, telegram: bool = False) -> AlphaCycleResult:
        """Full cycle: sync brackets, evaluate, execute entry if signaled."""
        await self._sync_operator_runtime()
        self._dry_run_guard.log_mode_banner()
        snap, validation, decision, orders = await self._gather_cycle_context()

        execution: Optional[EntryExecutionResult] = None
        paused = self._controls.is_paused()
        if paused:
            logger.info("trading_cycle_skipped | operator_pause_active")
            self._activity.append("cycle_skipped", reason="operator_pause")
        elif snap.risk.trading_allowed:
            execution = await self._executor.execute(decision, risk=snap.risk)
        else:
            logger.info("trading_cycle_skipped | risk_trading_not_allowed")

        if execution and (execution.executed or execution.dry_run):
            logger.info(
                "trading_cycle_execution | action=%s | executed=%s | dry_run=%s | msg=%s",
                execution.action,
                execution.executed,
                execution.dry_run,
                execution.message,
            )
            self._activity.append(
                "execution",
                action=execution.action,
                executed=execution.executed,
                dry_run=execution.dry_run,
                message=execution.message,
            )

        self._activity.append(
            "cycle",
            decision=decision.action.value,
            reason=decision.reason,
            dry_run=self.config.dry_run,
            kill=snap.risk.kill_switch_active,
        )

        ctx = self._build_report(snap, decision, orders, execution)
        report_text = self._reporting.publish_cycle(ctx, to_telegram=telegram)
        self._publish_hud_state(snap, decision, orders, execution, report_text)
        return AlphaCycleResult(
            snapshot=snap,
            decision=decision,
            orders=orders,
            execution=execution,
            config_validation=validation,
            report_text=report_text,
        )

    async def run_trading_loop(
        self,
        *,
        max_cycles: Optional[int] = None,
        telegram_each_cycle: bool = False,
    ) -> None:
        """Run trading cycles until interrupted or max_cycles reached."""
        interval = max(5, int(self.config.alpha_cycle_interval_seconds))
        cycle = 0
        self._reporting.send_startup(
            dry_run=self.config.dry_run,
            network="testnet" if self.config.testnet else "mainnet",
        )
        logger.info(
            "alpha_trading_loop_start | interval=%ds | dry_run=%s | max_cycles=%s",
            interval,
            self.config.dry_run,
            max_cycles,
        )
        try:
            while max_cycles is None or cycle < max_cycles:
                cycle += 1
                logger.info(
                    "alpha_trading_loop_cycle | n=%d | dry_run=%s | interval=%ds",
                    cycle,
                    self.config.dry_run,
                    interval,
                )
                try:
                    await self.run_trading_cycle(telegram=telegram_each_cycle)
                except Exception as exc:
                    logger.error("trading_cycle_error | cycle=%d | error=%s", cycle, exc, exc_info=True)
                if max_cycles is not None and cycle >= max_cycles:
                    break
                await asyncio.sleep(interval)
        finally:
            await self.close()
            logger.info("alpha_trading_loop_stop | cycles=%d", cycle)

    async def close(self) -> None:
        try:
            await self._ledger.close()
        except Exception as exc:
            logger.warning("ledger_close_error | %s", exc)
