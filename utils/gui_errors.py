"""Small GUI error formatters (no XRPL connector imports — safe during partial module loads)."""

from __future__ import annotations


def format_ledger_sync_error(exc: BaseException) -> str:
    """Human-readable message for XRPL / asyncio failures in the GUI."""
    if isinstance(exc, dict):
        detail = exc.get("error") or exc.get("currency") or exc.get("message")
        return str(detail) if detail else "Ledger request failed."
    text = str(exc).strip()
    if "Invalid currency RLUSD" in text or "'currency': 'Invalid currency RLUSD'" in text:
        return (
            "BookOffers rejected currency code RLUSD — use the on-ledger hex code "
            "(config maps RLUSD automatically; restart the GUI after updating)."
        )
    if len(text) > 400:
        return text[:400] + "…"
    return text or "Ledger sync failed."
