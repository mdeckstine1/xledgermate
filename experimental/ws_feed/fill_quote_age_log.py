"""M6 live fill quote-age stream — append-only JSONL (`logs/fill_quote_age.jsonl`)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

FILL_QUOTE_AGE_PATH = Path("logs/fill_quote_age.jsonl")
RECENT_FILL_AGES_MAX = 20


def append_fill_quote_age_record(
    record: Dict[str, Any],
    *,
    path: Path = FILL_QUOTE_AGE_PATH,
) -> Dict[str, Any]:
    """Persist one M6 fill-age row (engine calls at detect-fill time)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(record)
    row.setdefault("kind", "fill")
    row.setdefault("ts_utc", datetime.now(tz=timezone.utc).isoformat())
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    return row


def build_fill_quote_age_record(
    *,
    cycle: int,
    side: str,
    offer_side: str,
    xrp_amount: float,
    quote_age_seconds: Optional[float],
    offer_sequence: Optional[int],
    ws_as_version: str,
    fills_session: int,
    capture_xrp: float,
    tracking: str,
) -> Dict[str, Any]:
    """Structured M6 fill-age event for JSONL + HUD."""
    return {
        "kind": "fill",
        "cycle": int(cycle),
        "side": (side or "").upper(),
        "offer_side": (offer_side or "").lower(),
        "xrp_amount": round(float(xrp_amount), 4),
        "quote_age_seconds": round(float(quote_age_seconds), 6) if quote_age_seconds is not None else None,
        "offer_sequence": int(offer_sequence) if offer_sequence is not None else None,
        "tracking": tracking,
        "ws_as_version": ws_as_version,
        "fills_session": int(fills_session),
        "capture_xrp": round(float(capture_xrp), 6),
    }


def tail_fill_quote_age_records(
    *,
    limit: int = 500,
    path: Path = FILL_QUOTE_AGE_PATH,
    since: Optional[datetime] = None,
    ws_as_version: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not path.exists() or limit <= 0:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: List[Dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or row.get("kind") != "fill":
            continue
        if ws_as_version and str(row.get("ws_as_version") or "") != ws_as_version:
            continue
        if since is not None:
            ts_raw = str(row.get("ts_utc") or "")
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < since:
                    continue
            except ValueError:
                pass
        out.append(row)
    return out[-limit:]


def push_recent_fill_age(
    buffer: List[Dict[str, Any]],
    record: Dict[str, Any],
    *,
    max_len: int = RECENT_FILL_AGES_MAX,
) -> List[Dict[str, Any]]:
    """Keep last N fill-age rows in engine memory for runtime/HUD."""
    buf = list(buffer)
    buf.append(record)
    if len(buf) > max_len:
        buf = buf[-max_len:]
    return buf
