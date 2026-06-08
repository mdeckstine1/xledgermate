#!/usr/bin/env python3
"""
Lightweight real-time HUD for the WS + pure A-S strategy (committed future path).

Run standalone or integrated with live_pure_as_tester.

Provides a simple web UI (HTML + JS polling) showing:
- Live book (bid/ask/mid/spread from WS BookState)
- WS freshness (age, message count)
- Pure A-S decision in real time (reservation, optimal spread, suggested levels)
- Whether it would quote right now (2 or 0)
- Last decision note (rich policy string + PURE A-S math)
- Recent decisions

This is the "new GUI" surface for watching the strategy react to real WS book data
at high frequency, while the main Streamlit remains the deep analytical dashboard.

Usage from live tester:
  python -m experimental.ws_feed.live_pure_as_tester --serve-hud

Or run the HUD directly and feed it state via the /state POST (for future engine integration).

Requires: fastapi, uvicorn (pip install fastapi uvicorn)
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse
    import uvicorn
except ImportError:
    FastAPI = None
    uvicorn = None

# Global current state (updated by the live tester or engine)
_current_state: Dict[str, Any] = {
    "mid": None,
    "best_bid": None,
    "best_ask": None,
    "book_spread_pct": None,
    "ws_age_s": None,
    "ws_message_count": 0,
    "as_reservation": None,
    "as_optimal_spread_pct": None,
    "as_gamma": None,
    "as_kappa": None,
    "suggested_bid": None,
    "suggested_ask": None,
    "would_quote": False,
    "last_note": "Waiting for first WS update + A-S decision...",
    "recent_notes": [],
    "as_mode": "pure",
}

_recent_limit = 20

app = FastAPI(title="WS + Pure A-S Real-Time HUD") if FastAPI else None

if app:
    _HUD_DIR = Path(__file__).parent / "hud"
    _INDEX_HTML = _HUD_DIR / "index.html"

    @app.get("/", response_class=HTMLResponse)
    async def index():
        if not _INDEX_HTML.exists():
            return HTMLResponse("<h1>index.html not found in hud/ — run from correct cwd or restore the file</h1>", status_code=500)
        html = _INDEX_HTML.read_text(encoding="utf-8")
        resp = HTMLResponse(html)
        resp.headers["Content-Security-Policy"] = "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline';"
        return resp










    @app.get("/state")
    async def get_state():
        return _current_state

    @app.post("/state")
    async def post_state(request: Request):
        global _current_state
        data = await request.json()
        _current_state.update(data)
        # keep recent list bounded
        if "recent_notes" not in _current_state:
            _current_state["recent_notes"] = []
        if data.get("last_note"):
            _current_state["recent_notes"].insert(0, data["last_note"][:180])
            _current_state["recent_notes"] = _current_state["recent_notes"][:_recent_limit]
        return {"ok": True}


def update_state(new_state: Dict[str, Any]):
    """Call this from the live tester / engine on every decision cycle."""
    global _current_state
    _current_state.update(new_state)
    if "recent_notes" not in _current_state:
        _current_state["recent_notes"] = []
    if new_state.get("last_note"):
        _current_state["recent_notes"].insert(0, new_state["last_note"][:180])
        _current_state["recent_notes"] = _current_state["recent_notes"][:_recent_limit]


def run_hud(host: str = "127.0.0.1", port: int = 8765, background: bool = True):
    """Start the HUD server. Set background=False to block."""
    if FastAPI is None or uvicorn is None:
        print("FastAPI / uvicorn not installed. Run: pip install fastapi uvicorn")
        return None

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    if background:
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        print(f"[HUD] Real-time A-S HUD available at http://{host}:{port}")
        print("   (Open in browser — it polls /state every ~800ms for live book + A-S decisions)")
        print("   IMPORTANT: After editing hud/index.html (or this file) you MUST restart the tester process.")
        return server
    else:
        print(f"[HUD] Starting real-time A-S HUD on http://{host}:{port}")
        server.run()
        return server


if __name__ == "__main__":
    run_hud(background=False)
