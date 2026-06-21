"""Shared helpers for layered QD HUD reports."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple


def fmt_bool(value: Any, *, yes: str = "yes", no: str = "no") -> str:
    if value is True or value == "true":
        return yes
    if value is False or value == "false":
        return no
    return str(value) if value not in (None, "") else "—"


def fmt_on_off(value: Any) -> str:
    if value is True or value == "true":
        return "ON"
    if value is False or value == "false":
        return "OFF"
    return "?"


def operating_mode(
    *,
    intent: str,
    book_mode: str,
    solo_mode: bool,
    bid_allowed: Any,
    ask_allowed: Any,
    protection_active: bool = False,
    would_quote: Any = None,
) -> Tuple[str, str]:
    """
    Return (mode_label, one_line_hint) for acquisition-centered monitoring.
    """
    intent_l = (intent or "").lower()
    book = (book_mode or "").lower()
    bid_on = bid_allowed is True or bid_allowed == "true"
    ask_on = ask_allowed is True or ask_allowed == "true"

    if protection_active:
        return "PROTECT · BLEED", "Layer 4 bleed protection active — side-local pause"

    if "accumulate" in intent_l and book == "solo":
        if bid_on:
            return "ACCUMULATING · SOLO", "SOLO_ACCUMULATE_ON_EDGE — bid ON, acquiring on edge"
        return "ACCUMULATE · BLOCKED", "Accumulate intent but L5 bid OFF — check edge gate / bleed"

    if intent_l == "inventory_unload":
        if not bid_on and not ask_on:
            return "TRIM · IDLE", "INVENTORY_UNLOAD trim — no edge, both sides OFF (expected on solo)"
        return "TRIM · ACTIVE", "INVENTORY_UNLOAD — unloading via favored side"

    if bid_on or ask_on:
        quoting = fmt_on_off(would_quote).lower() if would_quote is not None else "?"
        return "QUOTING", f"L5 permissions allow quoting · would_quote={quoting}"

    if intent_l == "patient_solo":
        return "PATIENT · SOLO", "Waiting for viable edge on solo book"

    if intent_l == "hold_off":
        return "HOLD OFF", "Strategy hold — no quoting"

    return "IDLE · BLOCKED", "No side permitted this cycle"


def intent_mix_compact(summary: Mapping[str, Any]) -> str:
    if not summary:
        return ""
    intents = summary.get("intent_counts") or {}
    if not intents:
        return ""
    total = summary.get("total") or 0
    parts = []
    for key, label in (
        ("solo_accumulate_on_edge", "accum"),
        ("inventory_unload", "trim"),
        ("two_sided_skim", "skim"),
        ("patient_solo", "patient"),
    ):
        if intents.get(key):
            pct = 100.0 * intents[key] / total if total else 0
            parts.append(f"{label}={intents[key]} ({pct:.0f}%)")
    return " · ".join(parts)


def side_permission_block(
    side: str,
    *,
    allowed: Any,
    pause_cause: str,
    block_reason: str,
    edge_viable: Any,
    edge_bps: Any,
    bleeding: Any,
    size_mult: Optional[float] = None,
) -> list[str]:
    label = side.upper()
    lines = [
        f"  [{label}] allowed: {fmt_on_off(allowed)}"
        + (f"  ← cause: {pause_cause}" if pause_cause and not (allowed is True or allowed == "true") else ""),
    ]
    edge_txt = f"{float(edge_bps):.1f} bps" if edge_bps is not None else "—"
    lines.append(f"       edge: viable={fmt_bool(edge_viable)} @ {edge_txt}")
    if size_mult is not None:
        lines.append(f"       size_mult: ×{size_mult:.2f}")
    if bleeding:
        lines.append(f"       bleed: ACTIVE")
    if block_reason and block_reason != "—" and not (allowed is True or allowed == "true"):
        lines.append(f"       block: {block_reason}")
    return lines
