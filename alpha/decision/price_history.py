"""Multi-series price history for Alpha directional / price-action analysis."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

PRICE_HISTORY_PATH = Path("logs/alpha_price_history.json")
LEGACY_MID_HISTORY_PATH = Path("logs/alpha_mid_history.json")
VALID_PRICE_SOURCES = frozenset({"bid", "ask", "mid", "last"})
_MAX_SAMPLES = 480  # ~2h at 15s sampling
_PRICE_EPS = 1e-9


@dataclass(frozen=True)
class BookPrices:
    bid: Optional[float]
    ask: Optional[float]
    mid: Optional[float]
    last: Optional[float] = None


def normalize_price_source(source: str, *, default: str = "ask") -> str:
    key = (source or default).strip().lower()
    if key not in VALID_PRICE_SOURCES:
        logger.warning("price_source_invalid | source=%s | default=%s", source, default)
        return default
    return key


def resolve_book_price(prices: BookPrices, source: str) -> Optional[float]:
    """Pick executable reference price from a book snapshot."""
    src = normalize_price_source(source)
    if src == "bid":
        val = prices.bid
    elif src == "ask":
        val = prices.ask
    elif src == "mid":
        val = prices.mid
    else:
        val = prices.last if prices.last and prices.last > 0 else prices.ask or prices.mid
    if val is None or val <= 0:
        return None
    return float(val)


def book_prices_from_snapshot(book: object) -> BookPrices:
    """Build ``BookPrices`` from ``OrderBookSnapshot`` or duck-typed book."""
    return BookPrices(
        bid=getattr(book, "best_bid", None),
        ask=getattr(book, "best_ask", None),
        mid=getattr(book, "mid", None),
        last=None,
    )


def effective_sample_seconds(cycle_seconds: int, sample_interval_seconds: int) -> int:
    """Seconds between history points (sub-cycle sampling when configured)."""
    cycle = max(1, int(cycle_seconds))
    if sample_interval_seconds <= 0:
        return cycle
    return max(1, min(int(sample_interval_seconds), cycle))


def _empty_store() -> Dict[str, List[float]]:
    return {"bid": [], "ask": [], "mid": [], "last": []}


def _align_series_lengths(store: Dict[str, List[float]]) -> Dict[str, List[float]]:
    """Pad bid/ask/last prefix from mid so directional sources inherit migrated history."""
    mid = store.get("mid", [])
    if not mid:
        return store
    n_mid = len(mid)
    for key in ("bid", "ask", "last"):
        series = list(store.get(key, []))
        if len(series) >= n_mid:
            continue
        pad_count = n_mid - len(series)
        pad = mid[:pad_count]
        if key == "ask":
            pad = [m * 1.00015 for m in pad]
        elif key == "bid":
            pad = [m * 0.99985 for m in pad]
        store[key] = pad + series
    return store


def _load_store(path: Path = PRICE_HISTORY_PATH) -> Dict[str, List[float]]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("samples"), dict):
                store = _empty_store()
                for key in store:
                    raw = data["samples"].get(key, [])
                    if isinstance(raw, list):
                        store[key] = [float(x) for x in raw if float(x) > 0][-_MAX_SAMPLES:]
                aligned = _align_series_lengths(store)
                if (
                    path.exists()
                    and len(aligned.get("ask", [])) > len(store.get("ask", []))
                ):
                    _save_store(aligned, path)
                return aligned
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
    return _align_series_lengths(_migrate_legacy_mid_history(path))


def _migrate_legacy_mid_history(path: Path) -> Dict[str, List[float]]:
    """Import ``alpha_mid_history.json`` mids into the mid series once."""
    store = _empty_store()
    legacy = LEGACY_MID_HISTORY_PATH
    if not legacy.exists():
        return store
    try:
        data = json.loads(legacy.read_text(encoding="utf-8"))
        mids = data.get("mids", [])
        if isinstance(mids, list):
            store["mid"] = [float(x) for x in mids if float(x) > 0][-_MAX_SAMPLES:]
            store["ask"] = [m * 1.00015 for m in store["mid"]]
            store["bid"] = [m * 0.99985 for m in store["mid"]]
            logger.info("price_history_migrated | legacy_mids=%d", len(store["mid"]))
            _save_store(_align_series_lengths(store), path)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        pass
    return store


def _save_store(store: Dict[str, List[float]], path: Path = PRICE_HISTORY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "samples": {key: store[key][-_MAX_SAMPLES:] for key in _empty_store()},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_book_prices(
    prices: BookPrices,
    *,
    path: Path = PRICE_HISTORY_PATH,
) -> None:
    """Append bid/ask/mid (and last when set) to rolling price history."""
    store = _load_store(path)
    if prices.bid and prices.bid > 0:
        store["bid"].append(float(prices.bid))
    if prices.ask and prices.ask > 0:
        store["ask"].append(float(prices.ask))
    if prices.mid and prices.mid > 0:
        store["mid"].append(float(prices.mid))
    if prices.last and prices.last > 0:
        store["last"].append(float(prices.last))
    for key in store:
        store[key] = store[key][-_MAX_SAMPLES:]
    _save_store(_align_series_lengths(store), path)


def load_price_series(
    source: str,
    *,
    path: Path = PRICE_HISTORY_PATH,
    default: str = "ask",
) -> List[float]:
    """Load a price series; ``last`` falls back to ask then mid when empty."""
    src = normalize_price_source(source, default=default)
    store = _load_store(path)
    series = list(store.get(src, []))
    if series:
        return series
    if src == "last":
        for fallback in ("ask", "mid", "bid"):
            series = store.get(fallback, [])
            if series:
                return list(series)
    return []


def load_mid_history(path: Path = PRICE_HISTORY_PATH) -> List[float]:
    """Backward-compatible accessor — mid series from price history."""
    legacy = path
    if path.name == "alpha_mid_history.json":
        legacy = PRICE_HISTORY_PATH
    return load_price_series("mid", path=legacy)


def record_mid(mid: float, *, path: Path = PRICE_HISTORY_PATH) -> None:
    """Backward-compatible single-mid append."""
    if mid <= 0:
        return
    store = _load_store(path)
    store["mid"].append(float(mid))
    store["mid"] = store["mid"][-_MAX_SAMPLES:]
    _save_store(store, path)


def build_candle_from_prices(prices: Sequence[float]) -> Optional["CandleData"]:
    from alpha.decision.structure import CandleData

    clean = [float(p) for p in prices if float(p) > 0]
    if len(clean) < 2:
        return None
    return CandleData(
        open=clean[0],
        high=max(clean),
        low=min(clean),
        close=clean[-1],
    )
