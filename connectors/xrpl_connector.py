from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass
from statistics import pstdev
from typing import Deque, Dict, List, Optional

from core.perception import LiquidityMetrics
from core.runtime_state import QuoteIntent

logger = logging.getLogger(__name__)

# RLUSD/XRP on ledger is typically ~0.5–5; raw XRPL "quality" is ~1e8+.
_MAX_PLAUSIBLE_RLUSD_PER_XRP = 100.0


def is_plausible_rlusd_per_xrp(price: Optional[float]) -> bool:
    if price is None:
        return False
    return 1e-8 < price <= _MAX_PLAUSIBLE_RLUSD_PER_XRP

try:
    from xrpl.asyncio.clients import AsyncJsonRpcClient
    from xrpl.asyncio.transaction import autofill_and_sign, submit_and_wait
    from xrpl.models.amounts import IssuedCurrencyAmount
    from xrpl.models.currencies import IssuedCurrency, XRP
    from xrpl.models.requests import AccountInfo, AccountLines, AccountOffers, BookOffers
    from xrpl.models.transactions import OfferCancel, OfferCreate, TrustSet
    from xrpl.utils import drops_to_xrp, xrp_to_drops
    from xrpl.wallet import Wallet
except ImportError:  # pragma: no cover - handled at runtime
    AsyncJsonRpcClient = None
    IssuedCurrencyAmount = None
    IssuedCurrency = None
    XRP = None
    AccountInfo = None
    AccountLines = None
    AccountOffers = None
    BookOffers = None
    OfferCancel = None
    OfferCreate = None
    autofill_and_sign = None
    submit_and_wait = None
    Wallet = None
    drops_to_xrp = None
    xrp_to_drops = None


@dataclass(frozen=True)
class XRPLNetworkConfig:
    json_rpc_url: str = "https://s.altnet.rippletest.net:51234"


@dataclass(frozen=True)
class OpenOffer:
    sequence: int
    side: str
    price: float
    size_xrp: float


@dataclass(frozen=True)
class TrustLineInfo:
    exists: bool
    balance: float = 0.0
    limit: float = 0.0


class XRPLConnector:
    """Async XRPL access for market data, balances, and offers (xrpl-py 4.x compatible)."""

    def __init__(
        self,
        *,
        account_address: str,
        secret: Optional[str],
        rlusd_issuer: str,
        rlusd_currency: str,
        network: XRPLNetworkConfig | None = None,
        volatility_window: int = 120,
    ) -> None:
        self._ensure_xrpl_py_available()
        self.account_address = account_address
        self.secret = secret
        self.rlusd_issuer = rlusd_issuer
        self.rlusd_currency = rlusd_currency
        self.network = network or XRPLNetworkConfig()
        self.client = AsyncJsonRpcClient(self.network.json_rpc_url)
        self._mid_prices: Deque[float] = deque(maxlen=max(10, volatility_window))

    @staticmethod
    def _ensure_xrpl_py_available() -> None:
        if AsyncJsonRpcClient is None:
            raise RuntimeError(
                "xrpl-py is not installed. Install with: pip install xrpl-py"
            )

    def load_wallet(self) -> Wallet:
        if not self.secret:
            raise ValueError("Bot secret key is required to load wallet.")
        wallet = Wallet.from_seed(seed=self.secret)
        if wallet.classic_address != self.account_address:
            raise ValueError(
                "bot_secret_key does not match bot_account_address. "
                "Use credentials for the Bot Account only."
            )
        return wallet

    async def get_xrp_balance(self) -> float:
        req = AccountInfo(account=self.account_address, ledger_index="validated")
        result = (await self.client.request(req)).result
        drops_balance = result["account_data"]["Balance"]
        return float(drops_to_xrp(drops_balance))

    async def get_rlusd_trust_line(self) -> TrustLineInfo:
        req = AccountLines(
            account=self.account_address,
            peer=self.rlusd_issuer,
            ledger_index="validated",
        )
        lines = (await self.client.request(req)).result.get("lines", [])
        for line in lines:
            currency = line.get("currency", "")
            if currency == self.rlusd_currency or currency.startswith("524C555344"):
                return TrustLineInfo(
                    exists=True,
                    balance=float(line.get("balance", 0.0)),
                    limit=float(line.get("limit", 0.0)),
                )
        return TrustLineInfo(exists=False)

    async def get_rlusd_balance(self) -> float:
        return (await self.get_rlusd_trust_line()).balance

    @staticmethod
    def _validate_tx_response(response) -> str:
        result = response.result if hasattr(response, "result") else {}
        meta = result.get("meta", {})
        if isinstance(meta, dict):
            tx_result = meta.get("TransactionResult")
            if tx_result and tx_result != "tesSUCCESS":
                raise RuntimeError(f"XRPL transaction failed: {tx_result}")
        tx_hash = result.get("hash", "")
        if not tx_hash:
            raise RuntimeError("XRPL transaction returned no hash")
        return tx_hash

    async def setup_rlusd_trust_line(self, limit: str = "1000000000") -> str:
        """Create or increase RLUSD trust line (testnet/mainnet)."""
        wallet = self.load_wallet()
        tx = TrustSet(
            account=self.account_address,
            limit_amount=IssuedCurrencyAmount(
                currency=self.rlusd_currency,
                issuer=self.rlusd_issuer,
                value=limit,
            ),
        )
        signed = await autofill_and_sign(tx, self.client, wallet)
        response = await submit_and_wait(signed, self.client)
        return self._validate_tx_response(response)

    async def fetch_xrp_rlusd_order_book(
        self, limit: int = 40
    ) -> Dict[str, List[Dict[str, float]]]:
        taker_gets_xrp = XRP()
        taker_pays_rlusd = IssuedCurrency(
            currency=self.rlusd_currency,
            issuer=self.rlusd_issuer,
        )

        asks_req = BookOffers(
            taker_gets=taker_gets_xrp,
            taker_pays=taker_pays_rlusd,
            limit=limit,
        )
        bids_req = BookOffers(
            taker_gets=taker_pays_rlusd,
            taker_pays=taker_gets_xrp,
            limit=limit,
        )

        asks_raw = (await self.client.request(asks_req)).result.get("offers", [])
        bids_raw = (await self.client.request(bids_req)).result.get("offers", [])
        return {
            "asks": self._normalize_offers(asks_raw, side="ask"),
            "bids": self._normalize_offers(bids_raw, side="bid"),
        }

    async def get_open_offers(self) -> List[OpenOffer]:
        req = AccountOffers(account=self.account_address, ledger_index="validated")
        offers = (await self.client.request(req)).result.get("offers", [])
        parsed: List[OpenOffer] = []
        for offer in offers:
            seq = int(offer.get("seq", 0))
            gets = offer.get("TakerGets") or offer.get("taker_gets")
            pays = offer.get("TakerPays") or offer.get("taker_pays")
            if not seq or gets is None or pays is None:
                continue
            side, price, size_xrp = self._parse_offer_legs(gets, pays)
            if side:
                parsed.append(
                    OpenOffer(sequence=seq, side=side, price=price, size_xrp=size_xrp)
                )
        return parsed

    async def cancel_all_offers(self) -> int:
        wallet = self.load_wallet()
        cancelled = 0
        for offer in await self.get_open_offers():
            tx = OfferCancel(account=self.account_address, offer_sequence=offer.sequence)
            signed = await autofill_and_sign(tx, self.client, wallet)
            response = await submit_and_wait(signed, self.client)
            self._validate_tx_response(response)
            cancelled += 1
        return cancelled

    async def place_quote(self, intent: QuoteIntent) -> str:
        wallet = self.load_wallet()
        rlusd_amount = intent.size_xrp * intent.price
        if intent.side == "ask":
            taker_gets = str(xrp_to_drops(intent.size_xrp))
            taker_pays = IssuedCurrencyAmount(
                currency=self.rlusd_currency,
                issuer=self.rlusd_issuer,
                value=f"{rlusd_amount:.6f}",
            )
        elif intent.side == "bid":
            taker_gets = IssuedCurrencyAmount(
                currency=self.rlusd_currency,
                issuer=self.rlusd_issuer,
                value=f"{rlusd_amount:.6f}",
            )
            taker_pays = str(xrp_to_drops(intent.size_xrp))
        else:
            raise ValueError(f"Unsupported quote side: {intent.side}")

        tx = OfferCreate(
            account=self.account_address,
            taker_gets=taker_gets,
            taker_pays=taker_pays,
        )
        signed = await autofill_and_sign(tx, self.client, wallet)
        response = await submit_and_wait(signed, self.client)
        tx_hash = self._validate_tx_response(response)
        logger.info(
            "Placed %s L%s offer | size=%.4f XRP price=%.6f hash=%s",
            intent.side,
            intent.level,
            intent.size_xrp,
            intent.price,
            tx_hash,
        )
        return tx_hash

    def _parse_offer_legs(self, gets, pays) -> tuple[Optional[str], float, float]:
        if isinstance(gets, str) and isinstance(pays, dict):
            return (
                "ask",
                float(pays.get("value", 0.0)) / max(float(drops_to_xrp(gets)), 1e-9),
                float(drops_to_xrp(gets)),
            )
        if isinstance(gets, dict) and isinstance(pays, str):
            xrp_size = float(drops_to_xrp(pays))
            return "bid", float(gets.get("value", 0.0)) / max(xrp_size, 1e-9), xrp_size
        return None, 0.0, 0.0

    def _normalize_offers(self, offers: List[dict], *, side: str) -> List[Dict[str, float]]:
        """Convert BookOffers entries to RLUSD-per-XRP price and XRP size."""
        normalized: List[Dict[str, float]] = []
        for offer in offers:
            gets = offer.get("TakerGets") or offer.get("taker_gets")
            pays = offer.get("TakerPays") or offer.get("taker_pays")
            if gets is None or pays is None:
                continue

            price, size_xrp = self._book_offer_price_and_size(gets, pays)
            if price is None or price <= 0 or size_xrp <= 0:
                continue

            normalized.append({"price": price, "size": size_xrp, "side": side})
        return normalized

    def _book_offer_price_and_size(self, gets, pays) -> tuple[Optional[float], float]:
        """
        Return (RLUSD per 1 XRP, XRP size) from offer legs.
        """
        try:
            if isinstance(gets, str) and isinstance(pays, dict):
                # Taker receives XRP, pays RLUSD (buy XRP with RLUSD).
                xrp = float(drops_to_xrp(gets))
                rlusd = float(pays.get("value", 0.0))
                if xrp <= 0:
                    return None, 0.0
                return rlusd / xrp, xrp

            if isinstance(gets, dict) and isinstance(pays, str):
                # Taker receives RLUSD, pays XRP (sell XRP for RLUSD).
                rlusd = float(gets.get("value", 0.0))
                xrp = float(drops_to_xrp(pays))
                if xrp <= 0:
                    return None, 0.0
                return rlusd / xrp, xrp
        except (TypeError, ValueError):
            return None, 0.0
        return None, 0.0

    def compute_best_prices(
        self, order_book: Dict[str, List[Dict[str, float]]]
    ) -> tuple[Optional[float], Optional[float]]:
        """Return (best_bid, best_ask) as RLUSD per 1 XRP."""
        bids = order_book.get("bids", [])
        asks = order_book.get("asks", [])
        best_bid = max(bids, key=lambda x: x["price"])["price"] if bids else None
        best_ask = min(asks, key=lambda x: x["price"])["price"] if asks else None
        return best_bid, best_ask

    def compute_mid_price(self, order_book: Dict[str, List[Dict[str, float]]]) -> Optional[float]:
        bids = order_book.get("bids", [])
        asks = order_book.get("asks", [])
        if not bids or not asks:
            return None
        # RLUSD per XRP: highest bid, lowest ask.
        best_bid = max(bids, key=lambda x: x["price"])["price"]
        best_ask = min(asks, key=lambda x: x["price"])["price"]
        if best_bid <= 0 or best_ask <= 0:
            return None
        # Ignore crossed/invalid books (testnet often has stale liquidity).
        if best_bid > best_ask * 1.05:
            logger.warning(
                "Order book crossed or stale (bid=%.6f ask=%.6f); using ask as mid.",
                best_bid,
                best_ask,
            )
            return best_ask
        return (best_bid + best_ask) / 2.0

    def update_and_estimate_volatility_pct(self, mid_price: Optional[float]) -> float:
        if mid_price is None or mid_price <= 0:
            return 0.0
        self._mid_prices.append(mid_price)
        if len(self._mid_prices) < 8:
            return 0.0

        returns: List[float] = []
        prices = list(self._mid_prices)
        for prev, cur in zip(prices[:-1], prices[1:]):
            if prev > 0 and cur > 0:
                returns.append(math.log(cur / prev))
        if len(returns) < 2:
            return 0.0
        return pstdev(returns) * 100.0

    def compute_liquidity_metrics(
        self,
        order_book: Dict[str, List[Dict[str, float]]],
        *,
        depth_levels: int = 12,
    ) -> LiquidityMetrics:
        bids = sorted(order_book.get("bids", []), key=lambda x: x["price"], reverse=True)[
            :depth_levels
        ]
        asks = sorted(order_book.get("asks", []), key=lambda x: x["price"])[:depth_levels]

        bid_depth = sum(level["size"] for level in bids)
        ask_depth = sum(level["size"] for level in asks)
        total_depth = bid_depth + ask_depth

        if total_depth <= 0:
            return LiquidityMetrics()

        imbalance = (bid_depth - ask_depth) / total_depth
        depth_component = min(1.0, total_depth / 15000.0)
        imbalance_penalty = min(1.0, abs(imbalance))
        score = max(0.0, (0.75 * depth_component) + (0.25 * (1.0 - imbalance_penalty)))

        default_target_size = 150.0
        top_depth = 0.0
        if bids:
            top_depth += bids[0]["size"]
        if asks:
            top_depth += asks[0]["size"]
        est_fill_seconds = (
            999.0 if top_depth <= 0 else max(1.0, default_target_size / top_depth) * 60.0
        )

        return LiquidityMetrics(
            bid_depth_xrp=bid_depth,
            ask_depth_xrp=ask_depth,
            depth_imbalance=imbalance,
            liquidity_score=score,
            estimated_time_to_fill_seconds=est_fill_seconds,
        )
