"""Quick OHLC SQLite health dump (run on VPS: .venv/bin/python scripts/_ohlc_status_quick.py)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from alpha.decision.ohlc_cache import _connect, _db_path, _init_schema, cache_status
from alpha.decision.ta_config import effective_ta_candle_interval_seconds
from config.settings import BotConfig


def main() -> None:
    cfg = BotConfig.load()
    ta = effective_ta_candle_interval_seconds(
        cfg.alpha_technical_analysis,
        cycle_seconds=cfg.alpha_cycle_interval_seconds,
        sample_interval_seconds=cfg.alpha_price_sample_interval_seconds,
    )
    logs = Path("logs")
    st = cache_status(logs, ta_interval_seconds=ta)
    print("=== OHLC cache_status ===")
    print(json.dumps(st, indent=2))

    path = _db_path(logs)
    if path.is_file():
        print(f"\ndb_path: {path}  size_kb: {path.stat().st_size / 1024:.1f}")
    else:
        print("\ndb_path: missing")
        return

    with _connect(path) as conn:
        _init_schema(conn)
        print("\n=== meta ===")
        for row in conn.execute("SELECT key, value FROM meta ORDER BY key"):
            print(f"  {row[0]}: {row[1]}")

        print(f"\n=== TA interval {ta}s — last 5 bars ===")
        rows = conn.execute(
            """
            SELECT bar_open_ts, is_complete, tick_count, open, close
            FROM ohlc_bars WHERE interval_sec=?
            ORDER BY bar_open_ts DESC LIMIT 5
            """,
            (ta,),
        ).fetchall()
        for r in rows:
            ts = datetime.fromtimestamp(int(r[0]), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            print(f"  {ts}  complete={r[1]}  ticks={r[2]}  o={r[3]:.6f}  c={r[4]:.6f}")


if __name__ == "__main__":
    main()
