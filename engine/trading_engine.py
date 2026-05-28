from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from config.settings import BotConfig
from connectors import XRPLConnector, XRPLNetworkConfig
from core import BotPerception, DecisionLog, VERSION, get_profile
from core.runtime_state import QuoteIntent, RuntimeState, RuntimeStateStore
from engine.order_manager import OrderManager
from monitoring.csv_logger import CSVLogger
from monitoring.telegram_alerts import TelegramAlerts
from risk.drawdown import DrawdownMonitor, KillSwitch
from strategy.avellaneda_strategy import AvellanedaStrategy

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
        self._running = False

    async def run(self) -> None:
        self._running = True
        logger.info(
            "Trading engine started | network=%s dry_run=%s trading_enabled=%s",
            self.config.network_name(),
            self.config.dry_run,
            self.config.trading_enabled,
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

    async def _run_cycle(self) -> None:
        config = BotConfig.load()
        self.config = config
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

        try:
            balance_xrp = await connector.get_xrp_balance()
            rlusd_balance = await connector.get_rlusd_balance()
            self.drawdown_monitor.update_balance(balance_xrp)
            if self.drawdown_monitor.is_kill_switch_triggered():
                self.kill_switch.activate("Daily drawdown threshold reached")
                self.alerts.send_kill_switch_alert(
                    self.drawdown_monitor.get_drawdown_percent(),
                    "Daily drawdown threshold reached",
                )

            order_book = await connector.fetch_xrp_rlusd_order_book()
            liquidity = connector.compute_liquidity_metrics(order_book)
            mid_price = connector.compute_mid_price(order_book)
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
            self.decision_log.add("spread", spread_result.reason)

            quote_plan = self.order_manager.build_quotes(
                mid_price=mid_price or 0.0,
                spreads_pct=spread_result.effective_spreads_pct,
                xrp_balance=balance_xrp,
                rlusd_balance=rlusd_balance,
            )
            self.decision_log.add("quotes", quote_plan.reason)

            open_offers = await connector.get_open_offers()
            placed_count = 0
            if (
                config.trading_enabled
                and not self.kill_switch.is_active()
                and mid_price
                and quote_plan.intents
            ):
                placed_count = await self._refresh_orders(quote_plan.intents)

            self._persist_state(
                perception=perception,
                config=config,
                balance_xrp=balance_xrp,
                open_offers_count=len(open_offers),
                quote_intents=quote_plan.intents,
                placed_count=placed_count,
            )
            logger.info(
                "Cycle complete | profile=%s mid=%s vol=%.2f%% liq=%.2f intents=%s placed=%s",
                profile.name,
                f"{mid_price:.6f}" if mid_price else "n/a",
                perception.volatility_pct,
                perception.liquidity.liquidity_score,
                len(quote_plan.intents),
                placed_count,
            )
        except Exception as exc:
            logger.exception("Cycle failed: %s", exc)
            self._persist_error(str(exc))
        finally:
            self.connector = None

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
        return placed

    def _persist_state(
        self,
        *,
        perception: BotPerception,
        config: BotConfig,
        balance_xrp: float,
        open_offers_count: int,
        quote_intents: List[QuoteIntent],
        placed_count: int,
    ) -> None:
        decisions = [
            {"ts_utc": e.ts_utc, "category": e.category, "message": e.message}
            for e in self.decision_log.recent(limit=20)
        ]
        state = RuntimeState(
            version=VERSION,
            network=config.network_name(),
            rpc_url=config.resolved_rpc_url(),
            dry_run=config.dry_run,
            trading_enabled=config.trading_enabled,
            kill_switch_active=self.kill_switch.is_active(),
            active_profile=perception.active_profile.name,
            mid_price=perception.mid_price,
            volatility_pct=perception.volatility_pct,
            liquidity_score=perception.liquidity.liquidity_score,
            effective_spreads_pct=perception.effective_spreads_pct,
            balance_xrp=balance_xrp,
            open_offers_count=open_offers_count,
            quote_intents=quote_intents,
            recent_decisions=decisions,
            last_error=None,
        )
        if placed_count:
            state.recent_decisions.append(
                {
                    "ts_utc": state.updated_utc or "",
                    "category": "execution",
                    "message": f"Placed {placed_count} offers this cycle.",
                }
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
