"""Project version metadata."""

from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"


def _read_version() -> str:
    if _VERSION_FILE.exists():
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
    return "0.0.0"


def current_version() -> str:
    """Read VERSION file each call — matches WS path after deploy + service restart."""
    return _read_version()


VERSION = _read_version()
