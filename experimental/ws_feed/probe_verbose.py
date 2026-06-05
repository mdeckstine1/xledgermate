from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def classify_ws_message(message: Dict[str, Any]) -> str:
    """Short label for rippled WebSocket frames (for counts and verbose lines)."""
    msg_type = str(message.get("type") or "unknown")
    if msg_type == "transaction":
        from experimental.ws_feed.book_messages import _transaction_body

        tx = _transaction_body(message)
        if tx:
            return f"transaction:{tx.get('TransactionType') or tx.get('transaction_type') or '?'}"
        return "transaction:no_body"
    if msg_type == "response":
        result = message.get("result") or {}
        if isinstance(result, dict) and result.get("offers"):
            return "response:book_snapshot"
        status = message.get("status") or (result.get("status") if isinstance(result, dict) else None)
        return f"response:{status or 'ok'}"
    if msg_type == "ledgerClosed":
        return "ledgerClosed"
    if msg_type == "error":
        return f"error:{message.get('error', 'unknown')}"
    return msg_type


@dataclass
class WsProbeStats:
    """Aggregates WS traffic during a probe run."""

    counts: Dict[str, int] = field(default_factory=dict)
    total_frames: int = 0
    book_apply_events: int = 0
    offers_extracted: int = 0
    started_monotonic: float = field(default_factory=time.monotonic)
    last_http_mid: Optional[float] = None
    last_http_at: float = 0.0

    def record_frame(self, message: Dict[str, Any], *, offers_applied: int) -> str:
        label = classify_ws_message(message)
        self.counts[label] = self.counts.get(label, 0) + 1
        self.total_frames += 1
        if offers_applied:
            self.book_apply_events += 1
            self.offers_extracted += offers_applied
        return label

    def elapsed_s(self) -> float:
        return time.monotonic() - self.started_monotonic

    def top_types(self, n: int = 8) -> str:
        items = sorted(self.counts.items(), key=lambda x: -x[1])[:n]
        return ", ".join(f"{k}={v}" for k, v in items) if items else "(none)"

    def log_summary(
        self,
        *,
        ws_bid: Optional[float],
        ws_ask: Optional[float],
        ws_mid: Optional[float],
        ws_age_s: float,
        ws_state_msgs: int,
        prefix: str = "[WS summary]",
    ) -> None:
        http_mid = self.last_http_mid
        drift_bps = None
        if ws_mid and http_mid and http_mid > 0:
            drift_bps = (ws_mid - http_mid) / http_mid * 10000.0
        drift_s = (
            f"{drift_bps:+.1f} bps vs HTTP"
            if drift_bps is not None
            else "no HTTP mid yet"
        )
        logger.info(
            "%s t=%.0fs frames=%s book_apply=%s offers=%s | WS mid=%s age=%.1fs state_msgs=%s | HTTP mid=%s | %s | types: %s",
            prefix,
            self.elapsed_s(),
            self.total_frames,
            self.book_apply_events,
            self.offers_extracted,
            f"{ws_mid:.6f}" if ws_mid else "—",
            ws_age_s,
            ws_state_msgs,
            f"{http_mid:.6f}" if http_mid else "—",
            drift_s,
            self.top_types(),
        )


def log_verbose_frame(
    stats: WsProbeStats,
    *,
    label: str,
    offers_applied: int,
    ws_mid: Optional[float],
    ws_age_s: float,
) -> None:
    """One line per WebSocket frame when --verbose is on."""
    logger.info(
        "[WS #%s] %s offers_applied=%s mid=%s age=%.1fs | running: %s",
        stats.total_frames,
        label,
        offers_applied,
        f"{ws_mid:.6f}" if ws_mid else "—",
        ws_age_s,
        stats.top_types(5),
    )