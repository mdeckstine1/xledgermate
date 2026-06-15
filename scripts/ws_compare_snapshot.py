"""Print sacred vs WS demo runtime side-by-side (D3 terminal view)."""
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


def main() -> int:
    sacred = _load(ROOT / "logs" / "runtime_state.json")
    ws = _load(ROOT / "logs" / "ws_as_demo_runtime.json")

    print("=== D3 Side-by-side snapshot ===")
    print(f"Sacred updated: {sacred.get('updated_utc', 'n/a')}")
    ws_hist = ws.get("sample_history") or [{}]
    print(f"WS last sample:  {ws_hist[-1].get('ts_utc', 'n/a')}")
    print()

    print("--- Sacred (VPS path) ---")
    print(f"  profile:           {sacred.get('active_profile')}")
    print(f"  market_edge_met:   {sacred.get('market_edge_met')}")
    print(f"  zero_quote_reason: {sacred.get('zero_quote_reason', '—')}")
    print(f"  book_spread_pct:   {sacred.get('book_spread_pct')}")
    sp, sn = _presence(sacred)
    print(f"  presence:          {sp}% ({sn} samples)")
    print(f"  open_offers:       {sacred.get('open_offers_count', '—')}")
    print()

    print("--- WS + Pure A-S (lab) ---")
    print(f"  ws_as_version:     {ws.get('ws_as_version')}")
    print(f"  market_edge_met:   {ws.get('market_edge_met')}")
    print(f"  zero_quote_reason: {ws.get('zero_quote_reason')}")
    print(f"  as_reservation:    {ws.get('as_reservation')}")
    print(f"  ws_book_age_s:     {ws.get('ws_book_age_s')}")
    print(f"  dry_run open:      {ws.get('open_offers_count')}")
    wp, wn = _presence(ws)
    print(f"  presence:          {wp}% ({wn} samples)")
    print()

    print("--- Swap preview headline ---")
    se = sacred.get("market_edge_met", True)
    wq = ws.get("market_edge_met", True) or ws.get("zero_quote_reason") == "quoted"
    print(f"  Sacred edge met: {'YES' if se else 'NO'}  |  WS would quote: {'YES' if wq else 'NO'}")
    if sp is not None and wp is not None:
        print(f"  Presence delta:  {sp}% -> {wp}% ({wp - sp:+.1f} pts)")

    return 0 if (sacred or ws) else 1


if __name__ == "__main__":
    raise SystemExit(main())
