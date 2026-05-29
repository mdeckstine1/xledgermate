"""Derive XRPL wallets from bot secrets (family seed or Xaman sn... encoding)."""

from __future__ import annotations

from xrpl.constants import CryptoAlgorithm
from xrpl.wallet import Wallet


def bot_secret_algorithm(secret: str) -> CryptoAlgorithm:
    """Match xrpl-py Wallet inference: sEd* → Ed25519, else secp256k1 (Xaman sn..., legacy s...)."""
    if secret.strip().startswith("sEd"):
        return CryptoAlgorithm.ED25519
    return CryptoAlgorithm.SECP256K1


def wallet_from_bot_secret(secret: str) -> Wallet:
    secret = (secret or "").strip()
    if not secret:
        raise ValueError("Bot secret is empty.")
    return Wallet.from_seed(seed=secret, algorithm=bot_secret_algorithm(secret))


def secret_matches_address(secret: str, address: str) -> tuple[bool, str]:
    """Return (match, derived_classic_address_or_error_detail)."""
    address = (address or "").strip()
    secret = (secret or "").strip()
    if not address or not secret:
        return False, "Enter both address and secret (family seed s... or Xaman sn...)."
    try:
        derived = wallet_from_bot_secret(secret).classic_address
    except Exception as exc:
        return False, f"Invalid secret: {exc}"
    if derived == address:
        return True, derived
    return False, f"Secret derives to `{derived}`, not `{address}`."
