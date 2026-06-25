"""SQLite OHLC cache — persistent multi-TF bars with gap-tolerant restart."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from alpha.decision.price_history import (
    PRICE_HISTORY_PATH,
    effective_sample_seconds,
    load_price_series,
)
from alpha.decision.retention_policy import (
    CACHED_INTERVALS_SECONDS,
    OHLC_BARS_PER_TF,
    OHLC_DB_PATH,
    indicator_warmup_status,
)
from alpha.decision.structure import CandleData

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1
_EXTRA_INTERVALS: tuple[int, ...] = ()


def configure_ohlc_extra_intervals(*, intervals: Sequence[int]) -> None:
    """Register active TA bar width (e.g. 6900s) for live OHLC updates."""
    global _EXTRA_INTERVALS
    _EXTRA_INTERVALS = tuple(sorted({int(x) for x in intervals if int(x) > 0}))


def _active_intervals() -> tuple[int, ...]:
    seen = set(CACHED_INTERVALS_SECONDS)
    out = list(CACHED_INTERVALS_SECONDS)
    for sec in _EXTRA_INTERVALS:
        if sec not in seen:
            out.append(sec)
            seen.add(sec)
    return tuple(out)


def _db_path(logs_dir: Path) -> Path:
    return logs_dir / OHLC_DB_PATH


def _utc_ts(dt: Optional[datetime] = None) -> int:
    if dt is None:
        dt = datetime.now(tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _bar_open_ts(tick_ts: int, interval_sec: int) -> int:
    interval = max(1, int(interval_sec))
    return (int(tick_ts) // interval) * interval


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ohlc_bars (
            interval_sec INTEGER NOT NULL,
            bar_open_ts INTEGER NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            tick_count INTEGER NOT NULL DEFAULT 0,
            is_complete INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (interval_sec, bar_open_ts)
        );
        CREATE INDEX IF NOT EXISTS idx_ohlc_interval_ts
            ON ohlc_bars(interval_sec, bar_open_ts);
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
        (str(_SCHEMA_VERSION),),
    )
    conn.commit()


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
        (key, value),
    )


def _get_meta(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return str(row["value"]) if row else None


def _row_to_candle(row: sqlite3.Row) -> CandleData:
    return CandleData(
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        is_complete=bool(int(row["is_complete"])),
    )


def _close_elapsed_bars(
    conn: sqlite3.Connection,
    *,
    interval_sec: int,
    tick_ts: int,
) -> None:
    """Mark any bar whose period ended at or before ``tick_ts`` as complete."""
    interval = max(1, int(interval_sec))
    conn.execute(
        """
        UPDATE ohlc_bars
        SET is_complete=1
        WHERE interval_sec=?
          AND is_complete=0
          AND bar_open_ts + ? <= ?
        """,
        (interval, interval, int(tick_ts)),
    )


def _upsert_tick_bar(
    conn: sqlite3.Connection,
    *,
    interval_sec: int,
    bar_open: int,
    price: float,
    tick_ts: int,
) -> None:
    row = conn.execute(
        """
        SELECT open, high, low, close, tick_count, is_complete
        FROM ohlc_bars
        WHERE interval_sec=? AND bar_open_ts=?
        """,
        (interval_sec, bar_open),
    ).fetchone()

    if row is None:
        prev_open = int(bar_open) - int(interval_sec)
        if prev_open >= 0:
            conn.execute(
                """
                UPDATE ohlc_bars
                SET is_complete=1
                WHERE interval_sec=? AND bar_open_ts=? AND is_complete=0
                """,
                (interval_sec, prev_open),
            )
        conn.execute(
            """
            INSERT INTO ohlc_bars(
                interval_sec, bar_open_ts, open, high, low, close, tick_count, is_complete
            ) VALUES(?, ?, ?, ?, ?, ?, 1, 0)
            """,
            (interval_sec, bar_open, price, price, price, price),
        )
        return

    if int(row["is_complete"]):
        return

    high = max(float(row["high"]), price)
    low = min(float(row["low"]), price)
    conn.execute(
        """
        UPDATE ohlc_bars
        SET high=?, low=?, close=?, tick_count=tick_count+1
        WHERE interval_sec=? AND bar_open_ts=?
        """,
        (high, low, price, interval_sec, bar_open),
    )


def _trim_interval(conn: sqlite3.Connection, interval_sec: int) -> None:
    keep = max(2, int(OHLC_BARS_PER_TF))
    conn.execute(
        """
        DELETE FROM ohlc_bars
        WHERE interval_sec=?
          AND bar_open_ts NOT IN (
            SELECT bar_open_ts FROM ohlc_bars
            WHERE interval_sec=?
            ORDER BY bar_open_ts DESC
            LIMIT ?
          )
        """,
        (interval_sec, interval_sec, keep),
    )


def record_sample(
    price: float,
    *,
    logs_dir: Path,
    tick_ts: Optional[datetime] = None,
    intervals: Optional[Sequence[int]] = None,
) -> None:
    """Append one book sample to all cached OHLC series."""
    if price <= 0:
        return
    active = tuple(intervals) if intervals is not None else _active_intervals()
    ts = _utc_ts(tick_ts)
    path = _db_path(logs_dir)
    with _connect(path) as conn:
        _init_schema(conn)
        for interval_sec in active:
            bar_open = _bar_open_ts(ts, interval_sec)
            _close_elapsed_bars(conn, interval_sec=interval_sec, tick_ts=ts)
            _upsert_tick_bar(conn, interval_sec=interval_sec, bar_open=bar_open, price=price, tick_ts=ts)
            _trim_interval(conn, interval_sec)
        _set_meta(conn, "last_tick_ts", str(ts))
        _set_meta(conn, "last_tick_utc", datetime.fromtimestamp(ts, tz=timezone.utc).isoformat())
        conn.commit()


def get_candles(
    interval_sec: int,
    *,
    logs_dir: Path,
    limit: int = OHLC_BARS_PER_TF,
) -> List[CandleData]:
    path = _db_path(logs_dir)
    if not path.is_file():
        return []
    with _connect(path) as conn:
        _init_schema(conn)
        rows = conn.execute(
            """
            SELECT open, high, low, close, is_complete
            FROM ohlc_bars
            WHERE interval_sec=?
            ORDER BY bar_open_ts DESC
            LIMIT ?
            """,
            (int(interval_sec), max(1, int(limit))),
        ).fetchall()
    return [_row_to_candle(r) for r in reversed(rows)]


def _closed_bar_count(conn: sqlite3.Connection, interval_sec: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM ohlc_bars
        WHERE interval_sec=? AND is_complete=1
        """,
        (int(interval_sec),),
    ).fetchone()
    return int(row["n"]) if row else 0


def _total_bar_count(conn: sqlite3.Connection, interval_sec: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM ohlc_bars WHERE interval_sec=?",
        (int(interval_sec),),
    ).fetchone()
    return int(row["n"]) if row else 0


def rebuild_interval_from_ticks(
    prices: Sequence[float],
    *,
    interval_sec: int,
    sample_seconds: int,
    end_ts: Optional[int] = None,
    logs_dir: Path,
) -> int:
    """Rebuild one TF from tick series (gap-tolerant synthetic timestamps)."""
    clean = [float(p) for p in prices if float(p) > 0]
    if len(clean) < 2:
        return 0
    sample = max(1, int(sample_seconds))
    end = int(end_ts if end_ts is not None else _utc_ts())
    start = end - (len(clean) - 1) * sample

    bars: Dict[int, List[float]] = {}
    for i, price in enumerate(clean):
        tick_ts = start + i * sample
        bar_open = _bar_open_ts(tick_ts, interval_sec)
        bars.setdefault(bar_open, []).append(price)

    path = _db_path(logs_dir)
    with _connect(path) as conn:
        _init_schema(conn)
        conn.execute("DELETE FROM ohlc_bars WHERE interval_sec=?", (int(interval_sec),))
        ordered = sorted(bars.items())
        for idx, (bar_open, chunk) in enumerate(ordered):
            is_complete = 1 if idx < len(ordered) - 1 else 0
            conn.execute(
                """
                INSERT INTO ohlc_bars(
                    interval_sec, bar_open_ts, open, high, low, close, tick_count, is_complete
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(interval_sec),
                    int(bar_open),
                    chunk[0],
                    max(chunk),
                    min(chunk),
                    chunk[-1],
                    len(chunk),
                    is_complete,
                ),
            )
        _trim_interval(conn, int(interval_sec))
        conn.commit()
    return len(bars)


def rebuild_all_from_ticks(
    *,
    logs_dir: Path,
    price_source: str = "ask",
    history_path: Optional[Path] = None,
    cycle_seconds: int = 60,
    sample_interval_seconds: int = 15,
    intervals: Sequence[int] = CACHED_INTERVALS_SECONDS,
) -> Dict[int, int]:
    """Populate OHLC cache from tick JSON (restart / empty DB)."""
    hist = history_path or (logs_dir / PRICE_HISTORY_PATH.name)
    prices = load_price_series(price_source, path=hist)
    if len(prices) < 2:
        return {}
    sample = effective_sample_seconds(cycle_seconds, sample_interval_seconds)
    out: Dict[int, int] = {}
    for interval_sec in intervals:
        n = rebuild_interval_from_ticks(
            prices,
            interval_sec=interval_sec,
            sample_seconds=sample,
            logs_dir=logs_dir,
        )
        out[int(interval_sec)] = n
    with _connect(_db_path(logs_dir)) as conn:
        _init_schema(conn)
        _set_meta(conn, "rebuilt_from_ticks", datetime.now(tz=timezone.utc).isoformat())
        _set_meta(conn, "tick_count_at_rebuild", str(len(prices)))
        conn.commit()
    logger.info("ohlc_cache_rebuild | ticks=%d | bars=%s", len(prices), out)
    return out


def repair_incomplete_bars(
    logs_dir: Path,
    *,
    tick_ts: Optional[int] = None,
    intervals: Optional[Sequence[int]] = None,
) -> int:
    """Close bars whose period has ended (fixes stuck closed_bars after live-only updates)."""
    ts = int(tick_ts if tick_ts is not None else _utc_ts())
    active = tuple(intervals) if intervals is not None else _active_intervals()
    path = _db_path(logs_dir)
    closed = 0
    with _connect(path) as conn:
        _init_schema(conn)
        for interval_sec in active:
            before = _closed_bar_count(conn, interval_sec)
            _close_elapsed_bars(conn, interval_sec=interval_sec, tick_ts=ts)
            closed += _closed_bar_count(conn, interval_sec) - before
        conn.commit()
    return closed


def ensure_ohlc_cache(
    logs_dir: Path,
    *,
    price_source: str = "ask",
    history_path: Optional[Path] = None,
    cycle_seconds: int = 60,
    sample_interval_seconds: int = 15,
    ta_interval_seconds: int = 300,
) -> None:
    """On engine start: rebuild from ticks when DB or a TF is empty."""
    path = _db_path(logs_dir)
    with _connect(path) as conn:
        _init_schema(conn)
        need_rebuild = False
        for interval_sec in CACHED_INTERVALS_SECONDS:
            if _total_bar_count(conn, interval_sec) < 2:
                need_rebuild = True
                break

    if need_rebuild:
        rebuild_all_from_ticks(
            logs_dir=logs_dir,
            price_source=price_source,
            history_path=history_path,
            cycle_seconds=cycle_seconds,
            sample_interval_seconds=sample_interval_seconds,
        )

    if int(ta_interval_seconds) not in CACHED_INTERVALS_SECONDS:
        hist = history_path or (logs_dir / PRICE_HISTORY_PATH.name)
        prices = load_price_series(price_source, path=hist)
        with _connect(path) as conn:
            ta_bars = _total_bar_count(conn, int(ta_interval_seconds))
        if len(prices) >= 2 and ta_bars < 2:
            sample = effective_sample_seconds(cycle_seconds, sample_interval_seconds)
            rebuild_interval_from_ticks(
                prices,
                interval_sec=int(ta_interval_seconds),
                sample_seconds=sample,
                logs_dir=logs_dir,
            )
    configure_ohlc_extra_intervals(intervals=[int(ta_interval_seconds)])
    repair_incomplete_bars(
        logs_dir,
        intervals=_active_intervals(),
    )


def cache_status(
    logs_dir: Path,
    *,
    ta_interval_seconds: int,
) -> Dict[str, Any]:
    """HUD / report payload for OHLC health and gaps."""
    path = _db_path(logs_dir)
    if not path.is_file():
        return {
            "db_present": False,
            "last_tick_utc": None,
            "gap_seconds": None,
            "intervals": {},
            "indicator_warmup": indicator_warmup_status(0, interval_seconds=int(ta_interval_seconds)),
        }

    now = _utc_ts()
    with _connect(path) as conn:
        _init_schema(conn)
        last_tick_raw = _get_meta(conn, "last_tick_ts")
        last_tick_ts = int(last_tick_raw) if last_tick_raw else None
        gap_seconds = (now - last_tick_ts) if last_tick_ts else None
        closed = _closed_bar_count(conn, int(ta_interval_seconds))
        total = _total_bar_count(conn, int(ta_interval_seconds))
        last_tick_utc = _get_meta(conn, "last_tick_utc")
        rebuilt = _get_meta(conn, "rebuilt_from_ticks")
        intervals: Dict[str, Any] = {}
        for interval_sec in CACHED_INTERVALS_SECONDS:
            intervals[str(interval_sec)] = {
                "closed_bars": _closed_bar_count(conn, interval_sec),
                "total_bars": _total_bar_count(conn, interval_sec),
                "cap": OHLC_BARS_PER_TF,
            }
        key = str(int(ta_interval_seconds))
        if key not in intervals:
            intervals[key] = {
                "closed_bars": closed,
                "total_bars": total,
                "cap": OHLC_BARS_PER_TF,
            }

    warmup = indicator_warmup_status(closed, interval_seconds=int(ta_interval_seconds))
    return {
        "db_present": True,
        "last_tick_utc": last_tick_utc,
        "gap_seconds": gap_seconds,
        "ta_interval_seconds": int(ta_interval_seconds),
        "closed_bars": closed,
        "total_bars": total,
        "bars_cap": OHLC_BARS_PER_TF,
        "indicator_warmup": warmup,
        "intervals": intervals,
        "rebuilt_from_ticks": rebuilt,
    }
