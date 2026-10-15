"""Bounded JSONL tail — never slurp a multi-hundred-MB log into RAM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

_DEFAULT_MAX_BYTES = 8 * 1024 * 1024


def tail_lines(
    path: Path,
    limit: int,
    *,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> List[str]:
    """Return the last `limit` non-empty lines without reading the whole file."""
    if limit <= 0 or not path.is_file():
        return []
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size <= 0:
        return []
    cap = max(65536, int(max_bytes))
    to_read = min(size, min(cap, max(65536, limit * 256)))
    data = b""
    try:
        with path.open("rb") as handle:
            while True:
                handle.seek(-to_read, 2)
                data = handle.read(to_read)
                if data.count(b"\n") >= limit + 1 or to_read >= size or to_read >= cap:
                    break
                to_read = min(size, cap, to_read * 2)
            if to_read < size:
                nl = data.find(b"\n")
                if 0 <= nl < len(data) - 1:
                    data = data[nl + 1 :]
    except OSError:
        return []
    text = data.decode("utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-limit:]


def tail_json_objects(
    path: Path,
    limit: int,
    *,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for line in tail_lines(path, limit, max_bytes=max_bytes):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out
