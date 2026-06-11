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
    from fastapi.responses import HTMLResponse, Response
    import uvicorn
except ImportError:
    FastAPI = None
    uvicorn = None

# Optional QR support (real scannable PNGs for the Inventory tab)
# pillow is usually already present; we use it for nice fallback images too
try:
    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except Exception:
    HAS_PIL = False

try:
    import qrcode
    HAS_QRCODE = True
except Exception:
    HAS_QRCODE = False

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

    @app.get("/qr")
    async def qr_image(text: str = ""):
        """Return a real scannable QR PNG for an XRPL address (used by Inventory tab).
        Requires: pip install qrcode pillow (already done in this env).
        If not active, returns a visible placeholder image telling you to restart the tester.
        """
        if not text:
            text = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"  # safe default for demo

        def _make_placeholder(msg: str, sub: str = "") -> bytes:
            if not HAS_PIL:
                # last resort tiny png
                return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
            try:
                size = (220, 220)
                img = Image.new("RGB", size, color="#1e2937")
                draw = ImageDraw.Draw(img)
                # Try a default font; fall back to default
                try:
                    font = ImageFont.truetype("arial.ttf", 14)
                    small_font = ImageFont.truetype("arial.ttf", 11)
                except Exception:
                    font = ImageFont.load_default()
                    small_font = font
                # Center the message
                bbox = draw.textbbox((0, 0), msg, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                x = (size[0] - tw) // 2
                y = (size[1] - th) // 2 - 10
                draw.text((x, y), msg, fill="#e2e8f0", font=font)
                if sub:
                    sbbox = draw.textbbox((0, 0), sub, font=small_font)
                    sw = sbbox[2] - sbbox[0]
                    draw.text(((size[0] - sw) // 2, y + th + 8), sub, fill="#94a3b8", font=small_font)
                buf = BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()
            except Exception:
                return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'

        if not HAS_QRCODE:
            content = _make_placeholder("QR not available", "Restart the tester process")
            return Response(content=content, media_type="image/png")

        try:
            qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=8, border=2)
            qr.add_data(text)
            qr.make(fit=True)
            img = qr.make_image(fill_color="#0f172a", back_color="#e2e8f0")
            buf = BytesIO()
            img.save(buf, format="PNG")
            return Response(content=buf.getvalue(), media_type="image/png")
        except Exception as e:
            content = _make_placeholder("QR generation failed", str(e)[:30])
            return Response(content=content, media_type="image/png")

    @app.post("/set_intel_config")
    async def set_intel_config(request: Request):
        """Update the live Intelligence API config from the HUD Config tab (demo only).
        Allows changing provider/key/model mid-run without restarting the tester.
        The key is kept server-side for /analyze_competitor calls.
        """
        data = await request.json()
        _current_state["intel_ai_provider"] = data.get("provider", _current_state.get("intel_ai_provider", "stub"))
        _current_state["intel_ai_key"] = data.get("key", _current_state.get("intel_ai_key", ""))
        _current_state["intel_ai_model"] = data.get("model", _current_state.get("intel_ai_model", "grok-3"))
        _current_state["intel_ai_enabled"] = bool(data.get("enabled", _current_state.get("intel_ai_enabled", True)))
        return {"ok": True, "provider": _current_state.get("intel_ai_provider")}

    @app.get("/list_models")
    async def list_models():
        """Query xAI (or compatible) /v1/models using the key currently in Config.
        Returns the list of model IDs the key can actually use. Very useful for figuring out
        the exact string to put in the Model field (e.g. 'grok-3', 'grok-3-mini', etc.).
        """
        key = _current_state.get("intel_ai_key", "")
        provider = _current_state.get("intel_ai_provider", "grok")
        if not key:
            return {"models": [], "error": "No API key set in the Config tab yet. Enter key + Apply first."}

        # Only really useful for grok/openai-style providers for now
        if provider.lower() not in ("grok", "openai"):
            return {"models": [], "error": f"Model listing only supported for 'grok' or 'openai' provider (current: {provider})."}

        try:
            import requests
            url = "https://api.x.ai/v1/models" if provider.lower() == "grok" else "https://api.openai.com/v1/models"
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {key}"},
                timeout=20
            )
            resp.raise_for_status()
            data = resp.json()
            model_ids = sorted([m.get("id") for m in data.get("data", []) if m.get("id")])
            return {"models": model_ids, "count": len(model_ids), "note": "Click a model name below (or copy it) and paste into the Model field, then Apply Changes."}
        except Exception as e:
            api_body = ""
            if 'resp' in locals() and resp is not None:
                try:
                    api_body = " | " + str(resp.json())
                except Exception:
                    api_body = " | " + (resp.text[:300] if getattr(resp, 'text', None) else "")
            return {"models": [], "error": f"{type(e).__name__}: {e}{api_body}"}

    @app.post("/analyze_competitor")
    async def analyze_competitor(request: Request):
        """Real AI analysis for a competitor ledger address using the configured Intelligence API (from Config tab).
        Currently supports Grok (xAI) when provider=grok and key provided.
        The prompt focuses on on-chain trending, strategy, and how to compete/skim against it.
        Output is advisory only and does not affect A-S reservation or quoting.

        Endpoints on this HUD server (for reference):
        - GET /state : current live book + A-S + intel (polled by UI ~800ms)
        - POST /set_intel_config : from Config tab Apply (sets intel_ai_provider/key/model/enabled into _current_state)
        - POST /analyze_competitor : the one that may hit the real x.ai API (body: {"address": "r..."} ; may also include optional context)
        - Others: / (index), /qr, POST /state (for engine push).
        """
        data = await request.json()
        address = data.get("address", "").strip()
        if not address:
            return {"result": "No address provided."}

        provider = _current_state.get("intel_ai_provider", "stub")
        key = _current_state.get("intel_ai_key", "")
        model = _current_state.get("intel_ai_model", "grok-3")
        enabled = _current_state.get("intel_ai_enabled", True)

        # Pull any live context the tester has been pushing (from WS book + competitor scrape)
        # This makes the Grok "suggestion" current-aware for "skim harder right now".
        # Prefer values sent in this POST body (from the UI's lastState) as they are the freshest the browser saw.
        live_pressure = data.get("competitor_pressure") or _current_state.get("competitor_pressure")
        live_obs_spread = data.get("observed_spread_pct") or _current_state.get("competitor_observed_spread_pct")
        live_depth = _current_state.get("competitor_depth_xrp")
        inv_label = data.get("inventory_label") or _current_state.get("inventory_label")
        top_comps = _current_state.get("top_competitors", [])[:3] if _current_state.get("top_competitors") else []

        debug_note = f"[HUD /analyze] provider={provider} had_key={bool(key)} (len={len(key) if key else 0}) enabled={enabled} model={model}"

        if not enabled or not key:
            sim = (f"{debug_note}\n"
                   f"AI not enabled or no key configured in Config tab (provider={provider}). "
                   f"Demo simulation for {address}: This address shows high activity in the RLUSD/XRP book, "
                   f"likely a competitor MM with tight spreads and frequent L1 adjustments. "
                   f"Counter by monitoring their cancels for adverse signals.")
            return {"result": sim}

        if provider.lower() != "grok":
            sim = (f"{debug_note}\n"
                   f"Only Grok provider is supported for real API calls right now (configured: {provider}). "
                   f"Using simulation for {address}.")
            return {"result": sim}

        try:
            import requests
            url = "https://api.x.ai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }

            # Build richer prompt that includes live context so the suggestion is actionable for current skim vs this address.
            context_lines = []
            if live_pressure is not None:
                context_lines.append(f"current competitor pressure={live_pressure:.2f} (0=defensive/skim harder)")
            if live_obs_spread is not None:
                context_lines.append(f"observed L1 spread in book ~{live_obs_spread:.3f}%")
            if live_depth is not None:
                context_lines.append(f"recent competitor depth ~{live_depth:.1f} XRP")
            if inv_label:
                context_lines.append(f"our current inventory posture: {inv_label}")
            if top_comps:
                context_lines.append(f"other active makers visible: {', '.join([str(c.get('account','?'))[:8] for c in top_comps])}")

            context_str = (" Current live WS book context: " + "; ".join(context_lines) + ".") if context_lines else ""

            # Current on-demand prompt (for specific competitor address analysis)
            current_prompt = (
                f"You are an expert on XRPL market making and on-chain competitor analysis.\n"
                f"Analyze the ledger address {address} for its likely market-making strategy on the RLUSD/XRP order book.\n\n"
                f"**Primary goal:** Identify the holes and repeatable patterns in this competitor's behavior that we can exploit to win the best queue positions, "
                f"increase our realized skim (spread capture), and compound our bag more effectively over time.\n\n"
                f"Focus areas:\n"
                f"- Posted spreads and sizes from recent activity\n"
                f"- Aggressiveness vs defensiveness, inventory skew signals\n"
                f"- Reaction to fills or price moves (e.g. cancel patterns)\n"
                f"- Any 'trending' behavior (increasing/decreasing presence)\n"
                f"- Specific exploitable weaknesses (e.g. they cancel one side too aggressively after a fill, they step away predictably on volatility, they are weak on one side during rebalances, etc.)\n\n"
                f"Then give **concrete, actionable exploitative tactics** our pure A-S bot can use right now: better positioning ideas, when to step inside their levels, queue-jumping opportunities, sizing/timing suggestions, when to be patient vs aggressive, etc.\n\n"
                f"Base your reasoning only on public on-chain patterns; do not speculate on off-chain identity.\n"
                f"{context_str}"
            )

            prompt = current_prompt

            # TODO (future - once we start live MM with this bot):
            # Make this prompt significantly richer by feeding:
            #   - Full recent book history / our own recent fills + markouts on this book
            #   - More complete top-of-book levels from the scraped competitors
            #   - What our current pure A-S math is outputting (reservation price, optimal spread)
            #   - Recent periods where low pressure + good fills occurred
            # Goal: Turn the response into high-signal "how to beat this specific maker right now and win the best positions to maximize long-term skim" advice.

            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 600,
                "temperature": 0.6,
            }

            print(debug_note + " | sending real Grok call with prompt len=" + str(len(prompt)))

            resp = requests.post(url, headers=headers, json=payload, timeout=45)
            resp.raise_for_status()
            content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "No content returned from Grok.")
            result = f"{debug_note} | REAL GROK RESPONSE:\n\n{content}"
            return {"result": result}
        except Exception as e:
            # Surface the actual API error body for 4xx/5xx so we can debug model names, auth, etc.
            api_error = ""
            if 'resp' in locals() and resp is not None:
                try:
                    api_error = " | API body: " + str(resp.json())
                except Exception:
                    api_error = " | API body: " + (resp.text[:500] if resp.text else str(e))
            err = f"{debug_note}\nError calling Grok API for {address}: {str(e)}{api_error}. (Model '{model}' not accepted by this key. Current recommended model is 'grok-3'. In Config tab set Model to grok-3 (or grok-3-mini), click Apply Changes, then try Analyze again. The 'Fetch' button can help discover what your key supports.)"
            print(err)  # also to terminal for easy copy
            return {"result": err}


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

    qr_status = "ENABLED (real scannable codes)" if HAS_QRCODE else "DISABLED (run: pip install qrcode pillow, then fully restart this tester)"
    print(f"[HUD] QR support: {qr_status}")
    print(f"[HUD] Open http://{host}:{port} → Inventory tab → 'Show QR Code'. Direct test: http://{host}:{port}/qr?text=rYourBotAddressHere")

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
