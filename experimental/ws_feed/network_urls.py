from __future__ import annotations

from urllib.parse import urlparse, urlunparse


def rpc_url_to_websocket_url(json_rpc_url: str) -> str:
    """
    rippled JSON-RPC is typically :51234 (https); WebSocket is :51233 (wss).
    """
    parsed = urlparse(json_rpc_url.strip())
    scheme = parsed.scheme.lower()
    if scheme in ("https", "http"):
        ws_scheme = "wss" if scheme == "https" else "ws"
    elif scheme in ("wss", "ws"):
        return json_rpc_url
    else:
        ws_scheme = "wss"

    host = parsed.hostname or parsed.netloc.split(":")[0]
    port = parsed.port
    if port in (51234, None):
        port = 51233
    netloc = f"{host}:{port}" if port else host
    return urlunparse((ws_scheme, netloc, parsed.path or "", "", "", ""))