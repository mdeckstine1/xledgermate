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
from core import BotPerception, DecisionLog, VERSION, get_profile
from core.runtime_state import QuoteIntent, RuntimeState, RuntimeStateStore
from engine.order_manager import OrderManager
from monitoring.balance_logger import BalanceLogger
from monitoring.csv_logger import CSVLogger
from monitoring.fill_detection import detect_fill_from_balance_delta
from monitoring.telegram_alerts import TelegramAlerts
from risk.drawdown import DrawdownMonitor, portfolio_value_xrp
from risk.kill_switch import KillSwitch
from strategy.avellaneda_strategy import AvellanedaStrategy
from utils.preflight import evaluate_preflight
logger = logging.getLogger(__name__)
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
        self._decision_log_path = Path("logs/decisions.jsonl")
        self._decision_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._price_history: List[dict] = []
        self._price_history_max = 180
        self._last_preflight: Optional[Any] = None
        self._last_cycle_balances: Optional[tuple[float, float]] = None
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
            try:
                await self._run_cycle()
            except Exception as exc:
                logger.exception("Engine cycle failed: %s", exc)
                self._persist_error(str(exc))
            await asyncio.sleep(self.config.order_refresh_time_seconds)
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
    async def _run_cycle(self) -> None:
        config = BotConfig.load()
        self.config = config
        self.alerts = TelegramAlerts(
            token=config.telegram_token,
            chat_id=config.telegram_chat_id,
            enabled=config.telegram_enabled,
        )
        profile = get_profile(config.active_profile)
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
        balance_xrp = 0.0
        rlusd_balance = 0.0
        mid_price: Optional[float] = None
        best_bid: Optional[float] = None
        best_ask: Optional[float] = None
        open_offers: List[Any] = []
        placed_count = 0
        portfolio_value = 0.0
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
            if not config.dry_run:
                self._detect_and_log_fills(
                    config=config,
                    balance_xrp=balance_xrp,
                    rlusd_balance=rlusd_balance,
                    mid_price=mid_price,
                )
            drawdown_pct = self.drawdown_monitor.get_drawdown_percent()
            if self.drawdown_monitor.is_kill_switch_triggered():
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
            spread_result = self.strategy.compute_spreads(
                volatility_pct=volatility_pct,
                liquidity_score=liquidity.liquidity_score,
                profile=profile,
            )
            perception.update_market_state(
                mid_price=mid_price or 0.0,
                volatility_pct=volatility_pct,
                liquidity=liquidity,
                effective_spreads_pct=spread_result.effective_spreads_pct,
            )
            if preflight.ready and mid_price and not self.kill_switch.is_active():
                self.decision_log.add("spread", spread_result.reason)
                quote_plan = self.order_manager.build_quotes(
                    mid_price=mid_price,
                    spreads_pct=spread_result.effective_spreads_pct,
                    xrp_balance=balance_xrp,
                    rlusd_balance=rlusd_balance,
                )
                book_note = ""
                if best_bid is not None and best_ask is not None:
                    book_note = (
                        f" | book bid={best_bid:.6f} ask={best_ask:.6f} "
                        f"mid={mid_price:.6f} RLUSD/XRP"
                    )
                self.decision_log.add("quotes", quote_plan.reason + book_note)
                self._record_price_tick(mid=mid_price, bid=best_bid, ask=best_ask)
            else:
                quote_plan = None
                if not preflight.ready:
                    self.decision_log.add("quotes", "Skipped — preflight not ready.")
            if (
                quote_plan
                and quote_plan.intents
                and config.trading_enabled
                and not self.kill_switch.is_active()
                and preflight.ready
            ):
                placed_count = await self._refresh_orders(quote_plan.intents)
            open_offers = await connector.get_open_offers()
            if self._session_baseline_xrp is None:
                self._session_baseline_xrp = balance_xrp
                self._session_baseline_rlusd = rlusd_balance
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
            )
            logger.info(
                "Cycle complete | #%s profile=%s mid=%.4f RLUSD/XRP portfolio=%.4f XRP "
                "drawdown=%.2f%% intents=%s placed=%s preflight=%s",
                self._cycle_count,
                profile.name,
                mid_price or 0.0,
                portfolio_value,
                drawdown_pct,
                len(quote_plan.intents) if quote_plan else 0,
                placed_count,
                "OK" if preflight and preflight.ready else "FAIL",
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
        cycle = self._cycle_count + 1
        notes = "Inferred from balance change between cycles (verify on ledger for taxes)."
        common = dict(
            network=config.network_name(),
            xrp_amount=float(fill["xrp_amount"]),
            rlusd_amount=float(fill["rlusd_amount"]),
            price_rlusd_per_xrp=float(fill["price_rlusd_per_xrp"]),
            cycle=cycle,
            notes=notes,
            balance_xrp_after=balance_xrp,
            balance_rlusd_after=rlusd_balance,
        )
        if fill["side"] == "SELL":
            self.csv_logger.log_sell(**common)
            self.decision_log.add(
                "fill",
                f"SELL ~{common['xrp_amount']:.4f} XRP for {common['rlusd_amount']:.4f} RLUSD",
            )
        else:
            self.csv_logger.log_buy(**common)
            self.decision_log.add(
                "fill",
                f"BUY ~{common['xrp_amount']:.4f} XRP for {common['rlusd_amount']:.4f} RLUSD",
            )

    async def _refresh_orders(self, intents: List[QuoteIntent]) -> int:
        if self.config.dry_run:
            self.decision_log.add(
                "execution",
                f"Dry-run: would refresh {len(intents)} quotes (no ledger submit).",
            )
            return 0
        cancelled = await self.connector.cancel_all_offers()
        self.decision_log.add("execution", f"Cancelled {cancelled} open offers before refresh.")
        placed = 0
        for intent in intents:
            try:
                await self.connector.place_quote(intent)
                placed += 1
            except Exception as exc:
                self.decision_log.add(
                    "execution",
                    f"Failed {intent.side} L{intent.level}: {exc}",
                )
        self.decision_log.add("execution", f"Placed {placed}/{len(intents)} offers.")
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
    ) -> None:
        decisions = [
            {"ts_utc": e.ts_utc, "category": e.category, "message": e.message}
            for e in self.decision_log.recent_newest_first(limit=60)
        ]
        mid = perception.mid_price or 0.0
        pnl_estimate = 0.0
        if (
            self._session_baseline_xrp is not None
            and self._session_baseline_rlusd is not None
            and mid > 0
        ):
            current_val = portfolio_value_xrp(balance_xrp, balance_rlusd, mid)
            baseline_val = portfolio_value_xrp(
                self._session_baseline_xrp,
                self._session_baseline_rlusd,
                mid,
            )
            pnl_estimate = current_val - baseline_val
        pf = preflight or self._last_preflight
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
            session_pnl_xrp_estimate=pnl_estimate,
            quote_intents=quote_intents,
            recent_decisions=decisions,
            last_error=None,
            engine_pid=os.getpid(),
            price_source="xrpl_book_offers",
            price_history=list(self._price_history),
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
