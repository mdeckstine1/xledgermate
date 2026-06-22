"""HUD access control: username/password session + optional WebAuthn passkeys."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.responses import Response

try:
    from webauthn import (
        generate_authentication_options,
        generate_registration_options,
        options_to_json,
        verify_authentication_response,
        verify_registration_response,
    )
    from webauthn.helpers import bytes_to_base64url, base64url_to_bytes
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    HAS_WEBAUTHN = True
except ImportError:
    HAS_WEBAUTHN = False

SESSION_COOKIE = "xlg_hud_session"
SESSION_MAX_AGE_S = 30 * 24 * 3600
CHALLENGE_TTL_S = 300
PASSKEYS_FILE = Path("logs/hud_passkeys.json")

_PUBLIC_PREFIXES = (
    "/login",
    "/logout",
    "/auth/passkey/login",
    "/auth/passkey/register",
    "/favicon.png",
)


@dataclass(frozen=True)
class HudAuthSettings:
    enabled: bool
    username: str
    password: str
    session_secret: bytes
    rp_id: str = ""
    passkeys_path: Path = PASSKEYS_FILE

    @property
    def webauthn_enabled(self) -> bool:
        return HAS_WEBAUTHN


_challenges: Dict[str, Tuple[str, float, str]] = {}  # token -> (kind, expires, username)


def _clean(s: str) -> str:
    return (s or "").strip()


def resolve_hud_auth(config: Any, *, bind_host: str = "127.0.0.1") -> Optional[HudAuthSettings]:
    """Build auth settings from BotConfig + env. Enabled when creds set and HUD is public."""
    from utils.env_secrets import load_dotenv_local

    load_dotenv_local()
    username = _clean(getattr(config, "hud_auth_username", "")) or _clean(
        os.environ.get("XLG_HUD_USERNAME", "")
    )
    password = _clean(getattr(config, "hud_auth_password", "")) or _clean(
        os.environ.get("XLG_HUD_PASSWORD", "")
    )
    if not username or not password:
        return None

    explicit = bool(getattr(config, "hud_auth_enabled", False))
    public_bind = _clean(bind_host) not in ("", "127.0.0.1", "localhost", "::1")
    if not explicit and not public_bind:
        return None

    secret_material = f"{username}:{password}:xlg-hud-session".encode()
    session_secret = hashlib.sha256(secret_material).digest()
    rp_id = _clean(getattr(config, "hud_auth_rp_id", "")) or _clean(os.environ.get("XLG_HUD_RP_ID", ""))
    return HudAuthSettings(
        enabled=True,
        username=username,
        password=password,
        session_secret=session_secret,
        rp_id=rp_id,
    )


def verify_password(settings: HudAuthSettings, username: str, password: str) -> bool:
    return secrets.compare_digest(_clean(username), settings.username) and secrets.compare_digest(
        _clean(password), settings.password
    )


def _sign_session(settings: HudAuthSettings, username: str) -> str:
    issued = int(time.time())
    nonce = secrets.token_hex(8)
    payload = f"{username}|{issued}|{nonce}"
    sig = hmac.new(settings.session_secret, payload.encode(), hashlib.sha256).hexdigest()
    raw = f"{payload}|{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _verify_session(settings: HudAuthSettings, token: str) -> bool:
    if not token:
        return False
    try:
        pad = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token + pad).decode()
        username, issued_s, nonce, sig = raw.rsplit("|", 3)
        payload = f"{username}|{issued_s}|{nonce}"
        expected = hmac.new(settings.session_secret, payload.encode(), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(sig, expected):
            return False
        if username != settings.username:
            return False
        issued = int(issued_s)
        if time.time() - issued > SESSION_MAX_AGE_S:
            return False
        return True
    except (ValueError, UnicodeDecodeError):
        return False


def _session_from_request(request: Request) -> Optional[str]:
    return request.cookies.get(SESSION_COOKIE)


def is_authenticated(settings: HudAuthSettings, request: Request) -> bool:
    return _verify_session(settings, _session_from_request(request) or "")


def _session_response(settings: HudAuthSettings, *, next_url: str = "/") -> Response:
    target = next_url if next_url.startswith("/") and not next_url.startswith("//") else "/"
    resp = RedirectResponse(url=target, status_code=303)
    resp.set_cookie(
        SESSION_COOKIE,
        _sign_session(settings, settings.username),
        httponly=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE_S,
        path="/",
    )
    return resp


def _unauthorized_json() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)


def _rp_id_for_request(request: Request, settings: HudAuthSettings) -> str:
    if settings.rp_id:
        return settings.rp_id
    host = (request.headers.get("host") or "localhost").split(":")[0]
    return host


def _origin_for_request(request: Request) -> str:
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}"


def _load_passkeys(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    creds = data.get("credentials") if isinstance(data, dict) else None
    return list(creds) if isinstance(creds, list) else []


def _save_passkeys(path: Path, credentials: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"credentials": credentials}, indent=2), encoding="utf-8")


def _store_challenge(token: str, kind: str, username: str) -> None:
    now = time.time()
    expired = [k for k, (_, exp, _) in _challenges.items() if exp < now]
    for k in expired:
        _challenges.pop(k, None)
    _challenges[token] = (kind, now + CHALLENGE_TTL_S, username)


def _pop_challenge(token: str, kind: str, username: str) -> bool:
    row = _challenges.pop(token, None)
    if not row:
        return False
    stored_kind, expires, stored_user = row
    if stored_kind != kind or stored_user != username or time.time() > expires:
        return False
    return True


def _login_html(*, passkey_available: bool, secure_context_hint: bool, error: str = "") -> str:
    err = f'<p class="err">{error}</p>' if error else ""
    passkey_block = ""
    if passkey_available:
        passkey_block = """
        <button type="button" class="secondary" id="passkey-login">Sign in with passkey</button>
        <p class="hint">Use Face ID, fingerprint, or device PIN when your browser supports it.</p>
        """
    elif secure_context_hint:
        passkey_block = '<p class="hint">Passkeys need HTTPS. Password login still works; save it in your phone password manager for biometric unlock.</p>'
    else:
        passkey_block = '<p class="hint">Save your password in your phone&apos;s password manager for Face ID / fingerprint next time.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>XLedgerMate HUD — Sign in</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 16px; }}
    .card {{ background: #1e2937; border: 1px solid #334155; border-radius: 10px; padding: 24px; width: 100%; max-width: 380px; }}
    h1 {{ font-size: 1.1rem; margin: 0 0 4px; color: #60a5fa; }}
    p.sub {{ margin: 0 0 18px; color: #94a3b8; font-size: 0.85rem; }}
    label {{ display: block; font-size: 0.75rem; color: #94a3b8; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.04em; }}
    input {{ width: 100%; box-sizing: border-box; padding: 10px 12px; margin-bottom: 12px; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: #e2e8f0; font-size: 1rem; }}
    button {{ width: 100%; padding: 11px; border: none; border-radius: 6px; font-size: 1rem; font-weight: 600; cursor: pointer; margin-top: 4px; }}
    button.primary {{ background: #2563eb; color: white; }}
    button.secondary {{ background: #334155; color: #e2e8f0; margin-top: 10px; }}
    .hint {{ font-size: 0.78rem; color: #94a3b8; margin-top: 12px; line-height: 1.4; }}
    .err {{ color: #f87171; font-size: 0.85rem; margin-bottom: 10px; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>XLedgerMate HUD</h1>
    <p class="sub">Sign in to view the live market-maker dashboard.</p>
    {err}
    <form method="post" action="/login" autocomplete="on">
      <label for="username">Username</label>
      <input id="username" name="username" type="text" autocomplete="username" required>
      <label for="password">Password</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required>
      <input type="hidden" name="next" id="next" value="">
      <button class="primary" type="submit">Sign in</button>
    </form>
    {passkey_block}
  </div>
  <script>
    (function() {{
      const params = new URLSearchParams(location.search);
      document.getElementById('next').value = params.get('next') || '/';
      const btn = document.getElementById('passkey-login');
      if (!btn) return;
      btn.addEventListener('click', async () => {{
        const username = document.getElementById('username').value.trim();
        if (!username) {{ alert('Enter your username first.'); return; }}
        try {{
          const optRes = await fetch('/auth/passkey/login/options', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{ username }})
          }});
          const optJson = await optRes.json();
          if (!optJson.ok) throw new Error(optJson.error || 'Passkey options failed');
          const assertion = await navigator.credentials.get({{ publicKey: optJson.publicKey }});
          const verifyRes = await fetch('/auth/passkey/login/verify', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{
              username,
              challenge: optJson.challenge,
              credential: {{
                id: assertion.id,
                rawId: btoa(String.fromCharCode(...new Uint8Array(assertion.rawId))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,''),
                type: assertion.type,
                response: {{
                  authenticatorData: btoa(String.fromCharCode(...new Uint8Array(assertion.response.authenticatorData))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,''),
                  clientDataJSON: btoa(String.fromCharCode(...new Uint8Array(assertion.response.clientDataJSON))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,''),
                  signature: btoa(String.fromCharCode(...new Uint8Array(assertion.response.signature))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,''),
                  userHandle: assertion.response.userHandle ? btoa(String.fromCharCode(...new Uint8Array(assertion.response.userHandle))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,'') : null
                }}
              }}
            }})
          }});
          const verifyJson = await verifyRes.json();
          if (!verifyJson.ok) throw new Error(verifyJson.error || 'Passkey verification failed');
          location.href = document.getElementById('next').value || '/';
        }} catch (e) {{
          alert(e.message || String(e));
        }}
      }});
    }})();
  </script>
</body>
</html>"""


def _passkey_setup_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Register HUD passkey</title>
  <style>
    body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 16px; }
    .card { background: #1e2937; border: 1px solid #334155; border-radius: 10px; padding: 24px; max-width: 420px; }
    button { padding: 11px 16px; border: none; border-radius: 6px; background: #2563eb; color: white; font-weight: 600; cursor: pointer; }
    a { color: #60a5fa; }
    .hint { color: #94a3b8; font-size: 0.85rem; line-height: 1.45; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Register passkey</h1>
    <p class="hint">Add Face ID, fingerprint, or device PIN for faster sign-in on this phone or laptop.</p>
    <p><button id="register-passkey" type="button">Create passkey</button></p>
    <p><a href="/">Back to HUD</a></p>
  </div>
  <script>
    document.getElementById('register-passkey').addEventListener('click', async () => {
      try {
        const optRes = await fetch('/auth/passkey/register/options', { method: 'POST' });
        const optJson = await optRes.json();
        if (!optJson.ok) throw new Error(optJson.error || 'Could not start registration');
        const cred = await navigator.credentials.create({ publicKey: optJson.publicKey });
        const verifyRes = await fetch('/auth/passkey/register/verify', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            challenge: optJson.challenge,
            credential: {
              id: cred.id,
              rawId: btoa(String.fromCharCode(...new Uint8Array(cred.rawId))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,''),
              type: cred.type,
              response: {
                attestationObject: btoa(String.fromCharCode(...new Uint8Array(cred.response.attestationObject))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,''),
                clientDataJSON: btoa(String.fromCharCode(...new Uint8Array(cred.response.clientDataJSON))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,'')
              }
            }
          })
        });
        const verifyJson = await verifyRes.json();
        if (!verifyJson.ok) throw new Error(verifyJson.error || 'Registration failed');
        alert('Passkey registered. You can sign in with biometrics next time.');
        location.href = '/';
      } catch (e) {
        alert(e.message || String(e));
      }
    });
  </script>
</body>
</html>"""


def attach_hud_auth(app: FastAPI, settings: Optional[HudAuthSettings]) -> None:
    """Register login routes and HTTP middleware when auth is enabled."""
    if not settings or not settings.enabled:
        return

    passkeys = _load_passkeys(settings.passkeys_path)
    has_passkeys = bool(passkeys)

    @app.middleware("http")
    async def hud_auth_middleware(request: Request, call_next):
        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in _PUBLIC_PREFIXES):
            return await call_next(request)
        if is_authenticated(settings, request):
            return await call_next(request)
        if request.method in ("GET", "HEAD") and path in ("/", "/hud"):
            nxt = request.url.path
            if request.url.query:
                nxt += "?" + request.url.query
            return RedirectResponse(f"/login?next={nxt}", status_code=302)
        return _unauthorized_json()

    @app.get("/logout")
    async def logout() -> RedirectResponse:
        resp = RedirectResponse("/login", status_code=302)
        resp.delete_cookie(SESSION_COOKIE, path="/")
        return resp

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request, error: str = ""):
        if is_authenticated(settings, request):
            return RedirectResponse("/", status_code=302)
        secure = (request.headers.get("x-forwarded-proto") or request.url.scheme) == "https"
        return HTMLResponse(
            _login_html(
                passkey_available=HAS_WEBAUTHN and has_passkeys and secure,
                secure_context_hint=HAS_WEBAUTHN and has_passkeys and not secure,
                error=error,
            )
        )

    @app.post("/login")
    async def login_submit(request: Request):
        form = await request.form()
        username = str(form.get("username") or "")
        password = str(form.get("password") or "")
        next_url = str(form.get("next") or "/")
        if not verify_password(settings, username, password):
            return HTMLResponse(
                _login_html(
                    passkey_available=HAS_WEBAUTHN and has_passkeys,
                    secure_context_hint=False,
                    error="Invalid username or password.",
                ),
                status_code=401,
            )
        return _session_response(settings, next_url=next_url)

    @app.get("/login/passkey-setup", response_class=HTMLResponse)
    async def passkey_setup_page(request: Request):
        if not is_authenticated(settings, request):
            return RedirectResponse("/login?next=/login/passkey-setup", status_code=302)
        if not HAS_WEBAUTHN:
            return HTMLResponse("<p>Install webauthn package on the server.</p>", status_code=503)
        secure = (request.headers.get("x-forwarded-proto") or request.url.scheme) == "https"
        if not secure:
            return HTMLResponse(
                "<p>Passkey registration requires HTTPS. Use password login and save credentials in your password manager for biometric unlock.</p>",
                status_code=400,
            )
        return HTMLResponse(_passkey_setup_html())

    if not HAS_WEBAUTHN:
        return

    @app.post("/auth/passkey/register/options")
    async def passkey_register_options(request: Request):
        if not is_authenticated(settings, request):
            return _unauthorized_json()
        rp_id = _rp_id_for_request(request, settings)
        origin = _origin_for_request(request)
        user_id = hashlib.sha256(settings.username.encode()).digest()[:32]
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name="XLedgerMate HUD",
            user_id=user_id,
            user_name=settings.username,
            user_display_name=settings.username,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
        )
        challenge = bytes_to_base64url(options.challenge)
        _store_challenge(challenge, "register", settings.username)
        public_key = json.loads(options_to_json(options))
        return {"ok": True, "challenge": challenge, "publicKey": public_key["publicKey"]}

    @app.post("/auth/passkey/register/verify")
    async def passkey_register_verify(request: Request):
        if not is_authenticated(settings, request):
            return _unauthorized_json()
        data = await request.json()
        challenge = str(data.get("challenge") or "")
        if not _pop_challenge(challenge, "register", settings.username):
            return JSONResponse({"ok": False, "error": "Challenge expired."}, status_code=400)
        cred = data.get("credential") or {}
        rp_id = _rp_id_for_request(request, settings)
        origin = _origin_for_request(request)
        try:
            verified = verify_registration_response(
                credential={
                    "id": cred.get("id"),
                    "rawId": base64url_to_bytes(cred.get("rawId", "")),
                    "response": {
                        "attestationObject": base64url_to_bytes(
                            cred.get("response", {}).get("attestationObject", "")
                        ),
                        "clientDataJSON": base64url_to_bytes(
                            cred.get("response", {}).get("clientDataJSON", "")
                        ),
                    },
                    "type": "public-key",
                },
                expected_challenge=base64url_to_bytes(challenge),
                expected_rp_id=rp_id,
                expected_origin=origin,
            )
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

        stored = _load_passkeys(settings.passkeys_path)
        stored.append(
            {
                "id": verified.credential_id.hex(),
                "credential_id_b64": bytes_to_base64url(verified.credential_id),
                "public_key_b64": base64.b64encode(verified.credential_public_key).decode(),
                "sign_count": verified.sign_count,
                "username": settings.username,
            }
        )
        _save_passkeys(settings.passkeys_path, stored)
        nonlocal has_passkeys
        has_passkeys = True
        resp = JSONResponse({"ok": True})
        return resp

    @app.post("/auth/passkey/login/options")
    async def passkey_login_options(request: Request):
        data = await request.json()
        username = _clean(str(data.get("username") or ""))
        if username != settings.username:
            return JSONResponse({"ok": False, "error": "Unknown user."}, status_code=404)
        stored = _load_passkeys(settings.passkeys_path)
        if not stored:
            return JSONResponse({"ok": False, "error": "No passkeys registered."}, status_code=404)
        allow_credentials = [
            PublicKeyCredentialDescriptor(id=bytes.fromhex(row["id"]))
            for row in stored
            if row.get("username") == settings.username and row.get("id")
        ]
        options = generate_authentication_options(
            rp_id=_rp_id_for_request(request, settings),
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        challenge = bytes_to_base64url(options.challenge)
        _store_challenge(challenge, "login", settings.username)
        public_key = json.loads(options_to_json(options))
        return {"ok": True, "challenge": challenge, "publicKey": public_key["publicKey"]}

    @app.post("/auth/passkey/login/verify")
    async def passkey_login_verify(request: Request):
        data = await request.json()
        username = _clean(str(data.get("username") or ""))
        challenge = str(data.get("challenge") or "")
        if username != settings.username:
            return JSONResponse({"ok": False, "error": "Unknown user."}, status_code=404)
        if not _pop_challenge(challenge, "login", settings.username):
            return JSONResponse({"ok": False, "error": "Challenge expired."}, status_code=400)
        cred = data.get("credential") or {}
        cred_id_hex = base64url_to_bytes(cred.get("rawId", "")).hex()
        stored = _load_passkeys(settings.passkeys_path)
        row = next((r for r in stored if r.get("id") == cred_id_hex), None)
        if not row:
            return JSONResponse({"ok": False, "error": "Passkey not found."}, status_code=404)
        rp_id = _rp_id_for_request(request, settings)
        origin = _origin_for_request(request)
        try:
            verified = verify_authentication_response(
                credential={
                    "id": cred.get("id"),
                    "rawId": base64url_to_bytes(cred.get("rawId", "")),
                    "response": {
                        "authenticatorData": base64url_to_bytes(
                            cred.get("response", {}).get("authenticatorData", "")
                        ),
                        "clientDataJSON": base64url_to_bytes(
                            cred.get("response", {}).get("clientDataJSON", "")
                        ),
                        "signature": base64url_to_bytes(cred.get("response", {}).get("signature", "")),
                        "userHandle": (
                            base64url_to_bytes(cred.get("response", {}).get("userHandle", ""))
                            if cred.get("response", {}).get("userHandle")
                            else None
                        ),
                    },
                    "type": "public-key",
                },
                expected_challenge=base64url_to_bytes(challenge),
                expected_rp_id=rp_id,
                expected_origin=origin,
                credential_public_key=base64.b64decode(row["public_key_b64"]),
                credential_current_sign_count=int(row.get("sign_count") or 0),
            )
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

        row["sign_count"] = verified.new_sign_count
        _save_passkeys(settings.passkeys_path, stored)
        resp = JSONResponse({"ok": True})
        resp.set_cookie(
            SESSION_COOKIE,
            _sign_session(settings, settings.username),
            httponly=True,
            samesite="lax",
            max_age=SESSION_MAX_AGE_S,
            path="/",
        )
        return resp
