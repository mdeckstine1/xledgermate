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
import html
import json
import subprocess
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
    "ws_as_version": None,
    "sample_count": 0,
    "as_presence_pct": None,
}

_recent_limit = 20

app = FastAPI(title="WS + Pure A-S Real-Time HUD") if FastAPI else None

if app:
    _HUD_DIR = Path(__file__).parent / "hud"
    _INDEX_HTML = _HUD_DIR / "index.html"

    def _render_index_html() -> str:
        from experimental.ws_feed.pure_quote_path import current_ws_as_version

        ver = current_ws_as_version()
        mtime = int(_INDEX_HTML.stat().st_mtime) if _INDEX_HTML.exists() else 0
        build = f"{ver}-{mtime}"
        html = _INDEX_HTML.read_text(encoding="utf-8")
        return html.replace("__HUD_BUILD__", build)

    def _index_response() -> HTMLResponse:
        if not _INDEX_HTML.exists():
            return HTMLResponse(
                "<h1>index.html not found in hud/ — run from correct cwd or restore the file</h1>",
                status_code=500,
            )
        resp = HTMLResponse(_render_index_html())
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline';"
        )
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return _index_response()

    @app.get("/hud", response_class=HTMLResponse)
    async def hud_alias():
        return _index_response()










    @app.get("/state")
    async def get_state():
        from experimental.ws_feed.pure_quote_path import current_ws_as_version

        _current_state["ws_as_version"] = current_ws_as_version()
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

    @app.post("/engine/{action}")
    async def engine_control(action: str):
        """Production VPS: start/stop/restart ws-engine via systemd."""
        allowed = {"start", "stop", "restart"}
        if action not in allowed:
            return {"ok": False, "message": f"Unknown action: {action}"}
        unit = Path("/etc/systemd/system/xledgermate.service")
        if not unit.is_file():
            return {
                "ok": False,
                "message": "Engine control needs systemd (VPS). Local lab: run live_pure_as_tester --serve-hud.",
            }
        try:
            proc = subprocess.run(
                ["systemctl", action, "xledgermate"],
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {"ok": False, "message": str(exc)}
        active = subprocess.run(
            ["systemctl", "is-active", "xledgermate"],
            capture_output=True,
            text=True,
            check=False,
        )
        running = (active.stdout or "").strip() == "active"
        if proc.returncode == 0:
            return {
                "ok": True,
                "message": f"ws-engine {action} OK — {'running' if running else 'stopped'}.",
                "running": running,
            }
        err = (proc.stderr or proc.stdout or "systemctl failed").strip()
        return {"ok": False, "message": err[-500:], "running": running}

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
        """Update Intelligence API config from HUD Config tab; persists to logs/hud_intel_config.json."""
        from experimental.ws_feed.hud_intel_support import save_persisted_intel_config

        data = await request.json()
        provider = str(data.get("provider") or _current_state.get("intel_ai_provider") or "grok")
        key = str(data.get("key") or _current_state.get("intel_ai_key") or "")
        model = str(data.get("model") or _current_state.get("intel_ai_model") or "grok-3")
        enabled = bool(data.get("enabled", _current_state.get("intel_ai_enabled", True)))
        if key.strip() and provider.lower() == "stub":
            provider = "grok"
        _current_state["intel_ai_provider"] = provider
        _current_state["intel_ai_key"] = key
        _current_state["intel_ai_model"] = model
        _current_state["intel_ai_enabled"] = enabled and bool(key.strip())
        if key.strip():
            save_persisted_intel_config(
                provider=provider,
                key=key,
                model=model,
                enabled=_current_state["intel_ai_enabled"],
            )
        return {
            "ok": True,
            "provider": _current_state.get("intel_ai_provider"),
            "had_key": bool(key.strip()),
        }

    @app.get("/get_telegram_config")
    async def get_telegram_config():
        """Telegram reporting settings from config.yaml (no secrets)."""
        from experimental.ws_feed.hud_telegram_support import telegram_config_snapshot

        snap = telegram_config_snapshot()
        _current_state.update(snap)
        return snap

    @app.post("/set_telegram_config")
    async def set_telegram_config(request: Request):
        """Update Telegram report settings from HUD Config tab; persists to config.yaml."""
        from experimental.ws_feed.hud_telegram_support import apply_telegram_config_from_hud

        data = await request.json()
        snap = apply_telegram_config_from_hud(data)
        _current_state.update(snap)
        return {"ok": True, **snap}

    @app.get("/competitor_nicknames")
    async def get_competitor_nicknames():
        """F1 — local operator nicknames keyed by r-address (logs/competitor_nicknames.json)."""
        from experimental.ws_feed.competitor_nicknames import load_nicknames

        mapping = load_nicknames()
        _current_state["competitor_nicknames"] = mapping
        return {"nicknames": mapping}

    @app.post("/competitor_nicknames")
    async def post_competitor_nicknames(request: Request):
        """Set or remove one nickname, or replace the full map."""
        from experimental.ws_feed.competitor_nicknames import (
            load_nicknames,
            remove_nickname,
            save_nicknames,
            set_nickname,
        )

        data = await request.json()
        if isinstance(data.get("nicknames"), dict):
            mapping = save_nicknames(data["nicknames"])
        else:
            address = str(data.get("address") or "").strip()
            nickname = str(data.get("nickname") or "").strip()
            if not address:
                return {"ok": False, "error": "address required"}
            if nickname:
                mapping = set_nickname(address, nickname)
            else:
                mapping = remove_nickname(address)
        _current_state["competitor_nicknames"] = mapping
        return {"ok": True, "nicknames": mapping}

    @app.get("/reports/catalog")
    async def reports_catalog():
        """Soak-safe report list for HUD Reports tab."""
        from experimental.ws_feed.hud_reports_support import list_reports

        return {"reports": list_reports()}

    @app.get("/report/{report_id}", response_class=HTMLResponse)
    async def report_view_html(report_id: str):
        """Standalone report page (open in new browser tab)."""
        from experimental.ws_feed.hud_reports_support import (
            generate_report_text,
            get_report_spec,
            wrap_report_html,
        )

        spec = get_report_spec(report_id)
        if spec is None:
            return HTMLResponse(
                f"<h1>Unknown report: {html.escape(report_id)}</h1>"
                f"<p><a href='/'>Back to HUD</a></p>",
                status_code=404,
            )
        body = generate_report_text(report_id)
        page = wrap_report_html(
            report_id=report_id,
            title=spec.title,
            subtitle=spec.subtitle,
            body_text=body,
            spec=spec,
        )
        resp = HTMLResponse(page)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return resp

    @app.get("/report/{report_id}.txt")
    async def report_view_text(report_id: str):
        """Plain-text report (curl / automation)."""
        from fastapi.responses import PlainTextResponse

        from experimental.ws_feed.hud_reports_support import generate_report_text, get_report_spec

        if get_report_spec(report_id) is None:
            return PlainTextResponse(f"Unknown report: {report_id}\n", status_code=404)
        return PlainTextResponse(generate_report_text(report_id))

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

    @app.post("/send_funds")
    async def send_funds(request: Request):
        """Live withdraw: XRP or RLUSD from bot account to destination (signed on ledger)."""
        data = await request.json()
        destination = str(data.get("destination") or "").strip()
        asset = str(data.get("asset") or "XRP").strip().upper()
        try:
            amount = float(data.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        confirm_running = bool(data.get("confirm_engine_running"))

        from config.settings import BotConfig, patch_config_file

        config = BotConfig.load()
        if not config.bot_account_address.strip():
            return {"ok": False, "message": "bot_account_address is not configured."}
        if not (config.bot_secret_key or "").strip():
            return {
                "ok": False,
                "message": "bot_secret_key required — set in config/credentials.local.yaml.",
            }
        if not destination.startswith("r"):
            return {"ok": False, "message": "Destination must be a classic XRPL address (r...)."}
        if amount <= 0:
            return {"ok": False, "message": "Amount must be greater than zero."}
        if asset not in ("XRP", "RLUSD"):
            return {"ok": False, "message": "Asset must be XRP or RLUSD."}

        typed = str(data.get("confirm_text") or "").strip().upper()
        if typed != "SEND":
            return {
                "ok": False,
                "message": 'Type SEND in the confirmation box to authorize a live withdrawal.',
            }

        try:
            from gui.engine_control import is_engine_running

            engine_up = bool(is_engine_running())
        except Exception:
            engine_up = False
        if engine_up and not confirm_running:
            return {
                "ok": False,
                "message": "Engine is running — stop ws-engine first, or check the confirmation box.",
                "engine_running": True,
            }

        try:
            from utils.send_funds import send_from_bot_account

            tx_hash = await send_from_bot_account(
                destination=destination,
                amount=amount,
                asset=asset,
            )
        except Exception as exc:
            return {"ok": False, "message": str(exc)[:500]}

        patch_config_file({"send_destination_default": destination})
        return {
            "ok": True,
            "message": f"Sent {amount:g} {asset} to {destination}",
            "tx_hash": tx_hash,
        }

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

        try:
            from config.settings import BotConfig
            from experimental.ws_feed.ws_feature_flags import WsFeatureFlags

            if not WsFeatureFlags.from_config(BotConfig.load()).hud_grok:
                return {
                    "result": "Grok analysis disabled (set ws_hud_grok_enabled: true in config).",
                }
        except Exception:
            pass

        provider = _current_state.get("intel_ai_provider", "stub")
        key = _current_state.get("intel_ai_key", "")
        model = _current_state.get("intel_ai_model", "grok-3")
        enabled = _current_state.get("intel_ai_enabled", True)

        # Pull any live context the tester has been pushing (from WS book + competitor scrape)
        # This makes the Grok "suggestion" current-aware for "skim harder right now".
        # Prefer values sent in this POST body (from the UI's lastState) as they are the freshest the browser saw.
        live_pressure = data.get("competitor_pressure") or _current_state.get("competitor_pressure")
        live_obs_spread = data.get("observed_spread_pct") or _current_state.get("competitor_observed_spread_pct")
        live_depth = data.get("competitor_depth_xrp") or _current_state.get("competitor_depth_xrp")
        inv_label = data.get("inventory_label") or _current_state.get("inventory_label")

        from experimental.ws_feed.hud_intel_support import build_competitor_analysis_context

        briefing = build_competitor_analysis_context(_current_state, address, extra=data)
        profile = briefing.get("profile")
        in_peer_lane = bool(briefing.get("in_peer_lane"))
        peer_count = int(_current_state.get("peer_lane_count") or 0)
        our_lane = briefing.get("our_lane_xrp") or _current_state.get("our_lane_xrp")
        if peer_count > 0 and _current_state.get("top_peers"):
            top_comps = _current_state.get("top_peers", [])[:3]
            comp_source = "peer_lane"
        else:
            top_comps = _current_state.get("top_competitors", [])[:3] if _current_state.get("top_competitors") else []
            comp_source = "book_wide"

        debug_note = (
            f"[HUD /analyze] provider={provider} had_key={bool(key)} (len={len(key) if key else 0}) "
            f"enabled={enabled} model={model} profile_found={profile is not None} "
            f"in_peer_lane={in_peer_lane} source={briefing.get('source')}"
        )

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
            if our_lane is not None:
                context_lines.append(f"our posted touch lane ~{float(our_lane):.1f} XRP (peer band 0.4×–2.5×)")
            if peer_count > 0:
                context_lines.append(f"peer_lane_count={peer_count} (pressure/spread from touch-band peers, not book-wide whales)")
            if top_comps:
                label = "peer makers at our touch" if comp_source == "peer_lane" else "other active makers (book-wide)"
                context_lines.append(f"{label}: {', '.join([str(c.get('account','?'))[:8] for c in top_comps])}")

            context_str = (" Current live WS book context: " + "; ".join(context_lines) + ".") if context_lines else ""

            is_our_bot = bool(briefing.get("is_our_bot"))
            response_format = (
                "Respond in plain English with markdown section headers "
                "(e.g. ## Visibility, ## Inventory, ## Recommendations). "
                "Do NOT output JSON, code fences, or repeat a structured briefing schema."
            )
            if is_our_bot:
                current_prompt = (
                    f"You are an expert XRPL market-making operator reviewing OUR OWN bot ledger {address}.\n\n"
                    f"**Primary goal:** Self-audit — quote visibility, touch distance vs BBO, inventory alignment, "
                    f"cancel/fill hygiene, and whether G7 envelope settings match current regime. "
                    f"Do NOT recommend exploitative tactics against this address (it is us).\n\n"
                    f"{briefing.get('prompt_block', '')}\n\n"
                    f"Focus areas:\n"
                    f"- Are we visible at touch or too far back (worst_vs_touch_bps, quote_visibility)?\n"
                    f"- Does inventory_label match our bid/ask backoff (G7 summary)?\n"
                    f"- Session cancel_per_fill and fill age vs peer_lane_count=0 regime\n"
                    f"- Concrete tuning suggestions for our pure A-S bot only\n\n"
                    f"{response_format}\n"
                    f"{context_str}"
                )
            else:
                current_prompt = (
                    f"You are an expert on XRPL market making and on-chain competitor analysis.\n"
                    f"Analyze the ledger address {address} for its likely market-making strategy on the RLUSD/XRP order book.\n\n"
                    f"**Primary goal:** Identify the holes and repeatable patterns in this competitor's behavior that we can exploit to win the best queue positions, "
                    f"increase our realized skim (spread capture), and compound our bag more effectively over time.\n\n"
                    f"{briefing.get('prompt_block', '')}\n\n"
                    f"Focus areas:\n"
                    f"- Posted spreads and sizes from recent activity (use scraped facts first)\n"
                    f"- Aggressiveness vs defensiveness, inventory skew signals\n"
                    f"- Reaction to fills or price moves (e.g. cancel patterns, fled-touch events if listed)\n"
                    f"- Any 'trending' behavior (increasing/decreasing presence)\n"
                    f"- Specific exploitable weaknesses supported by the scrape evidence\n\n"
                    f"Then give **concrete, actionable exploitative tactics** our pure A-S bot can use right now: better positioning ideas, when to step inside their levels, queue-jumping opportunities, sizing/timing suggestions, when to be patient vs aggressive, etc.\n"
                    f"If the maker is OUT of our peer touch band, say so up front and limit tactics to regime/macro context.\n\n"
                    f"Base your reasoning on the scraped facts above; do not speculate on off-chain identity.\n"
                    f"{response_format}\n"
                    f"{context_str}"
                )

            prompt = current_prompt

            # Post-soak (ws-engine): per-peer event history, fill-correlated cancels, structured JSON output → G4 hook.

            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2048,
                "temperature": 0.6,
            }

            print(debug_note + " | sending real Grok call with prompt len=" + str(len(prompt)))

            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            choice = resp.json().get("choices", [{}])[0] or {}
            content = choice.get("message", {}).get("content", "No content returned from Grok.")
            finish = choice.get("finish_reason") or ""
            result = content.strip()
            if finish == "length":
                result += "\n\n---\n(Response hit the token limit and may be cut off mid-thought.)"
            from experimental.ws_feed.hud_intel_support import (
                format_intel_analysis_report,
                strip_grok_json_echo,
            )

            local_report = format_intel_analysis_report(briefing)
            grok_text = strip_grok_json_echo(result)
            result = f"{local_report}\n\n── Grok commentary (advisory) ──\n\n{grok_text}"
            try:
                from experimental.ws_feed.intel_decisions_log import (
                    append_intel_record,
                    build_grok_suggestion_intel_record,
                )

                append_intel_record(
                    build_grok_suggestion_intel_record(
                        address=address,
                        model=model,
                        briefing=briefing,
                        result_text=result,
                        context_snapshot={
                            "competitor_pressure": live_pressure,
                            "book_regime_pressure": _current_state.get("book_regime_pressure"),
                            "book_side_skew_label": _current_state.get("book_side_skew_label"),
                            "inventory_label": inv_label,
                            "our_lane_xrp": our_lane,
                            "peer_lane_count": peer_count,
                        },
                    )
                )
            except Exception as log_exc:
                print(f"[HUD /analyze] grok_suggestion log failed: {log_exc}")
            return {
                "result": result,
                "truncated": finish == "length",
                "debug": debug_note,
                "briefing": {
                    "profile_found": profile is not None,
                    "in_peer_lane": in_peer_lane,
                    "source": briefing.get("source"),
                    "touch_xrp": briefing.get("touch_xrp"),
                    "evidence_lines": briefing.get("evidence_lines"),
                    "structured_briefing": briefing.get("structured_briefing"),
                },
            }
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


def get_hud_current_state() -> Dict[str, Any]:
    """Snapshot of in-memory HUD state (intel config, competitor fields, etc.)."""
    return dict(_current_state)


def update_state(new_state: Dict[str, Any]):
    """Call this from the live tester / engine on every decision cycle."""
    global _current_state
    old_key = (_current_state.get("intel_ai_key") or "").strip()
    if old_key:
        if not (new_state.get("intel_ai_key") or "").strip():
            new_state = {k: v for k, v in new_state.items() if k != "intel_ai_key"}
        if new_state.get("intel_ai_provider") == "stub" and _current_state.get("intel_ai_provider") not in (
            None,
            "",
            "stub",
        ):
            new_state = {k: v for k, v in new_state.items() if k != "intel_ai_provider"}
        if new_state.get("intel_ai_enabled") is False and _current_state.get("intel_ai_enabled"):
            new_state = {k: v for k, v in new_state.items() if k != "intel_ai_enabled"}
    _current_state.update(new_state)
    if "recent_notes" not in _current_state:
        _current_state["recent_notes"] = []
    if new_state.get("last_note"):
        _current_state["recent_notes"].insert(0, new_state["last_note"][:180])
        _current_state["recent_notes"] = _current_state["recent_notes"][:_recent_limit]


_auth_attached = False


def run_hud(
    host: str = "127.0.0.1",
    port: int = 8765,
    background: bool = True,
    auth: Optional[Any] = None,
):
    """Start the HUD server. Set background=False to block."""
    global _auth_attached
    if FastAPI is None or uvicorn is None:
        print("FastAPI / uvicorn not installed. Run: pip install fastapi uvicorn")
        return None

    if app and auth and not _auth_attached:
        from experimental.ws_feed.hud_auth import attach_hud_auth

        attach_hud_auth(app, auth)
        _auth_attached = True
        print("[HUD] Access control enabled (username/password; passkeys on HTTPS)")

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
