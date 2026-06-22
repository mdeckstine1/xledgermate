from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass
from statistics import pstdev
from typing import Deque, Dict, List, Optional, Any

from core.perception import LiquidityMetrics
from core.runtime_state import QuoteIntent
from utils.rpc_health import amendment_blocked_message, is_retryable_rpc_error, request_with_retry
from utils.wallet_credentials import wallet_from_bot_secret

logger = logging.getLogger(__name__)

# RLUSD/XRP on ledger is typically ~0.5–5; raw XRPL "quality" is ~1e8+.
_MIN_PLAUSIBLE_RLUSD_PER_XRP = 0.45
_MAX_PLAUSIBLE_RLUSD_PER_XRP = 100.0
_CROSSED_BOOK_ASK_TOLERANCE = 1.05


def is_plausible_rlusd_per_xrp(price: Optional[float]) -> bool:
    if price is None:
        return False
    return _MIN_PLAUSIBLE_RLUSD_PER_XRP < price <= _MAX_PLAUSIBLE_RLUSD_PER_XRP


def is_book_crossed(best_bid: Optional[float], best_ask: Optional[float]) -> bool:
    if best_bid is None or best_ask is None or best_bid <= 0 or best_ask <= 0:
        return False
    return best_bid > best_ask * _CROSSED_BOOK_ASK_TOLERANCE


def is_trustworthy_rlusd_mid(
    mid: Optional[float],
    *,
    best_bid: Optional[float] = None,
    best_ask: Optional[float] = None,
) -> bool:
    """Reject raw-quality mids and crossed/stale books (bid >> ask)."""
    if not is_plausible_rlusd_per_xrp(mid):
        return False
    if is_book_crossed(best_bid, best_ask):
        return False
    if best_bid is None or best_ask is None or best_bid <= 0 or best_ask <= 0:
        return True
    lo, hi = min(best_bid, best_ask), max(best_bid, best_ask)
    return lo * 0.92 <= float(mid) <= hi * 1.08

try:
    from xrpl.asyncio.clients import AsyncJsonRpcClient
    from xrpl.asyncio.transaction import autofill_and_sign, submit_and_wait
    from xrpl.models.amounts import IssuedCurrencyAmount
    from xrpl.models.currencies import IssuedCurrency, XRP
    from xrpl.models.requests import AccountInfo, AccountLines, AccountOffers, AccountTx, BookOffers
    from xrpl.models.transactions import (
        OfferCancel,
        OfferCreate,
        Payment,
        TrustSet,
        TrustSetFlag,
    )
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
    AccountTx = None
    BookOffers = None
    OfferCancel = None
    OfferCreate = None
    Payment = None
    TrustSet = None
    TrustSetFlag = None
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
    no_ripple: bool = False


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
        from utils.xrpl_currency import resolve_rlusd_currency_code

        self.account_address = account_address
        self.secret = secret
        self.rlusd_issuer = rlusd_issuer
        self.rlusd_currency = resolve_rlusd_currency_code(rlusd_currency)
        self.network = network or XRPLNetworkConfig()
        self.client = AsyncJsonRpcClient(self.network.json_rpc_url)
        self._mid_prices: Deque[float] = deque(maxlen=max(10, volatility_window))

    def _issued_rlusd_currency_code(self) -> str:
        """Hex/code for BookOffers — xrpl-py rejects display name 'RLUSD'."""
        from utils.xrpl_currency import RLUSD_CURRENCY_HEX, resolve_rlusd_currency_code

        code = resolve_rlusd_currency_code(self.rlusd_currency)
        if code.upper() == "RLUSD" or len(code) < 20:
            return RLUSD_CURRENCY_HEX
        return code

    @staticmethod
    def _ensure_xrpl_py_available() -> None:
        if AsyncJsonRpcClient is None:
            raise RuntimeError(
                "xrpl-py is not installed. Install with: pip install xrpl-py"
            )

    def load_wallet(self) -> Wallet:
        if not self.secret:
            raise ValueError("Bot secret key is required to load wallet.")
        wallet = wallet_from_bot_secret(self.secret)
        if wallet.classic_address != self.account_address:
            raise ValueError(
                "bot_secret_key does not match bot_account_address. "
                "Use credentials for the Bot Account only."
            )
        return wallet

    async def _request(self, req: Any) -> Any:
        try:
            return await request_with_retry(self.client, req)
        except Exception as exc:
            if is_retryable_rpc_error(exc):
                raise RuntimeError(amendment_blocked_message(exc)) from exc
            raise

    async def _sign_and_submit(self, tx: Any, wallet: Wallet) -> Any:
        last_exc: Optional[BaseException] = None
        for attempt in range(4):
            try:
                signed = await autofill_and_sign(tx, self.client, wallet)
                return await submit_and_wait(signed, self.client)
            except Exception as exc:
                last_exc = exc
                if not is_retryable_rpc_error(exc) or attempt >= 3:
                    if is_retryable_rpc_error(exc):
                        raise RuntimeError(amendment_blocked_message(exc)) from exc
                    raise
                logger.warning(
                    "Ledger submit attempt %s/4 failed (%s); retrying…",
                    attempt + 1,
                    exc,
                )
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Ledger submit failed with no response")

    async def get_xrp_balance(self) -> float:
        req = AccountInfo(account=self.account_address, ledger_index="validated")
        result = (await self._request(req)).result
        drops_balance = result["account_data"]["Balance"]
        return float(drops_to_xrp(drops_balance))

    async def get_rlusd_trust_line(self) -> TrustLineInfo:
        req = AccountLines(
            account=self.account_address,
            peer=self.rlusd_issuer,
            ledger_index="validated",
        )
        lines = (await self._request(req)).result.get("lines", [])
        for line in lines:
            currency = line.get("currency", "")
            if currency == self.rlusd_currency or currency.startswith("524C555344"):
                return TrustLineInfo(
                    exists=True,
                    balance=float(line.get("balance", 0.0)),
                    limit=float(line.get("limit", 0.0)),
                    no_ripple=bool(line.get("no_ripple", False)),
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

    def _rlusd_limit_amount(self, value: str) -> IssuedCurrencyAmount:
        return IssuedCurrencyAmount(
            currency=self._issued_rlusd_currency_code(),
            issuer=self.rlusd_issuer,
            value=value,
        )

    async def setup_rlusd_trust_line(self, limit: str = "1000000000") -> str:
        """Create or increase RLUSD trust line with No Ripple enabled."""
        wallet = self.load_wallet()
        tx = TrustSet(
            account=self.account_address,
            limit_amount=self._rlusd_limit_amount(limit),
            flags=TrustSetFlag.TF_SET_NO_RIPPLE,
        )
        response = await self._sign_and_submit(tx, wallet)
        return self._validate_tx_response(response)

    async def disable_rlusd_rippling(self) -> str:
        """Set tfSetNoRipple on the existing RLUSD trust line (rippling off)."""
        trust = await self.get_rlusd_trust_line()
        if not trust.exists:
            raise ValueError("No RLUSD trust line on bot account.")
        if trust.no_ripple:
            return ""
        wallet = self.load_wallet()
        limit_value = f"{trust.limit:.6f}".rstrip("0").rstrip(".")
        if not limit_value or limit_value == "0":
            limit_value = "1000000000"
        tx = TrustSet(
            account=self.account_address,
            limit_amount=self._rlusd_limit_amount(limit_value),
            flags=TrustSetFlag.TF_SET_NO_RIPPLE,
        )
        response = await self._sign_and_submit(tx, wallet)
        return self._validate_tx_response(response)

    async def send_payment(
        self,
        *,
        destination: str,
        amount: float,
        asset: str = "XRP",
        xrp_reserve: float = 12.0,
    ) -> str:
        """Send XRP or RLUSD from the bot account to destination (classic address)."""
        dest = (destination or "").strip()
        if not dest.startswith("r"):
            raise ValueError("Destination must be a classic XRPL address (starts with r).")
        if dest == self.account_address:
            raise ValueError("Destination cannot be the bot account itself.")
        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")

        wallet = self.load_wallet()

        if asset.upper() == "XRP":
            balance = await self.get_xrp_balance()
            if amount + xrp_reserve > balance:
                raise ValueError(
                    f"Send would exceed spendable XRP. Balance={balance:.4f}, "
                    f"amount={amount:.4f}, reserve={xrp_reserve:.4f}."
                )
            tx = Payment(
                account=self.account_address,
                destination=dest,
                amount=str(xrp_to_drops(amount)),
            )
        elif asset.upper() == "RLUSD":
            trust = await self.get_rlusd_trust_line()
            if not trust.exists:
                raise ValueError("No RLUSD trust line on bot account.")
            if amount > trust.balance:
                raise ValueError(
                    f"Insufficient RLUSD balance ({trust.balance:.6f}) for send {amount:.6f}."
                )
            tx = Payment(
                account=self.account_address,
                destination=dest,
                amount=IssuedCurrencyAmount(
                    currency=self._issued_rlusd_currency_code(),
                    issuer=self.rlusd_issuer,
                    value=f"{amount:.6f}",
                ),
            )
        else:
            raise ValueError(f"Unsupported asset: {asset}. Use XRP or RLUSD.")

        response = await self._sign_and_submit(tx, wallet)
        tx_hash = self._validate_tx_response(response)
        logger.info(
            "Sent %s %s to %s | hash=%s",
            amount,
            asset.upper(),
            dest,
            tx_hash,
        )
        return tx_hash

    async def get_mid_price(self, limit: int = 40) -> Optional[float]:
        book = await self.fetch_xrp_rlusd_order_book(limit=limit)
        return self.compute_mid_price(book)

    async def fetch_xrp_rlusd_order_book(
        self, limit: int = 40
    ) -> Dict[str, List[Dict[str, float]]]:
        taker_gets_xrp = XRP()
        rlusd_code = self._issued_rlusd_currency_code()
        taker_pays_rlusd = IssuedCurrency(
            currency=rlusd_code,
            issuer=self.rlusd_issuer,
        )

        # Use validated ledger + taker perspective to reduce stale/ghost offers and
        # get quality-adjusted prices for the bot account (helps ask inversion / bad ticks).
        taker = self.account_address if (self.account_address or "").startswith("r") else None
        common = {"limit": limit, "ledger_index": "validated"}
        if taker:
            common["taker"] = taker

        asks_req = BookOffers(
            taker_gets=taker_gets_xrp,
            taker_pays=taker_pays_rlusd,
            **common,
        )
        bids_req = BookOffers(
            taker_gets=taker_pays_rlusd,
            taker_pays=taker_gets_xrp,
            **common,
        )

        asks_raw = (await self._request(asks_req)).result.get("offers", [])
        bids_raw = (await self._request(bids_req)).result.get("offers", [])
        book = {
            "asks": self._normalize_offers(asks_raw, side="ask"),
            "bids": self._normalize_offers(bids_raw, side="bid"),
        }
        return self._sanitize_book(book)

    async def fetch_order_book(self, limit: int = 40) -> Dict[str, List[Dict[str, Any]]]:
        """Alias used by CompetitorIntelProvider for on-chain maker scraping.
        Returns the same shape as fetch_xrp_rlusd_order_book but with 'account' preserved in each offer.
        """
        return await self.fetch_xrp_rlusd_order_book(limit=limit)

    @staticmethod
    def _offer_field(offer: Any, *keys: str) -> Any:
        if isinstance(offer, dict):
            for key in keys:
                if key in offer and offer[key] is not None:
                    return offer[key]
            return None
        for key in keys:
            val = getattr(offer, key, None)
            if val is not None:
                return val
        return None

    @staticmethod
    def _coerce_ledger_amount(amount: Any) -> Any:
        """Normalize xrpl-py Amount models to str XRP drops or issued-currency dict."""
        if amount is None or isinstance(amount, (str, dict)):
            return amount
        if hasattr(amount, "to_dict"):
            try:
                return amount.to_dict()
            except (TypeError, ValueError, AttributeError):
                pass
        if hasattr(amount, "value"):
            out: Dict[str, Any] = {"value": str(getattr(amount, "value"))}
            currency = getattr(amount, "currency", None)
            issuer = getattr(amount, "issuer", None)
            if currency is not None:
                out["currency"] = currency
            if issuer is not None:
                out["issuer"] = issuer
            return out
        return amount

    async def get_open_offer_sequences(self) -> List[int]:
        """Offer sequence numbers from AccountOffers (for cancel even if leg parse fails)."""
        req = AccountOffers(account=self.account_address, ledger_index="validated")
        offers = (await self._request(req)).result.get("offers", [])
        sequences: List[int] = []
        for offer in offers or []:
            seq_raw = self._offer_field(offer, "seq", "Sequence", "sequence")
            if seq_raw is None:
                continue
            try:
                seq = int(seq_raw)
            except (TypeError, ValueError):
                continue
            if seq > 0:
                sequences.append(seq)
        return sequences

    async def get_open_offers(self) -> List[OpenOffer]:
        req = AccountOffers(account=self.account_address, ledger_index="validated")
        offers = (await self._request(req)).result.get("offers", [])
        parsed: List[OpenOffer] = []
        for offer in offers or []:
            seq_raw = self._offer_field(offer, "seq", "Sequence", "sequence")
            if seq_raw is None:
                continue
            try:
                seq = int(seq_raw)
            except (TypeError, ValueError):
                continue
            if seq <= 0:
                continue
            gets = self._coerce_ledger_amount(
                self._offer_field(offer, "TakerGets", "taker_gets")
            )
            pays = self._coerce_ledger_amount(
                self._offer_field(offer, "TakerPays", "taker_pays")
            )
            if gets is None or pays is None:
                continue
            side, price, size_xrp = self._parse_offer_legs(gets, pays)
            if side:
                parsed.append(
                    OpenOffer(sequence=seq, side=side, price=price, size_xrp=size_xrp)
                )
        return parsed

    async def fetch_account_transactions(self, limit: int = 40) -> List[Dict[str, Any]]:
        """Recent validated ledger transactions for fill scanning."""
        req = AccountTx(
            account=self.account_address,
            ledger_index_min=-1,
            limit=max(1, min(limit, 100)),
        )
        result = (await self._request(req)).result
        txs = result.get("transactions", [])
        return list(txs) if isinstance(txs, list) else []

    async def cancel_offer(self, sequence: int) -> str:
        wallet = self.load_wallet()
        tx = OfferCancel(account=self.account_address, offer_sequence=sequence)
        response = await self._sign_and_submit(tx, wallet)
        return self._validate_tx_response(response)

    async def cancel_all_offers(self) -> int:
        """Cancel every AccountOffers entry by sequence (does not rely on leg parsing)."""
        wallet = self.load_wallet()
        sequences = await self.get_open_offer_sequences()
        cancelled = 0
        for seq in sequences:
            tx = OfferCancel(account=self.account_address, offer_sequence=seq)
            response = await self._sign_and_submit(tx, wallet)
            self._validate_tx_response(response)
            cancelled += 1
            logger.info("Cancelled offer seq=%s on %s", seq, self.account_address)
        remaining = await self.get_open_offer_sequences()
        if remaining:
            logger.warning(
                "%s offer(s) still open after cancel (%s submitted).",
                len(remaining),
                cancelled,
            )
        return cancelled

    async def place_quote(self, intent: QuoteIntent) -> str:
        wallet = self.load_wallet()
        rlusd_amount = intent.size_xrp * intent.price
        if intent.side == "ask":
            taker_gets = str(xrp_to_drops(intent.size_xrp))
            taker_pays = IssuedCurrencyAmount(
                currency=self._issued_rlusd_currency_code(),
                issuer=self.rlusd_issuer,
                value=f"{rlusd_amount:.6f}",
            )
        elif intent.side == "bid":
            taker_gets = IssuedCurrencyAmount(
                currency=self._issued_rlusd_currency_code(),
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
        response = await self._sign_and_submit(tx, wallet)
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

    def _normalize_offers(self, offers: List[dict], *, side: str) -> List[Dict[str, Any]]:
        """Convert BookOffers entries to RLUSD-per-XRP price and XRP size.

        Applies plausibility filter for ghost/inverted offers. Preserves account
        for CompetitorIntelProvider / peer-lane scraping on the WS path.
        """
        normalized: List[Dict[str, Any]] = []
        for offer in offers:
            gets = offer.get("TakerGets") or offer.get("taker_gets")
            pays = offer.get("TakerPays") or offer.get("taker_pays")
            if gets is None or pays is None:
                continue

            price, size_xrp = self._book_offer_price_and_size(gets, pays)
            if price is None or price <= 0 or size_xrp <= 0:
                continue
            if not is_plausible_rlusd_per_xrp(price):
                continue

            # Preserve account for competitor scraping / intelligence
            acct = self._offer_field(offer, "Account", "account", "Owner") or "unknown"
            normalized.append({
                "price": price,
                "size": size_xrp,
                "side": side,
                "account": acct
            })
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
        # Crossed book: do not use a lone ask as mid (inflates portfolio / false drawdown).
        if is_book_crossed(best_bid, best_ask):
            logger.warning(
                "Order book crossed or stale (bid=%.6f ask=%.6f); mid unavailable this cycle.",
                best_bid,
                best_ask,
            )
            return None
        return (best_bid + best_ask) / 2.0

    def _sanitize_book(
        self, book: Dict[str, List[Dict[str, float]]]
    ) -> Dict[str, List[Dict[str, float]]]:
        """Light post-filter to drop internally crossed or ghost-like levels.

        Helps when raw BookOffers still surfaces an ask below the bid side after
        normalization (inversion/ghost ask cases). Keeps the spirit of the 5%
        crossed tolerance used for mids.
        """
        bids = list(book.get("bids", []))
        asks = list(book.get("asks", []))
        if not bids or not asks:
            return {"bids": bids, "asks": asks}

        max_bid = max(b["price"] for b in bids)
        # Drop asks that are at or below the best bid (with tiny tolerance for fp).
        # This removes ghost asks that would invert the book for edge calc.
        asks = [a for a in asks if a["price"] > max_bid * 0.999]

        # Also drop any bids above the new best ask (symmetric, rare).
        if asks:
            min_ask = min(a["price"] for a in asks)
            bids = [b for b in bids if b["price"] < min_ask * 1.001]

        return {"bids": bids, "asks": asks}

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
