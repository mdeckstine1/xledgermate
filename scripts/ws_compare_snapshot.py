"""Print production WS runtime vs optional lab export side-by-side."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _presence(runtime: dict) -> tuple[float | None, int]:
    hist = runtime.get("sample_history") or []
    if hist:
        quoted = sum(
            1
            for row in hist
            if row.get("would_quote") or row.get("zero_quote_reason") == "quoted"
        )
        return round(100.0 * quoted / len(hist), 1), len(hist)
    pct = runtime.get("as_presence_pct")
    return (float(pct) if pct is not None else None), int(runtime.get("sample_count") or 0)


def _is_ws_production(runtime: dict) -> bool:
    return (
        runtime.get("price_source") == "ws_book_feed"
        or runtime.get("as_mode") == "pure"
        or bool(runtime.get("ws_as_version"))
    )


def main() -> int:
    production = _load(ROOT / "logs" / "runtime_state.json")
    lab = _load(ROOT / "logs" / "ws_as_demo_runtime.json")

    print("=== WS runtime side-by-side ===")
    print(f"Production updated: {production.get('updated_utc', 'n/a')}")
    lab_hist = lab.get("sample_history") or [{}]
    print(f"Lab last sample:    {lab_hist[-1].get('ts_utc', 'n/a')}")
    print()

    print("--- Production (ws-engine SSOT) ---")
    print(f"  ws_as_version:     {production.get('ws_as_version', '—')}")
    print(f"  price_source:      {production.get('price_source', '—')}")
    print(f"  as_mode:           {production.get('as_mode', '—')}")
    print(f"  zero_quote_reason: {production.get('zero_quote_reason', '—')}")
    print(f"  book_spread_pct:   {production.get('book_spread_pct')}")
    print(f"  ws_book_age_s:     {production.get('ws_book_age_s')}")
    sp, sn = _presence(production)
    print(f"  presence:          {sp}% ({sn} samples)")
    print(f"  open_offers:       {production.get('open_offers_count', '—')}")
    print()

    print("--- Lab export (live_pure_as_tester / dry-run) ---")
    print(f"  ws_as_version:     {lab.get('ws_as_version')}")
    print(f"  zero_quote_reason: {lab.get('zero_quote_reason')}")
    print(f"  as_reservation:    {lab.get('as_reservation')}")
    print(f"  ws_book_age_s:     {lab.get('ws_book_age_s')}")
    print(f"  dry_run open:      {lab.get('open_offers_count')}")
    wp, wn = _presence(lab)
    print(f"  presence:          {wp}% ({wn} samples)")
    print()

    print("--- Headline ---")
    prod_quote = production.get("zero_quote_reason") == "quoted" or production.get("would_quote")
    lab_quote = lab.get("would_quote") or lab.get("zero_quote_reason") == "quoted"
    print(f"  Production would quote: {'YES' if prod_quote else 'NO'}  |  Lab would quote: {'YES' if lab_quote else 'NO'}")
    if sp is not None and wp is not None:
        print(f"  Presence delta:  {sp}% -> {wp}% ({wp - sp:+.1f} pts)")
    if production and not _is_ws_production(production):
        print("  WARNING: runtime_state.json does not look like ws-engine output (legacy poll?)")

    return 0 if (production or lab) else 1


if __name__ == "__main__":
    raise SystemExit(main())
