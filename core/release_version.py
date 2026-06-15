"""Release version helpers — read from disk on each call (safe after git pull + restart)."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = _REPO_ROOT / "VERSION"
WS_AS_VERSION_FILE = _REPO_ROOT / "experimental/ws_feed/WS_AS_VERSION"


def read_version_file(path: Path) -> str:
    if not path.exists():
        return "0.0.0"
    return path.read_text(encoding="utf-8").strip()


def current_project_version() -> str:
    return read_version_file(VERSION_FILE)


def current_ws_path_version() -> str:
    from experimental.ws_feed.pure_quote_path import current_ws_as_version

    return current_ws_as_version()


def versions_in_sync() -> bool:
    return current_project_version() == read_version_file(WS_AS_VERSION_FILE)


def version_summary() -> dict[str, str]:
    proj = current_project_version()
    ws = read_version_file(WS_AS_VERSION_FILE)
    return {
        "project_version": proj,
        "ws_as_version": ws,
        "in_sync": str(proj == ws).lower(),
    }
