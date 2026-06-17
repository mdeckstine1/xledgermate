"""F1 — operator-only competitor nicknames (local JSON; not on-chain)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional

NICKNAMES_PATH = Path("logs/competitor_nicknames.json")


def load_nicknames(path: Optional[Path] = None) -> Dict[str, str]:
    p = path or NICKNAMES_PATH
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: Dict[str, str] = {}
    for key, val in data.items():
        addr = str(key or "").strip()
        nick = str(val or "").strip()
        if addr.startswith("r") and nick:
            out[addr] = nick
    return out


def save_nicknames(
    mapping: Mapping[str, str],
    *,
    path: Optional[Path] = None,
) -> Dict[str, str]:
    p = path or NICKNAMES_PATH
    cleaned: Dict[str, str] = {}
    for key, val in mapping.items():
        addr = str(key or "").strip()
        nick = str(val or "").strip()
        if addr.startswith("r") and nick:
            cleaned[addr] = nick
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cleaned, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass
    return cleaned


def set_nickname(
    address: str,
    nickname: str,
    *,
    path: Optional[Path] = None,
) -> Dict[str, str]:
    addr = (address or "").strip()
    nick = (nickname or "").strip()
    if not addr.startswith("r"):
        raise ValueError("address must be an r-address")
    if not nick:
        raise ValueError("nickname required")
    current = load_nicknames(path=path)
    current[addr] = nick
    return save_nicknames(current, path=path)


def remove_nickname(address: str, *, path: Optional[Path] = None) -> Dict[str, str]:
    addr = (address or "").strip()
    current = load_nicknames(path=path)
    current.pop(addr, None)
    return save_nicknames(current, path=path)


def resolve_nickname(address: str, nicknames: Optional[Mapping[str, str]] = None) -> Optional[str]:
    addr = (address or "").strip()
    if not addr:
        return None
    mapping = nicknames if nicknames is not None else load_nicknames()
    if addr in mapping:
        return mapping[addr]
    for key, val in mapping.items():
        if addr.startswith(key) or key.startswith(addr):
            return val
    return None


def apply_nicknames_to_profiles(
    rows: Optional[List[Dict[str, Any]]],
    nicknames: Optional[Mapping[str, str]] = None,
) -> List[Dict[str, Any]]:
    if not rows:
        return []
    mapping = nicknames if nicknames is not None else load_nicknames()
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        full = str(item.get("account_full") or item.get("account") or "").strip()
        nick = resolve_nickname(full, mapping)
        if nick:
            item["nickname"] = nick
        out.append(item)
    return out
