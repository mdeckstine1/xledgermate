from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import pstdev
from typing import Deque, Dict, List, Optional
from collections import deque

from core.perception import LiquidityMetrics

try:
    from xrpl.clients import JsonRpcClient
    from xrpl.models.amounts import IssuedCurrencyAmount
    from xrpl.models.requests import AccountInfo, BookOffers
    from xrpl.utils import drops_to_xrp
    from xrpl.wallet import Wallet
except ImportError:  # pragma: no cover - handled at runtime
    JsonRpcClient = None
    IssuedCurrencyAmount = None
    AccountInfo = None
    BookOffers = None
    Wallet = None
    drops_to_xrp = None


@dataclass(frozen=True)
class XRPLNetworkConfig:
    json_rpc_url: str = "https://s.altnet.rippletest.net:51234"


class XRPLConnector:
    """XRPL market data + wallet access for XRP/RLUSD."""

    def __init__(
        self,
        *,
        account_address: str,
        secret: Optional[str],
        network: XRPLNetworkConfig | None = None,
        volatility_window: int = 120,
    ) -> None:
        self._ensure_xrpl_py_available()
        self.account_address = account_address
        self.secret = secret
        self.network = network or XRPLNetworkConfig()
        self.client = JsonRpcClient(self.network.json_rpc_url)
        self._mid_prices: Deque[float] = deque(maxlen=max(10, volatility_window))

    @staticmethod
    def _ensure_xrpl_py_available() -> None:
        if JsonRpcClient is None:
            raise RuntimeError(
                "xrpl-py is not installed. Install with: pip install xrpl-py"
            )

    def load_wallet(self) -> Wallet:
        if not self.secret:
            raise ValueError("Bot secret key is required to load wallet.")
        return Wallet.from_seed(seed=self.secret)

    def get_xrp_balance(self) -> float:
        req = AccountInfo(account=self.account_address, ledger_index="validated")
        result = self.client.request(req).result
        drops_balance = result["account_data"]["Balance"]
        return float(drops_to_xrp(drops_balance))

    def fetch_xrp_rlusd_order_book(self, limit: int = 40) -> Dict[str, List[Dict[str, float]]]:
        # XRP is represented in drops as a plain string for BookOffers takes/gets.
        taker_gets_xrp = "1000000"
        taker_pays_rlusd = IssuedCurrencyAmount(
            currency="RLUSD",
            issuer="rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De",
            value="1",
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

        asks_raw = self.client.request(asks_req).result.get("offers", [])
        bids_raw = self.client.request(bids_req).result.get("offers", [])
        asks = self._normalize_offers(asks_raw)
        bids = self._normalize_offers(bids_raw)
        return {"bids": bids, "asks": asks}

    def _normalize_offers(self, offers: List[dict]) -> List[Dict[str, float]]:
        normalized: List[Dict[str, float]] = []
        for offer in offers:
            quality = offer.get("quality")
            funded = offer.get("taker_gets_funded") or offer.get("TakerGets")

            if quality is None or funded is None:
                continue

            try:
                price = float(quality)
                if isinstance(funded, dict):
                    # Issued asset amount represented as decimal string.
                    size = float(funded.get("value", 0.0))
                else:
                    # XRP amount in drops.
                    size = float(drops_to_xrp(funded))
            except (TypeError, ValueError):
                continue

            normalized.append({"price": price, "size": size})
        return normalized

    def compute_mid_price(self, order_book: Dict[str, List[Dict[str, float]]]) -> Optional[float]:
        bids = order_book.get("bids", [])
        asks = order_book.get("asks", [])
        if not bids or not asks:
            return None
        best_bid = max(bids, key=lambda x: x["price"])["price"]
        best_ask = min(asks, key=lambda x: x["price"])["price"]
        if best_bid <= 0 or best_ask <= 0:
            return None
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
        bids = sorted(order_book.get("bids", []), key=lambda x: x["price"], reverse=True)[:depth_levels]
        asks = sorted(order_book.get("asks", []), key=lambda x: x["price"])[:depth_levels]

        bid_depth = sum(level["size"] for level in bids)
        ask_depth = sum(level["size"] for level in asks)
        total_depth = bid_depth + ask_depth

        if total_depth <= 0:
            return LiquidityMetrics()

        imbalance = (bid_depth - ask_depth) / total_depth
        # Smooth score: depth supports score, imbalance penalizes score.
        depth_component = min(1.0, total_depth / 15000.0)
        imbalance_penalty = min(1.0, abs(imbalance))
        score = max(0.0, (0.75 * depth_component) + (0.25 * (1.0 - imbalance_penalty)))

        # Rough "time-to-fill": how many refresh cycles for L1 default size.
        default_target_size = 150.0
        top_depth = 0.0
        if bids:
            top_depth += bids[0]["size"]
        if asks:
            top_depth += asks[0]["size"]
        est_fill_seconds = 999.0 if top_depth <= 0 else max(1.0, default_target_size / top_depth) * 60.0

        return LiquidityMetrics(
            bid_depth_xrp=bid_depth,
            ask_depth_xrp=ask_depth,
            depth_imbalance=imbalance,
            liquidity_score=score,
            estimated_time_to_fill_seconds=est_fill_seconds,
        )
