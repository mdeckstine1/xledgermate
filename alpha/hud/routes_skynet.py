"""Alpha HUD SKYNET routes — advisor (Phase 1 + Phase 2 agent)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_RUNTIME = Path("logs/alpha_runtime_state.json")
_OVERRIDES = Path("logs/alpha_overrides.json")
_COMMANDS = Path("logs/alpha_commands.json")


def register_skynet_routes(app: Any) -> None:
    from fastapi import Body
    from fastapi.responses import JSONResponse

    from alpha.hud.skynet import (
        build_skynet_context,
        call_skynet_advisor,
        filter_applicable_suggestions,
        format_advisor_display,
        skynet_status,
    )
    from alpha.hud.skynet_agent import (
        agent_status_payload,
        load_agent_config,
        load_audit_entries,
        merge_agent_patch,
        pause_full_skynet_mode,
        run_skynet_agent,
    )
    from alpha.operator.runtime import (
        OperatorRuntimeStore,
        apply_overrides,
        effective_config_snapshot,
    )
    from config.settings import BotConfig
    from utils.env_secrets import resolve_grok_key

    def _load_hud_state() -> Dict[str, Any]:
        if not _RUNTIME.is_file():
            return {}
        try:
            data = json.loads(_RUNTIME.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _runtime() -> OperatorRuntimeStore:
        return OperatorRuntimeStore(overrides_path=_OVERRIDES, commands_path=_COMMANDS)

    def _effective_context() -> tuple[Dict[str, Any], BotConfig, Dict[str, Any]]:
        hud_state = _load_hud_state()
        base = BotConfig.load()
        overrides = _runtime().load_overrides()
        effective = apply_overrides(base, overrides)
        snap = effective_config_snapshot(effective, overrides)
        return hud_state, effective, snap

    @app.get("/operator/skynet/status")
    async def get_skynet_status() -> JSONResponse:
        return JSONResponse({"ok": True, **skynet_status(), **agent_status_payload()})

    @app.get("/operator/skynet/agent")
    async def get_skynet_agent() -> JSONResponse:
        return JSONResponse({"ok": True, **agent_status_payload()})

    @app.patch("/operator/skynet/agent")
    async def patch_skynet_agent(body: Dict[str, Any] = Body(...)) -> JSONResponse:
        merged, errors = merge_agent_patch(body if isinstance(body, dict) else {})
        if errors:
            return JSONResponse({"ok": False, "errors": errors}, status_code=400)
        return JSONResponse({"ok": True, **agent_status_payload(), "message": "Agent Smith settings saved"})

    @app.post("/operator/skynet/agent/trigger")
    async def post_skynet_agent_trigger() -> JSONResponse:
        result = run_skynet_agent(force=True)
        if not result.get("ok"):
            return JSONResponse(result, status_code=400)
        return JSONResponse(result)

    @app.get("/operator/skynet/audit")
    async def get_skynet_audit(limit: int = 50) -> JSONResponse:
        lim = max(1, min(200, int(limit or 50)))
        return JSONResponse({"ok": True, "entries": load_audit_entries(limit=lim)})

    @app.post("/operator/skynet/agent/pause-full")
    async def post_skynet_pause_full() -> JSONResponse:
        agent = pause_full_skynet_mode()
        return JSONResponse(
            {
                "ok": True,
                "full_mode_enabled": False,
                "message": "Full SKYNET mode paused — agent suggest mode unchanged",
                **agent_status_payload(),
            }
        )

    def _apply_suggestions(suggestions: List[Dict[str, Any]]) -> JSONResponse:
        base = BotConfig.load()
        sanitized, accepted, errors = filter_applicable_suggestions(suggestions, base=base)
        if errors:
            return JSONResponse({"ok": False, "errors": errors}, status_code=400)
        if not sanitized:
            return JSONResponse(
                {"ok": False, "message": "No applicable changes after guardrails"},
                status_code=400,
            )
        merged, patch_errors = _runtime().patch_overrides(sanitized, base=base)
        if patch_errors:
            return JSONResponse({"ok": False, "errors": patch_errors}, status_code=400)
        effective = apply_overrides(base, merged)
        return JSONResponse(
            {
                "ok": True,
                "applied": sanitized,
                "applied_details": accepted,
                "operator_overrides": merged,
                "config_effective": effective_config_snapshot(effective, merged),
                "message": f"Applied {len(sanitized)} operator override(s). Takes effect next cycle.",
            }
        )

    @app.post("/operator/skynet/agent/apply-safe")
    async def post_skynet_agent_apply_safe() -> JSONResponse:
        agent = load_agent_config()
        proposal = agent.get("latest_proposal") or {}
        safe = proposal.get("safe_changes") or []
        if not safe:
            return JSONResponse(
                {"ok": False, "message": "No safe changes in latest agent proposal"},
                status_code=400,
            )
        return _apply_suggestions(safe)

    @app.post("/operator/skynet/ask")
    async def post_skynet_ask(body: Dict[str, Any] = Body(...)) -> JSONResponse:
        cfg = BotConfig.load()
        status = skynet_status(cfg)
        if not status["enabled"]:
            return JSONResponse(
                {"ok": False, "message": "SKYNET disabled in config (alpha_skynet_enabled)."},
                status_code=400,
            )
        api_key = resolve_grok_key(getattr(cfg, "alpha_grok_api_key", "") or "")
        if not api_key:
            return JSONResponse(
                {
                    "ok": False,
                    "message": "SKYNET API key not configured. Set XAI_API_KEY or XLG_GROK_KEY in .env on the server.",
                },
                status_code=400,
            )

        prompt = str(body.get("prompt") or "").strip()
        if not prompt:
            return JSONResponse({"ok": False, "message": "prompt required"}, status_code=400)

        hud_state, effective, snap = _effective_context()
        base = BotConfig.load()
        try:
            context = build_skynet_context(hud_state, operator_config=snap)
        except Exception as exc:
            logger.exception("skynet_context_failed")
            return JSONResponse(
                {"ok": False, "message": f"SKYNET context build failed: {exc}"},
                status_code=400,
            )

        try:
            raw, parsed = call_skynet_advisor(
                user_prompt=prompt,
                context=context,
                api_key=api_key,
                model=status["model"],
                max_tokens=status.get("max_tokens", 4096),
                operator_phase=snap.get("alpha_operator_phase"),
                market_regime=snap.get("alpha_operator_market_regime"),
            )
        except Exception as exc:
            logger.warning("skynet_ask_failed | %s", exc)
            return JSONResponse({"ok": False, "message": str(exc)[:800]}, status_code=400)

        sanitized, accepted, apply_errors = filter_applicable_suggestions(
            parsed.get("suggested_changes") or [],
            base=base,
        )

        return JSONResponse(
            {
                "ok": True,
                "raw_response": raw,
                "parsed": parsed,
                "display": format_advisor_display(parsed),
                "applicable_overrides": sanitized,
                "applicable_changes": accepted,
                "apply_preview_errors": apply_errors,
                "model": status["model"],
            }
        )

    @app.post("/operator/skynet/apply")
    async def post_skynet_apply(body: Dict[str, Any] = Body(...)) -> JSONResponse:
        suggestions: List[Dict[str, Any]] = []
        if isinstance(body.get("suggested_changes"), list):
            suggestions = body["suggested_changes"]
        elif isinstance(body.get("overrides"), dict):
            suggestions = [
                {"key": k, "value": v, "reason": "operator apply"}
                for k, v in body["overrides"].items()
            ]
        else:
            return JSONResponse(
                {"ok": False, "message": "suggested_changes array or overrides object required"},
                status_code=400,
            )
        return _apply_suggestions(suggestions)

    logger.debug("alpha_hud_skynet_routes_registered")
