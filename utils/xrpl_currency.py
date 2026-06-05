"""XRPL issued-currency code helpers."""

from xrpl.utils import str_to_hex

# Official RLUSD representation on XRPL (40-char hex currency code).
RLUSD_CURRENCY_HEX = "524C555344000000000000000000000000000000"

RLUSD_ISSUER_MAINNET = "rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De"
RLUSD_ISSUER_TESTNET = "rQhWct2fv4Vc4KRjRgMrxa8xPN9Zx9iLKV"


def encode_currency_code(symbol: str) -> str:
    """Encode a currency symbol for XRPL IssuedCurrencyAmount."""
    symbol = (symbol or "").strip().upper()
    if len(symbol) == 3 and symbol.isalnum():
        return symbol
    hex_code = str_to_hex(symbol).upper()
    return hex_code.ljust(40, "0")


def resolve_rlusd_currency_code(currency: str) -> str:
    """On-ledger RLUSD code for BookOffers / IssuedCurrencyAmount (not display name 'RLUSD')."""
    symbol = (currency or "").strip().upper()
    if symbol in {"RLUSD", RLUSD_CURRENCY_HEX} or symbol.startswith("524C555344"):
        return RLUSD_CURRENCY_HEX
    return encode_currency_code(currency)
