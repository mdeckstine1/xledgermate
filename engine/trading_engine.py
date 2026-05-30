from __future__ import annotations
import asyncio
import json
import logging
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from config.settings import BotConfig
from connectors import XRPLConnector, XRPLNetworkConfig
from connectors.xrpl_connector import is_plausible_rlusd_per_xrp
from core.market_conditions import (
    assess_market_conditions,
    compute_book_spread_pct,
    is_more_defensive_than,
    profile_for_auto_switch,
)
from utils.profile_recommendation import normalize_profile_recommendation
from core.runtime_state import QuoteIntent, RuntimeState, RuntimeStateStore
from engine.order_manager import OrderManager
from engine.order_sync import plan_order_sync
from monitoring.balance_logger import BalanceLogger
from monitoring.csv_logger import CSVLogger
from monitoring.fill_detection import detect_fill_from_balance_delta
from monitoring.fill_economics import estimate_spread_capture_xrp
from monitoring.ledger_fills import LedgerFill, LedgerFillScanner
from monitoring.telegram_alerts import TelegramAlerts
from risk.drawdown import (
    DrawdownMonitor,
    portfolio_value_xrp,
    session_pnl_balance_delta_xrp,
    session_pnl_mtm_xrp,
)
from risk.kill_switch import KillSwitch
from core import BotPerception, DecisionLog, VERSION, get_profile
from core.perception import BUILT_IN_PROFILES
from core.profile_execution import ProfileExecution, resolve_profile_execution
from utils.auto_profile_state import (
    clear_auto_profile_pending,
    load_auto_profile_state,
    minutes_since_auto_switch,
    save_auto_profile_state,
)
from utils.profile_request import consume_profile_request
from strategy.avellaneda_strategy import AvellanedaStrategy
from strategy.quote_decision import (
    apply_spread_adjustments,
    assess_inventory,
    build_quote_adjustments,
    compute_mid_momentum_pct,
)
from strategy.fill_quality import FillQualityTracker
from strategy.inventory_balance import assess_rebalance_need
from strategy.market_microstructure import resolve_effective_min_edge_pct
from utils.preflight import evaluate_preflight
from utils.quote_validation import validate_quotes_against_book
logger = logging.getLogger(__name__)
ENGINE_STOP_FILE = Path("logs/engine.stop")


class TradingEngine:
    """Continuous market loop: perception updates, quote planning, optional order refresh."""
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.connector: Optional[XRPLConnector] = None
        self.strategy = AvellanedaStrategy(config)
        self.order_manager = OrderManager(config)
        self.drawdown_monitor = DrawdownMonitor(max_drawdown_percent=config.max_daily_drawdown_percent)
        self.kill_switch = KillSwitch()
        self.decision_log = DecisionLog(max_entries=150)
        self.state_store = RuntimeStateStore()
        self.alerts = TelegramAlerts(
            token=config.telegram_token,
            chat_id=config.telegram_chat_id,
            enabled=config.telegram_enabled,
        )
        self.csv_logger = CSVLogger()
        self.balance_logger = BalanceLogger()
        self._running = False
        self._cycle_count = 0
        self._session_baseline_xrp: Optional[float] = None
        self._session_baseline_rlusd: Optional[float] = None
        self._session_baseline_mid: Optional[float] = None
        self._session_baseline_portfolio_xrp: Optional[float] = None
        self._decision_log_path = Path("logs/decisions.jsonl")
        self._decision_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._price_history_max = 180
        self._price_history = self._restore_price_history()
        self._last_preflight: Optional[Any] = None
        self._last_spread_validation: Optional[Any] = None
        self._last_cycle_balances: Optional[tuple[float, float]] = None
        self._prev_kill_active = False
        self._fill_quality = FillQualityTracker()
        self._ledger_fill_scanner = LedgerFillScanner()
        self._active_profile_last_cycle: Optional[str] = None
        self._last_market_condition: Optional[str] = None
        self._last_liquidity_level: Optional[str] = None
        self._last_quote_mid: Optional[float] = None
        self._last_full_refresh_mid: Optional[float] = None
        self._consecutive_spread_failures: int = 0
        self._rpc_failure_streak: int = 0
        self._poll_counter: int = 0
        self._session_offers_cancelled: int = 0
        self._session_offers_kept: int = 0
        self._session_fills: int = 0
        self._recent_fill_keys: set = set()

    def _restore_price_history(self) -> List[dict]:
        """Continue chart history across engine restarts (from runtime_state.json)."""
        try:
            prior = self.state_store.load()
            if prior and prior.price_history:
                return list(prior.price_history)[-self._price_history_max :]
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            logger.debug("Could not restore price history: %s", exc)
        return []

    async def run(self) -> None:
        self._running = True
        logger.info(
            "Trading engine started | network=%s dry_run=%s trading_enabled=%s kill=%s",
            self.config.network_name(),
            self.config.dry_run,
            self.config.trading_enabled,
            self.kill_switch.is_active(),
        )
        self.csv_logger.log_major(
            network=self.config.network_name(),
            notes=(
                f"Engine started | dry_run={self.config.dry_run} "
                f"trading_enabled={self.config.trading_enabled}"
            ),
        )
        while self._running:
            if ENGINE_STOP_FILE.exists():
                ENGINE_STOP_FILE.unlink(missing_ok=True)
                logger.info("Stop requested via GUI — shutting down engine loop.")
                break
            config = BotConfig.load()
            self.config = config
            profile = get_profile(config.active_profile)
            exec_cfg = resolve_profile_execution(profile, config)
            tiered = bool(getattr(config, "tiered_refresh_enabled", True))
            if tiered:
                self._poll_counter += 1
                full_refresh = self._poll_counter >= exec_cfg.full_refresh_every_n_polls
                if full_refresh:
                    self._poll_counter = 0
            else:
                full_refresh = True
            try:
                await self._run_cycle(full_refresh=full_refresh, exec_cfg=exec_cfg)
                self._rpc_failure_streak = 0
            except Exception as exc:
                self._rpc_failure_streak += 1
                logger.exception("Engine cycle failed: %s", exc)
                self._persist_error(str(exc))
                if self.connector and not config.dry_run:
                    await self._maybe_kill_on_rpc_failures(config, self.connector)
            if ENGINE_STOP_FILE.exists():
                ENGINE_STOP_FILE.unlink(missing_ok=True)
                logger.info("Stop requested via GUI — shutting down engine loop.")
                break
            sleep_sec = (
                exec_cfg.book_poll_interval_seconds
                if tiered
                else max(30, int(config.order_refresh_time_seconds))
            )
            await asyncio.sleep(sleep_sec)
    def stop(self) -> None:
        self._running = False
    async def cancel_all_offers(self) -> int:
        """Cancel every open offer on the ledger (used by CLI / emergency stop)."""
        config = BotConfig.load()
        if not config.bot_account_address.strip() or not (config.bot_secret_key or "").strip():
            raise ValueError("Bot account address and secret required to cancel offers.")
        connector = XRPLConnector(
            account_address=config.bot_account_address.strip(),
            secret=config.bot_secret_key,
            rlusd_issuer=config.resolved_rlusd_issuer(),
            rlusd_currency=config.resolved_rlusd_currency_code(),
            network=XRPLNetworkConfig(json_rpc_url=config.resolved_rpc_url()),
        )
        return await connector.cancel_all_offers()
    async def _run_cycle(
        self,
        *,
        full_refresh: bool = True,
        exec_cfg: Optional[ProfileExecution] = None,
    ) -> None:
        config = BotConfig.load()
        self.config = config
        self.order_manager.config = config
        self.alerts = TelegramAlerts(
            token=config.telegram_token,
            chat_id=config.telegram_chat_id,
            enabled=config.telegram_enabled,
        )
        requested = consume_profile_request(known_profiles=set(BUILT_IN_PROFILES.keys()))
        if requested and requested != config.active_profile:
            old = config.active_profile
            config.active_profile = requested
            config.save()
            self.config = config
            self.order_manager.config = config
            msg = f"Operator profile {old} → {requested} (no engine restart)"
            logger.info(msg)
            self.decision_log.add("profile", msg)
        prev = self._active_profile_last_cycle
        if prev is not None and prev != config.active_profile:
            msg = f"Active profile {prev} → {config.active_profile} (from config)"
            logger.info(msg)
            self.decision_log.add("profile", msg)
        self._active_profile_last_cycle = config.active_profile

        profile = get_profile(config.active_profile)
        if exec_cfg is None:
            exec_cfg = resolve_profile_execution(profile, config)
        self._fill_quality.set_toxic_threshold_pct(exec_cfg.markout_toxic_threshold_pct)
        perception = BotPerception(active_profile=profile)
        if not config.bot_account_address.strip():
            msg = (
                "bot_account_address is required. "
                "Set it in the GUI sidebar (Bot Account) and click Save Config."
            )
            self.decision_log.add("setup", msg)
            self._persist_error(msg)
            logger.warning(msg)
            return
        connector = XRPLConnector(
            account_address=config.bot_account_address.strip(),
            secret=config.bot_secret_key or None,
            rlusd_issuer=config.resolved_rlusd_issuer(),
            rlusd_currency=config.resolved_rlusd_currency_code(),
            network=XRPLNetworkConfig(json_rpc_url=config.resolved_rpc_url()),
        )
        self.connector = connector
        preflight = None
        quote_plan = None
        spread_validation = None
        balance_xrp = 0.0
        rlusd_balance = 0.0
        mid_price: Optional[float] = None
        best_bid: Optional[float] = None
        best_ask: Optional[float] = None
        open_offers: List[Any] = []
        placed_count = 0
        portfolio_value = 0.0
        market_assessment = None
        quote_adjustments = None
        mid_momentum = 0.0
        book_spread_pct = 0.0
        rebalance = None
        fill_quality = None
        try:
            balance_xrp = await connector.get_xrp_balance()
            trust = await connector.get_rlusd_trust_line()
            rlusd_balance = trust.balance
            order_book = await connector.fetch_xrp_rlusd_order_book()
            liquidity = connector.compute_liquidity_metrics(order_book)
            best_bid, best_ask = connector.compute_best_prices(order_book)
            mid_price = connector.compute_mid_price(order_book)
            if mid_price is not None and not is_plausible_rlusd_per_xrp(mid_price):
                self.decision_log.add(
                    "quotes",
                    (
                        f"Skipped quotes: invalid mid={mid_price:.6f} "
                        "(looks like raw XRPL quality, not RLUSD/XRP)."
                    ),
                )
                mid_price = None
            portfolio_value = self.drawdown_monitor.update_portfolio(
                balance_xrp, rlusd_balance, mid_price or 0.0
            )
            self.kill_switch.reload()
            if getattr(self, "_prev_kill_active", False) and not self.kill_switch.is_active():
                self.drawdown_monitor.reset_baseline(portfolio_value)
                self.decision_log.add("profile", "Kill switch cleared — drawdown baseline reset.")
            self._prev_kill_active = self.kill_switch.is_active()
            if not config.dry_run:
                await self._scan_ledger_fills(
                    config=config,
                    connector=connector,
                    mid_price=mid_price,
                )
                self._detect_and_log_fills(
                    config=config,
                    balance_xrp=balance_xrp,
                    rlusd_balance=rlusd_balance,
                    mid_price=mid_price,
                )
            drawdown_pct = self.drawdown_monitor.get_drawdown_percent()
            if self.drawdown_monitor.is_kill_switch_triggered() and not self.kill_switch.is_active():
                await self._activate_kill_switch(
                    connector,
                    config,
                    f"Daily portfolio drawdown {drawdown_pct:.2f}%",
                )
            preflight = evaluate_preflight(
                config=config,
                xrp_balance=balance_xrp,
                rlusd_balance=rlusd_balance,
                trust_line_limit=trust.limit if trust.exists else None,
                has_trust_line=trust.exists,
                trust_line_no_ripple=trust.no_ripple if trust.exists else None,
                mid_price=mid_price,
                kill_switch_active=self.kill_switch.is_active(),
                xrp_reserve=config.xrp_reserve,
                min_order_xrp=config.min_order_size_xrp,
            )
            self._last_preflight = preflight
            self.decision_log.add("preflight", preflight.summary())
            for warning in preflight.warnings:
                self.decision_log.add("preflight", f"Warning: {warning}")
            for err in preflight.errors:
                self.decision_log.add("preflight", f"Error: {err}")
            if self.kill_switch.is_active():
                await self._cancel_offers_if_live(connector, config, "Kill switch active")
            volatility_pct = connector.update_and_estimate_volatility_pct(mid_price)
            book_spread_pct = compute_book_spread_pct(best_bid, best_ask)
            market_assessment = assess_market_conditions(
                volatility_pct=volatility_pct,
                liquidity_score=liquidity.liquidity_score,
                book_spread_pct=book_spread_pct,
                active_profile=config.active_profile,
                previous_condition=self._last_market_condition,
                previous_liquidity_level=self._last_liquidity_level,
            )
            self._last_market_condition = market_assessment.condition
            self._last_liquidity_level = market_assessment.liquidity_level
            self.decision_log.add("market", market_assessment.summary)

            if mid_price is not None:
                self._record_price_tick(mid=mid_price, bid=best_bid, ask=best_ask)
                self._fill_quality.note_mid(mid_price)

            if (
                not full_refresh
                and mid_price
                and self._last_full_refresh_mid
                and self._last_full_refresh_mid > 0
            ):
                move_pct = (
                    abs(mid_price - self._last_full_refresh_mid)
                    / self._last_full_refresh_mid
                    * 100.0
                )
                if move_pct >= exec_cfg.mid_requote_trigger_pct:
                    full_refresh = True
                    self.decision_log.add(
                        "execution",
                        f"Mid moved {move_pct:.2f}% — full quote refresh "
                        f"(profile {profile.name} trigger {exec_cfg.mid_requote_trigger_pct:.2f}%)",
                    )

            fill_quality = self._fill_quality.assess()

            if not full_refresh:
                self.decision_log.add(
                    "execution",
                    f"Book poll only ({exec_cfg.book_poll_interval_seconds}s cadence, "
                    f"profile {profile.name}) — queue preserved.",
                )
                open_offers = await connector.get_open_offers()
                if self._session_baseline_xrp is None:
                    self._session_baseline_xrp = balance_xrp
                    self._session_baseline_rlusd = rlusd_balance
                    self._session_baseline_mid = mid_price
                    self._session_baseline_portfolio_xrp = portfolio_value
                self._cycle_count += 1
                execution_summary = (
                    f"Book poll — toxic ratio {fill_quality.toxic_ratio:.0%}, "
                    f"cancel/fill {self._cancel_per_fill_ratio():.1f}"
                )
                self._persist_state(
                    perception=perception,
                    config=config,
                    balance_xrp=balance_xrp,
                    balance_rlusd=rlusd_balance,
                    open_offers=open_offers,
                    quote_intents=[],
                    placed_count=0,
                    execution_summary=execution_summary,
                    best_bid=best_bid,
                    best_ask=best_ask,
                    preflight=preflight,
                    portfolio_value=portfolio_value,
                    drawdown_pct=drawdown_pct,
                    market_assessment=market_assessment,
                    fill_quality=fill_quality,
                    exec_cfg=exec_cfg,
                    full_refresh=False,
                )
                self._last_cycle_balances = (balance_xrp, rlusd_balance)
                return

            if config.auto_profile_switching:
                from utils.operator_activity import minutes_since_save_config

                idle_min = minutes_since_save_config()
                inactive = idle_min >= config.auto_profile_inactivity_minutes
                proposed = profile_for_auto_switch(
                    market_assessment,
                    active_profile=config.active_profile,
                )
                if not inactive or not proposed:
                    if not proposed:
                        clear_auto_profile_pending()
                    elif not inactive and proposed:
                        self.decision_log.add(
                            "profile",
                            (
                                f"Auto-switch waiting: {idle_min:.0f}/"
                                f"{config.auto_profile_inactivity_minutes} min since Save Config "
                                f"(would switch to {proposed})"
                            ),
                        )
                else:
                    confirm_cycles = max(
                        1, int(getattr(config, "auto_profile_confirm_cycles", 3))
                    )
                    if proposed and not is_more_defensive_than(
                        config.active_profile, proposed
                    ):
                        confirm_cycles += 2
                        self.decision_log.add(
                            "profile",
                            f"Aggressive auto-switch to {proposed} needs "
                            f"{confirm_cycles} confirm cycles",
                        )
                    cooldown_min = max(
                        0, int(getattr(config, "auto_profile_switch_cooldown_minutes", 45))
                    )
                    ap_state = load_auto_profile_state()
                    if proposed == ap_state.pending_profile:
                        ap_state.pending_cycles += 1
                    else:
                        ap_state.pending_profile = proposed
                        ap_state.pending_cycles = 1
                    since_switch = minutes_since_auto_switch(ap_state)
                    if (
                        ap_state.pending_cycles >= confirm_cycles
                        and since_switch >= cooldown_min
                    ):
                        old = config.active_profile
                        config.active_profile = proposed
                        config.save()
                        profile = get_profile(proposed)
                        perception.active_profile = profile
                        ap_state.last_auto_switch_utc = datetime.now(
                            tz=timezone.utc
                        ).isoformat()
                        ap_state.pending_profile = None
                        ap_state.pending_cycles = 0
                        save_auto_profile_state(ap_state)
                        msg = (
                            f"Auto-switched profile {old} → {proposed} "
                            f"(operator idle, {market_assessment.condition_label} market, "
                            f"confirmed {confirm_cycles} cycles | "
                            f"vol={volatility_pct:.2f}% liq={liquidity.liquidity_score:.2f} "
                            f"book_spread={book_spread_pct:.3f}%)"
                        )
                        self.decision_log.add("profile", msg)
                        self.csv_logger.log_major(
                            network=config.network_name(),
                            notes=msg,
                            cycle=self._cycle_count + 1,
                        )
                    else:
                        save_auto_profile_state(ap_state)
                        if ap_state.pending_cycles == 1:
                            self.decision_log.add(
                                "profile",
                                (
                                    f"Auto-switch pending {proposed} "
                                    f"({ap_state.pending_cycles}/{confirm_cycles} cycles, "
                                    f"cooldown {since_switch:.0f}/{cooldown_min} min)"
                                ),
                            )

            spread_result = self.strategy.compute_spreads(
                volatility_pct=volatility_pct,
                liquidity_score=liquidity.liquidity_score,
                profile=profile,
            )
            mid_momentum = compute_mid_momentum_pct(self._price_history)
            inventory_state = assess_inventory(
                xrp_balance=balance_xrp,
                rlusd_balance=rlusd_balance,
                mid_price=mid_price or 0.0,
                target_xrp_ratio=config.inventory_target_xrp_ratio,
                skew_strength=profile.inventory_skew_strength,
            )
            l1_spread = spread_result.effective_spreads_pct.get(1, config.base_spread * 100.0)
            fill_quality = self._fill_quality.assess()
            effective_min_edge, edge_resolution = resolve_effective_min_edge_pct(
                profile=profile,
                edge_strictness=float(getattr(config, "edge_strictness", 1.0)),
                book_spread_pct=book_spread_pct,
                dynamic_enabled=bool(getattr(config, "dynamic_min_edge_enabled", False)),
            )
            quote_adjustments = build_quote_adjustments(
                profile=profile,
                assessment=market_assessment,
                inventory=inventory_state,
                mid_momentum_pct=mid_momentum,
                effective_spread_l1_pct=l1_spread,
                book_spread_pct=book_spread_pct,
                depth_imbalance=liquidity.depth_imbalance,
                min_edge_pct=effective_min_edge,
                book_pressure_sensitivity=float(
                    getattr(config, "book_pressure_sensitivity", 1.0)
                ),
                fill_quality=fill_quality,
                fund_with_xrp_only=config.fund_with_xrp_only,
                rlusd_balance=rlusd_balance,
                min_order_xrp=config.min_order_size_xrp,
                target_xrp_ratio=float(config.inventory_target_xrp_ratio),
                inventory_max_deviation=float(
                    getattr(config, "inventory_max_deviation", 0.12)
                ),
            )
            if fill_quality and not self.kill_switch.is_active():
                await self._maybe_kill_on_toxic_fills(
                    config, fill_quality, connector
                )
            spendable_xrp = max(0.0, balance_xrp - config.xrp_reserve)
            rebalance = assess_rebalance_need(
                xrp_balance=balance_xrp,
                rlusd_balance=rlusd_balance,
                mid_price=mid_price or 0.0,
                target_xrp_ratio=config.inventory_target_xrp_ratio,
                spendable_xrp=spendable_xrp,
                xrp_reserve=config.xrp_reserve,
                min_order_xrp=config.min_order_size_xrp,
                fund_with_xrp_only=config.fund_with_xrp_only,
            )
            self.decision_log.add("inventory", rebalance.summary)
            self.decision_log.add("edge", edge_resolution)
            adjusted_spreads = apply_spread_adjustments(
                spread_result.effective_spreads_pct,
                quote_adjustments,
            )
            self.decision_log.add("inventory", f"Inventory {inventory_state.label} (XRP ratio {inventory_state.xrp_ratio:.2f})")
            self.decision_log.add("decision", quote_adjustments.decision_summary or "baseline quoting")
            perception.update_market_state(
                mid_price=mid_price or 0.0,
                volatility_pct=volatility_pct,
                liquidity=liquidity,
                effective_spreads_pct=adjusted_spreads,
            )
            if preflight.ready and mid_price and not self.kill_switch.is_active():
                self.decision_log.add("spread", spread_result.reason)
                quote_plan = self.order_manager.build_quotes(
                    mid_price=mid_price,
                    spreads_pct=adjusted_spreads,
                    xrp_balance=balance_xrp,
                    rlusd_balance=rlusd_balance,
                    adjustments=quote_adjustments,
                    best_bid=best_bid,
                    best_ask=best_ask,
                )
                book_note = ""
                if best_bid is not None and best_ask is not None:
                    book_note = (
                        f" | book bid={best_bid:.6f} ask={best_ask:.6f} "
                        f"mid={mid_price:.6f} RLUSD/XRP"
                    )
                self.decision_log.add("quotes", quote_plan.reason + book_note)
            else:
                quote_plan = None
                if not preflight.ready:
                    self.decision_log.add("quotes", "Skipped — preflight not ready.")

            intents_for_check = quote_plan.intents if quote_plan else []
            spread_validation = validate_quotes_against_book(
                intents_for_check,
                mid_price=mid_price,
                best_bid=best_bid,
                best_ask=best_ask,
                max_half_spread_from_mid_pct=float(
                    getattr(config, "max_half_spread_from_mid_pct", 1.0)
                ),
                max_worse_than_touch_pct=float(
                    getattr(config, "max_quote_worse_than_touch_pct", 0.50)
                ),
                max_improve_touch_pct=float(
                    getattr(config, "max_quote_improve_touch_pct", 0.15)
                ),
                require_intents_when_trading=config.trading_enabled,
            )
            self._last_spread_validation = spread_validation
            self.decision_log.add("spread_check", spread_validation.summary)
            for check in spread_validation.checks[:4]:
                self.decision_log.add("spread_check", check)
            for err in spread_validation.errors:
                self.decision_log.add("spread_check", f"Error: {err}")
            for warn in spread_validation.warnings:
                self.decision_log.add("spread_check", f"Warning: {warn}")

            live_blocked_by_spread = (
                not config.dry_run
                and bool(getattr(config, "require_spread_validation_for_live", True))
                and not spread_validation.ok
            )
            if live_blocked_by_spread:
                self._consecutive_spread_failures += 1
                self.decision_log.add(
                    "execution",
                    "Live orders blocked — spread check failed (fix spreads or stay in dry-run).",
                )
                await self._maybe_kill_on_spread_failures(config, connector)
            else:
                self._consecutive_spread_failures = 0

            if (
                quote_plan
                and quote_plan.intents
                and config.trading_enabled
                and not self.kill_switch.is_active()
                and preflight.ready
                and not live_blocked_by_spread
            ):
                refresh_paused = (
                    fill_quality.recent_fills >= 3
                    and fill_quality.toxic_ratio >= exec_cfg.toxic_refresh_pause_ratio
                )
                if refresh_paused:
                    self.decision_log.add(
                        "execution",
                        f"Refresh paused — toxic ratio {fill_quality.toxic_ratio:.0%} "
                        f">= profile {profile.name} limit {exec_cfg.toxic_refresh_pause_ratio:.0%}",
                    )
                else:
                    self._last_quote_mid = mid_price
                    placed_count = await self._refresh_orders(
                        quote_plan.intents, exec_cfg=exec_cfg
                    )
                    self._last_full_refresh_mid = mid_price
            open_offers = await connector.get_open_offers()
            if self._session_baseline_xrp is None:
                self._session_baseline_xrp = balance_xrp
                self._session_baseline_rlusd = rlusd_balance
                self._session_baseline_mid = mid_price
                self._session_baseline_portfolio_xrp = portfolio_value
            execution_summary = self._execution_summary(config, placed_count)
            self._cycle_count += 1
            self.balance_logger.log_snapshot(
                cycle=self._cycle_count,
                network=config.network_name(),
                xrp_balance=balance_xrp,
                rlusd_balance=rlusd_balance,
                mid_rlusd_per_xrp=mid_price or 0.0,
                portfolio_xrp_equiv=portfolio_value,
                open_offers=len(open_offers),
                dry_run=config.dry_run,
            )
            self._append_decision_file(
                cycle=self._cycle_count,
                mid=mid_price,
                execution=execution_summary,
            )
            self._last_cycle_balances = (balance_xrp, rlusd_balance)
            self._persist_state(
                perception=perception,
                config=config,
                balance_xrp=balance_xrp,
                balance_rlusd=rlusd_balance,
                open_offers=open_offers,
                quote_intents=quote_plan.intents if quote_plan else [],
                placed_count=placed_count,
                execution_summary=execution_summary,
                best_bid=best_bid,
                best_ask=best_ask,
                preflight=preflight,
                portfolio_value=portfolio_value,
                drawdown_pct=drawdown_pct,
                market_assessment=market_assessment,
                quote_adjustments=quote_adjustments,
                book_spread_pct=book_spread_pct,
                mid_momentum=mid_momentum,
                spread_validation=spread_validation,
                rebalance=rebalance,
                fill_quality=fill_quality,
                effective_min_edge_pct=effective_min_edge,
                edge_resolution_summary=edge_resolution,
                dynamic_min_edge_enabled=bool(
                    getattr(config, "dynamic_min_edge_enabled", False)
                ),
                exec_cfg=exec_cfg,
                full_refresh=True,
            )
            spread_ok = spread_validation.ok if spread_validation else False
            logger.info(
                "Cycle complete | #%s profile=%s mid=%.4f RLUSD/XRP portfolio=%.4f XRP "
                "drawdown=%.2f%% intents=%s placed=%s preflight=%s spread_check=%s",
                self._cycle_count,
                profile.name,
                mid_price or 0.0,
                portfolio_value,
                drawdown_pct,
                len(quote_plan.intents) if quote_plan else 0,
                placed_count,
                "OK" if preflight and preflight.ready else "FAIL",
                "OK" if spread_ok else "FAIL",
            )
            if config.telegram_notify_each_cycle and self.alerts.is_configured():
                self.alerts.send_cycle_summary(
                    network=config.network_name(),
                    mid=mid_price or 0.0,
                    cycle=self._cycle_count,
                    dry_run=config.dry_run,
                    placed=placed_count,
                    preflight_ok=bool(preflight and preflight.ready),
                )
        except Exception as exc:
            logger.exception("Cycle failed: %s", exc)
            self._persist_error(str(exc))
        finally:
            self.connector = None
    async def _activate_kill_switch(
        self,
        connector: XRPLConnector,
        config: BotConfig,
        reason: str,
    ) -> None:
        if self.kill_switch.is_active():
            return
        self.kill_switch.activate(reason)
        self.csv_logger.log_major(
            network=config.network_name(),
            cycle=self._cycle_count,
            notes=f"Kill switch activated: {reason}",
        )
        self.alerts.send_kill_switch_alert(
            self.drawdown_monitor.get_drawdown_percent(),
            reason,
        )
        await self._cancel_offers_if_live(connector, config, reason)
    async def _cancel_offers_if_live(
        self,
        connector: XRPLConnector,
        config: BotConfig,
        reason: str,
    ) -> None:
        if config.dry_run or not (config.bot_secret_key or "").strip():
            return
        try:
            cancelled = await connector.cancel_all_offers()
            self.decision_log.add(
                "execution",
                f"Cancelled {cancelled} open offer(s) ({reason}).",
            )
        except Exception as exc:
            self.decision_log.add("execution", f"Cancel failed: {exc}")
            logger.exception("Failed to cancel offers: %s", exc)
    def _record_price_tick(
        self,
        *,
        mid: Optional[float],
        bid: Optional[float],
        ask: Optional[float],
    ) -> None:
        if mid is None or mid <= 0:
            return
        tick: Dict[str, Any] = {
            "ts_utc": datetime.now(tz=timezone.utc).isoformat(),
            "mid": mid,
            "bid": bid,
            "ask": ask,
        }
        self._price_history.append(tick)
        if len(self._price_history) > self._price_history_max:
            self._price_history = self._price_history[-self._price_history_max :]
    def _execution_summary(self, config: BotConfig, placed_count: int) -> str:
        if self.kill_switch.is_active():
            return f"Kill switch: {self.kill_switch.reason}"
        if config.dry_run:
            return "Dry-run: no orders submitted to the ledger."
        if not config.trading_enabled:
            return "Trading disabled in config."
        if placed_count:
            return f"Live: placed {placed_count} offer(s) on the ledger."
        return "Live: no offers placed this cycle."
    def _append_decision_file(
        self, *, cycle: int, mid: Optional[float], execution: str
    ) -> None:
        record = {
            "cycle": cycle,
            "mid_rlusd_per_xrp": mid,
            "execution": execution,
            "pid": os.getpid(),
            "events": [
                {
                    "ts_utc": e.ts_utc,
                    "category": e.category,
                    "message": e.message,
                }
                for e in self.decision_log.recent_newest_first(limit=6)
            ],
        }
        with self._decision_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    def _cancel_per_fill_ratio(self) -> float:
        if self._session_fills <= 0:
            return float(self._session_offers_cancelled)
        return self._session_offers_cancelled / self._session_fills

    async def _scan_ledger_fills(
        self,
        *,
        config: BotConfig,
        connector: XRPLConnector,
        mid_price: Optional[float],
    ) -> None:
        try:
            txs = await connector.fetch_account_transactions(limit=40)
        except Exception as exc:
            self.decision_log.add("fill", f"Ledger tx scan failed: {exc}")
            return
        fills = self._ledger_fill_scanner.scan_transactions(
            txs,
            account=config.bot_account_address.strip(),
            rlusd_currency=config.resolved_rlusd_currency_code(),
            rlusd_issuer=config.resolved_rlusd_issuer(),
        )
        for fill in fills:
            self._log_fill(
                config=config,
                side=fill.side,
                xrp_amount=fill.xrp_amount,
                rlusd_amount=fill.rlusd_amount,
                price=fill.price_rlusd_per_xrp,
                mid_price=mid_price,
                tx_hash=fill.tx_hash,
                fill_source=fill.source,
                balance_xrp=0.0,
                balance_rlusd=0.0,
            )

    def _log_fill(
        self,
        *,
        config: BotConfig,
        side: str,
        xrp_amount: float,
        rlusd_amount: float,
        price: float,
        mid_price: Optional[float],
        tx_hash: str = "",
        fill_source: str = "balance_delta",
        balance_xrp: float = 0.0,
        balance_rlusd: float = 0.0,
    ) -> None:
        cycle = self._cycle_count + 1
        dedupe_key = (cycle, side, round(xrp_amount, 2), round(rlusd_amount, 2), tx_hash[:8])
        if dedupe_key in self._recent_fill_keys:
            return
        self._recent_fill_keys.add(dedupe_key)
        if len(self._recent_fill_keys) > 40:
            self._recent_fill_keys = set(list(self._recent_fill_keys)[-20:])

        mid_at_quote = self._last_quote_mid or mid_price
        profit_xrp = estimate_spread_capture_xrp(
            side=side,
            xrp_amount=xrp_amount,
            fill_price_rlusd_per_xrp=price,
            mid_at_quote_rlusd_per_xrp=mid_at_quote,
        )
        self._fill_quality.note_fill(
            side=side,
            xrp_amount=xrp_amount,
            price=price,
            mid_at_fill=mid_price or price,
            tx_hash=tx_hash,
            fill_source=fill_source,
        )
        self._session_fills += 1
        src_note = "ledger" if fill_source == "ledger" else "balance delta"
        notes = (
            f"Fill via {src_note}; spread capture ~{profit_xrp:+.4f} XRP "
            f"@ mid {mid_at_quote or 'n/a'}"
        )
        if tx_hash:
            notes += f"; tx {tx_hash}"
        common = dict(
            network=config.network_name(),
            xrp_amount=xrp_amount,
            rlusd_amount=rlusd_amount,
            price_rlusd_per_xrp=price,
            profit_xrp_equiv=profit_xrp,
            tx_hash=tx_hash,
            cycle=cycle,
            notes=notes,
            balance_xrp_after=balance_xrp,
            balance_rlusd_after=balance_rlusd,
        )
        if side == "SELL":
            self.csv_logger.log_sell(**common)
            self.decision_log.add(
                "fill",
                f"SELL ~{xrp_amount:.4f} XRP for {rlusd_amount:.4f} RLUSD ({src_note})",
            )
        else:
            self.csv_logger.log_buy(**common)
            self.decision_log.add(
                "fill",
                f"BUY ~{xrp_amount:.4f} XRP for {rlusd_amount:.4f} RLUSD ({src_note})",
            )

    def _detect_and_log_fills(
        self,
        *,
        config: BotConfig,
        balance_xrp: float,
        rlusd_balance: float,
        mid_price: Optional[float],
    ) -> None:
        if self._last_cycle_balances is None:
            return
        prev_xrp, prev_rlusd = self._last_cycle_balances
        fill = detect_fill_from_balance_delta(
            prev_xrp=prev_xrp,
            prev_rlusd=prev_rlusd,
            curr_xrp=balance_xrp,
            curr_rlusd=rlusd_balance,
            mid_price=mid_price,
        )
        if not fill:
            return
        self._log_fill(
            config=config,
            side=str(fill["side"]),
            xrp_amount=float(fill["xrp_amount"]),
            rlusd_amount=float(fill["rlusd_amount"]),
            price=float(fill["price_rlusd_per_xrp"]),
            mid_price=mid_price,
            fill_source="balance_delta",
            balance_xrp=balance_xrp,
            balance_rlusd=rlusd_balance,
        )

    async def _maybe_kill_on_rpc_failures(
        self, config: BotConfig, connector: XRPLConnector
    ) -> None:
        limit = int(getattr(config, "rpc_failure_kill_streak", 6))
        if limit <= 0 or self._rpc_failure_streak < limit:
            return
        if self.kill_switch.is_active():
            return
        reason = f"RPC/ledger failure streak {self._rpc_failure_streak} (limit {limit})"
        await self._activate_kill_switch(connector, config, reason)

    async def _maybe_kill_on_spread_failures(
        self, config: BotConfig, connector: XRPLConnector
    ) -> None:
        limit = int(getattr(config, "spread_failure_kill_cycles", 8))
        if limit <= 0 or self._consecutive_spread_failures < limit:
            return
        if self.kill_switch.is_active():
            return
        reason = (
            f"Spread check failed {self._consecutive_spread_failures} consecutive cycles "
            f"(limit {limit})"
        )
        await self._activate_kill_switch(connector, config, reason)

    async def _maybe_kill_on_toxic_fills(
        self, config: BotConfig, fill_quality: Any, connector: XRPLConnector
    ) -> None:
        min_fills = int(getattr(config, "toxic_fill_min_count", 5))
        threshold = float(getattr(config, "toxic_fill_ratio_kill_threshold", 0.55))
        if fill_quality.recent_fills < min_fills:
            return
        ratio = fill_quality.toxic_fills / max(1, fill_quality.recent_fills)
        if ratio < threshold or self.kill_switch.is_active():
            return
        reason = (
            f"Toxic fill ratio {ratio:.0%} over last {fill_quality.recent_fills} fills "
            f"(threshold {threshold:.0%})"
        )
        await self._activate_kill_switch(connector, config, reason)

    async def _refresh_orders(
        self, intents: List[QuoteIntent], *, exec_cfg: Optional[ProfileExecution] = None
    ) -> int:
        if self.config.dry_run:
            self.decision_log.add(
                "execution",
                f"Dry-run: would refresh {len(intents)} quotes (no ledger submit).",
            )
            return 0

        profile = get_profile(self.config.active_profile)
        if exec_cfg is None:
            exec_cfg = resolve_profile_execution(profile, self.config)
        selective = bool(getattr(self.config, "selective_order_refresh", True))
        open_offers = await self.connector.get_open_offers()
        cancelled = 0
        placed = 0
        kept = 0

        if selective and intents:
            plan = plan_order_sync(
                intents,
                open_offers,
                price_tolerance_pct=exec_cfg.order_price_tolerance_pct,
                size_tolerance_xrp=exec_cfg.order_size_tolerance_xrp,
            )
            for seq in plan.cancel_sequences:
                try:
                    await self.connector.cancel_offer(seq)
                    cancelled += 1
                except Exception as exc:
                    self.decision_log.add("execution", f"Cancel seq {seq} failed: {exc}")
            to_place = plan.place_intents
            kept = plan.kept_count
            self._session_offers_kept += kept
            self._session_offers_cancelled += cancelled
            if plan.kept_count or plan.cancel_sequences or to_place:
                self.decision_log.add(
                    "execution",
                    f"Profile {profile.name} sync: kept {plan.kept_count}, "
                    f"cancel {len(plan.cancel_sequences)}, place {len(to_place)} "
                    f"(tol {exec_cfg.order_price_tolerance_pct:.2f}% / "
                    f"{exec_cfg.order_size_tolerance_xrp:.2f} XRP).",
                )
        else:
            cancelled = await self.connector.cancel_all_offers()
            self._session_offers_cancelled += cancelled
            to_place = list(intents)
            self.decision_log.add(
                "execution", f"Cancelled {cancelled} open offers before refresh."
            )

        for intent in to_place:
            try:
                await self.connector.place_quote(intent)
                placed += 1
            except Exception as exc:
                self.decision_log.add(
                    "execution",
                    f"Failed {intent.side} L{intent.level}: {exc}",
                )
        self.decision_log.add("execution", f"Placed {placed}/{len(to_place)} offers.")
        self.csv_logger.log_offer_refresh(
            network=self.config.network_name(),
            placed=placed,
            cancelled=cancelled,
            cycle=self._cycle_count + 1,
            dry_run=False,
        )
        return placed
    def _persist_state(
        self,
        *,
        perception: BotPerception,
        config: BotConfig,
        balance_xrp: float,
        balance_rlusd: float,
        open_offers: List[Any],
        quote_intents: List[QuoteIntent],
        placed_count: int,
        execution_summary: str,
        best_bid: Optional[float] = None,
        best_ask: Optional[float] = None,
        preflight: Optional[Any] = None,
        portfolio_value: float = 0.0,
        drawdown_pct: float = 0.0,
        market_assessment: Optional[Any] = None,
        quote_adjustments: Optional[Any] = None,
        book_spread_pct: float = 0.0,
        mid_momentum: float = 0.0,
        spread_validation: Optional[Any] = None,
        rebalance: Optional[Any] = None,
        fill_quality: Optional[Any] = None,
        effective_min_edge_pct: float = 0.0,
        edge_resolution_summary: str = "",
        dynamic_min_edge_enabled: bool = False,
        exec_cfg: Optional[ProfileExecution] = None,
        full_refresh: bool = True,
    ) -> None:
        decisions = [
            {"ts_utc": e.ts_utc, "category": e.category, "message": e.message}
            for e in self.decision_log.recent_newest_first(limit=60)
        ]
        mid = perception.mid_price or 0.0
        pnl_balance = 0.0
        pnl_mtm = 0.0
        if (
            self._session_baseline_xrp is not None
            and self._session_baseline_rlusd is not None
            and mid > 0
        ):
            pnl_balance = session_pnl_balance_delta_xrp(
                balance_xrp=balance_xrp,
                balance_rlusd=balance_rlusd,
                baseline_xrp=self._session_baseline_xrp,
                baseline_rlusd=self._session_baseline_rlusd,
                mid_rlusd_per_xrp=mid,
            )
        if self._session_baseline_portfolio_xrp is not None:
            pnl_mtm = session_pnl_mtm_xrp(
                portfolio_value_xrp=portfolio_value,
                baseline_portfolio_xrp=self._session_baseline_portfolio_xrp,
            )
        pf = preflight or self._last_preflight
        recommended_profile = config.active_profile
        recommendation_reason = ""
        if market_assessment:
            recommended_profile, recommendation_reason = normalize_profile_recommendation(
                market_assessment.recommended_profile,
                market_assessment.recommendation_reason,
            )
        state = RuntimeState(
            version=VERSION,
            network=config.network_name(),
            rpc_url=config.resolved_rpc_url(),
            dry_run=config.dry_run,
            trading_enabled=config.trading_enabled,
            kill_switch_active=self.kill_switch.is_active(),
            kill_switch_reason=self.kill_switch.reason,
            preflight_ready=bool(pf.ready) if pf else False,
            preflight_summary=pf.summary() if pf else "",
            preflight_errors=list(pf.errors) if pf else [],
            preflight_warnings=list(pf.warnings) if pf else [],
            portfolio_value_xrp=portfolio_value,
            drawdown_pct=drawdown_pct,
            active_profile=perception.active_profile.name,
            mid_price=perception.mid_price,
            best_bid_rlusd_per_xrp=best_bid,
            best_ask_rlusd_per_xrp=best_ask,
            price_is_testnet_book=config.testnet,
            volatility_pct=perception.volatility_pct,
            liquidity_score=perception.liquidity.liquidity_score,
            effective_spreads_pct=perception.effective_spreads_pct,
            balance_xrp=balance_xrp,
            balance_rlusd=balance_rlusd,
            open_offers_count=len(open_offers),
            open_offers=[
                {
                    "sequence": int(o.sequence),
                    "side": str(o.side),
                    "price": float(o.price),
                    "size_xrp": float(o.size_xrp),
                }
                for o in open_offers
            ],
            cycle_count=self._cycle_count,
            offers_placed_last_cycle=placed_count,
            last_execution_summary=execution_summary,
            session_baseline_xrp=self._session_baseline_xrp,
            session_baseline_rlusd=self._session_baseline_rlusd,
            session_baseline_mid=self._session_baseline_mid,
            session_baseline_portfolio_xrp=self._session_baseline_portfolio_xrp,
            session_pnl_mtm_xrp=pnl_mtm,
            session_pnl_balance_xrp=pnl_balance,
            session_pnl_xrp_estimate=pnl_mtm,
            quote_intents=quote_intents,
            recent_decisions=decisions,
            last_error=None,
            engine_pid=os.getpid(),
            price_source="xrpl_book_offers",
            price_history=list(self._price_history),
            market_condition=market_assessment.condition if market_assessment else "neutral",
            market_condition_label=market_assessment.condition_label if market_assessment else "Neutral",
            volatility_level=market_assessment.volatility_level if market_assessment else "moderate",
            liquidity_level=market_assessment.liquidity_level if market_assessment else "moderate",
            book_spread_pct=book_spread_pct,
            book_spread_status=market_assessment.book_spread_status if market_assessment else "unknown",
            market_health_score=market_assessment.health_score if market_assessment else 0.0,
            recommended_profile=recommended_profile,
            recommendation_reason=recommendation_reason,
            quote_decision_summary=quote_adjustments.decision_summary if quote_adjustments else "",
            inventory_label=quote_adjustments.inventory_label if quote_adjustments else "balanced",
            mid_momentum_pct=mid_momentum,
            spread_validation_ok=bool(spread_validation.ok) if spread_validation else False,
            spread_validation_summary=(
                spread_validation.summary if spread_validation else ""
            ),
            spread_validation_errors=(
                list(spread_validation.errors) if spread_validation else []
            ),
            spread_validation_lines=(
                list(spread_validation.lines) if spread_validation else []
            ),
            adverse_selection_tier=(
                quote_adjustments.adverse_selection_tier if quote_adjustments else "none"
            ),
            book_pressure_label=(
                quote_adjustments.book_pressure_label if quote_adjustments else "balanced"
            ),
            market_edge_met=(
                bool(quote_adjustments.market_edge_met) if quote_adjustments else True
            ),
            market_edge_pct=(
                float(quote_adjustments.market_edge_pct) if quote_adjustments else 0.0
            ),
            fill_quality_score=float(fill_quality.score) if fill_quality else 100.0,
            fill_quality_summary=str(fill_quality.summary) if fill_quality else "",
            toxic_fill_ratio=float(fill_quality.toxic_ratio) if fill_quality else 0.0,
            toxic_fill_ratio_30s=float(fill_quality.toxic_ratio_30s) if fill_quality else 0.0,
            mean_markout_30s_pct=float(fill_quality.mean_markout_30s_pct) if fill_quality else 0.0,
            offers_cancelled_session=self._session_offers_cancelled,
            offers_kept_session=self._session_offers_kept,
            fills_session=self._session_fills,
            cancel_per_fill=self._cancel_per_fill_ratio(),
            book_poll_interval_seconds=int(exec_cfg.book_poll_interval_seconds) if exec_cfg else 15,
            full_quote_refresh_seconds=int(
                exec_cfg.book_poll_interval_seconds * exec_cfg.full_refresh_every_n_polls
            )
            if exec_cfg
            else int(getattr(config, "order_refresh_time_seconds", 60)),
            last_cycle_full_refresh=full_refresh,
            rebalance_action=str(rebalance.action) if rebalance else "",
            rebalance_summary=str(rebalance.summary) if rebalance else "",
            pause_bids=bool(quote_adjustments.pause_bids) if quote_adjustments else False,
            pause_asks=bool(quote_adjustments.pause_asks) if quote_adjustments else False,
            effective_min_edge_pct=effective_min_edge_pct,
            edge_resolution_summary=edge_resolution_summary,
            dynamic_min_edge_enabled=dynamic_min_edge_enabled,
            edge_strictness=float(getattr(config, "edge_strictness", 1.0)),
        )
        self.state_store.save(state)
    def _persist_error(self, message: str) -> None:
        existing = self.state_store.load()
        state = existing or RuntimeState(
            network=self.config.network_name(),
            rpc_url=self.config.resolved_rpc_url(),
            dry_run=self.config.dry_run,
        )
        state.last_error = message
        self.state_store.save(state)
