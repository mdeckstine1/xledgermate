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
    @app.get("/", response_class=HTMLResponse)
    async def index():
        html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:;">
    <title>WS + Pure A-S Live HUD</title>
    <style>
        body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 0; display: flex; height: 100vh; overflow: hidden; }
        .sidebar { width: 260px; background: #1e2937; border-right: 1px solid #334155; padding: 16px; overflow-y: auto; flex-shrink: 0; }
        .sidebar .section { margin-bottom: 16px; }
        .sidebar .label { font-size: 0.7rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 2px; }
        .sidebar .value { font-size: 1rem; font-weight: 600; }
        .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        .marquee-container { background: #0f172a; border-bottom: 1px solid #334155; padding: 6px 12px; overflow: hidden; white-space: nowrap; }
        .marquee { display: inline-block; animation: marquee 60s linear infinite; font-size: 0.85rem; color: #cbd5e1; }
        @keyframes marquee { 0% { transform: translateX(100%); } 100% { transform: translateX(-100%); } }
        .marquee span.quote { color: #4ade80; font-weight: 500; }
        .marquee span.warn { color: #facc15; }
        .marquee span.danger { color: #f87171; }
        .marquee span.info { color: #60a5fa; }
        .header { font-size: 1.3rem; padding: 12px 16px; color: #60a5fa; background: #1e2937; border-bottom: 1px solid #334155; flex-shrink: 0; }
        .content { flex: 1; padding: 16px; overflow-y: auto; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
        .card { background: #1e2937; border-radius: 8px; padding: 12px; border: 1px solid #334155; }
        .label { font-size: 0.7rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }
        .value { font-size: 1.1rem; font-weight: 600; margin-top: 2px; }
        .good { color: #4ade80; }
        .warn { color: #facc15; }
        .bad { color: #f87171; }
        .note { font-family: ui-monospace, monospace; font-size: 0.8rem; background: #0f172a; padding: 6px; border-radius: 4px; white-space: pre-wrap; }
        .recent { max-height: 180px; overflow-y: auto; font-size: 0.75rem; }
        .metric-row { display: flex; justify-content: space-between; margin: 2px 0; font-size: 0.9rem; }
        .sidebar-value { font-size: 0.95rem; font-weight: 600; margin-top: 1px; }
        .nav { display: flex; gap: 12px; background: #1e2937; padding: 8px 16px; border-bottom: 1px solid #334155; flex-shrink: 0; }
        .nav a { color: #60a5fa; text-decoration: none; padding: 4px 10px; border-radius: 4px; font-size: 0.9rem; }
        .nav a:hover { background: #334155; }
        .nav a.active { background: #334155; font-weight: 500; }
        .page { display: none; }
        .page.active { display: block; }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="section">
            <div class="label">Balances</div>
            <div class="sidebar-value" id="sidebar-xrp">XRP: —</div>
            <div class="sidebar-value" id="sidebar-rlusd">RLUSD: —</div>
        </div>
        <div class="section">
            <div class="label">Inventory</div>
            <div class="sidebar-value" id="sidebar-inventory">—</div>
        </div>
        <div class="section">
            <div class="label">Profile (A-S tuning preset)</div>
            <select id="sidebar-profile-select" style="width:100%; font-size:0.85rem; margin-top:2px;">
                <option value="tight_spread">tight_spread (A-S tuned)</option>
                <option value="safe">safe</option>
                <option value="profit_mode">profit_mode</option>
                <option value="thin_liquidity">thin_liquidity</option>
            </select>
            <div class="sidebar-value" id="sidebar-profile" style="margin-top:2px;">—</div>
            <small style="font-size:0.6rem; opacity:0.7;">In pure A-S, profiles are mostly (γ, κ) tuning + size/toxicity overlays. No more hard gates.</small>
        </div>
        <div class="section">
            <div class="label">Status</div>
            <div class="sidebar-value" id="sidebar-would-quote">—</div>
        </div>
        <div class="section">
            <div class="label">Engine Controls (demo only)</div>
            <button id="btn-start-engine" style="width:100%; margin:2px 0; font-size:0.75rem;">▶ Start</button>
            <button id="btn-stop-engine" style="width:100%; margin:2px 0; font-size:0.75rem;">⏹ Stop</button>
            <button id="btn-restart-engine" style="width:100%; margin:2px 0; font-size:0.75rem;">↻ Restart</button>
            <small style="font-size:0.6rem; opacity:0.7;">Full controls in base Streamlit when loading the runtime JSON from tester.</small>
        </div>
        <div class="section">
            <div class="label">Credentials (demo)</div>
            <div style="font-size:0.75rem;">Address: <span id="creds-address">loaded from config</span></div>
            <form style="margin:0; padding:0;">
                <input type="text" id="sidebar-bot-address" name="bot-address" placeholder="Bot Address" value="r... (from config.yaml)" readonly style="width:100%; font-size:0.7rem; margin:2px 0;">
                <input type="password" id="sidebar-bot-secret" name="bot-secret" placeholder="Secret" value="********" readonly style="width:100%; font-size:0.7rem; margin:2px 0;">
            </form>
            <small style="font-size:0.6rem; opacity:0.7;">Edit config/credentials.local.yaml. Full entry form in main Streamlit GUI.</small>
        </div>
    </div>

    <div class="main">
        <div class="header">WS + Pure A-S — Live Strategy HUD <span id="mode" style="font-size:0.9rem; color:#64748b;"></span></div>

        <div class="nav">
            <a href="#" data-page="live" class="active">Live</a>
            <a href="#" data-page="config">Config</a>
            <a href="#" data-page="credentials">Credentials</a>
        </div>

        <div id="live" class="page active">
            <div class="marquee-container">
                <div class="marquee" id="marquee">PURE A-S active • WS book feed • loading decisions...</div>
            </div>
            <div id="hud-poll-status" style="font-size:0.65rem; color:#64748b; padding:2px 16px 6px; font-family: ui-monospace, monospace; background:#0f172a; display:inline-block;">polling /state every 800ms...</div>
            <button id="btn-force-poll" style="font-size:0.55rem; padding:1px 5px; margin-left:4px; vertical-align:middle; cursor:pointer;">↻</button>

            <div class="content">
                <div class="grid">
                    <div class="card">
                        <div class="label">Live Book (WS)</div>
                        <div id="book" class="value">—</div>
                        <div class="metric-row"><span class="label">Spread</span> <span id="spread" class="value">—</span></div>
                        <div class="metric-row"><span class="label">WS Age</span> <span id="age" class="value">—</span></div>
                        <div class="metric-row"><span class="label">WS Messages</span> <span id="msgs" class="value">—</span></div>
                    </div>

                    <div class="card">
                        <div class="label">Pure A-S Decision</div>
                        <div class="metric-row"><span class="label">Reservation</span> <span id="reservation" class="value">—</span></div>
                        <div class="metric-row"><span class="label">Optimal Spread</span> <span id="as_spread" class="value">—</span></div>
                        <div class="metric-row"><span class="label">Gamma / Kappa</span> <span id="params" class="value">—</span></div>
                        <div id="would_quote" class="value" style="margin-top:8px;">—</div>
                        <div id="base_gate" class="value" style="margin-top:4px; font-size:0.8rem;">—</div>
                    </div>

                    <div class="card">
                        <div class="label">Suggested Levels (near book)</div>
                        <div class="metric-row"><span class="label">Bid</span> <span id="bid" class="value good">—</span></div>
                        <div class="metric-row"><span class="label">Ask</span> <span id="ask" class="value">—</span></div>
                    </div>
                </div>

                <div class="card" style="margin-top:16px;">
                    <div class="label">Last Decision Note</div>
                    <div id="last_note" class="note">Waiting for first update...</div>
                </div>

                <div class="card" style="margin-top:16px;">
                    <div class="label">Recent Decisions (newest first)</div>
                    <div id="recent" class="recent"></div>
                </div>
            </div>
        </div>

        <div id="config" class="page">
            <div class="content">
                <h3 style="margin-top:0; color:#60a5fa;">Configuration</h3>
                <div class="card">
                    <div class="label">XRPL Ledger Address (Bot Account)</div>
                    <input type="text" id="config-ledger-address" value="r... (from config)" style="width:100%; margin:4px 0;">
                    <small>Used for the bot's XRPL account.</small>
                </div>
                <div class="card" style="margin-top:12px;">
                    <div class="label">Telegram Token</div>
                    <input type="text" id="config-telegram-token" value="123456:ABC-DEF..." style="width:100%; margin:4px 0;">
                    <small>For alerts (see monitoring/telegram_alerts.py).</small>
                </div>
                <div class="card" style="margin-top:12px;">
                    <div class="label">Other Config</div>
                    <div>Profile: <span id="config-profile">tight_spread</span></div>
                    <div>Min Order Size: 0.1 XRP (from config)</div>
                    <div>Inventory Target: 0.55 (from config)</div>
                    <small>Edit config/config.yaml for real changes. Full editing in main Streamlit GUI.</small>
                </div>
                <button id="btn-apply-config" style="margin-top:12px;">Apply Changes (demo)</button>
            </div>
        </div>

        <div id="credentials" class="page">
            <div class="content">
                <h3 style="margin-top:0; color:#60a5fa;">Credentials &amp; Keys</h3>
                <p style="font-size:0.85rem; color:#94a3b8;">Enter or update credentials here (demo only — changes are in-memory for this HUD session). For persistent storage and the full tabbed form, use the main Streamlit GUI and load the runtime JSON from the tester.</p>

                <div class="card">
                    <div class="label">XRPL Bot Account Address</div>
                    <input type="text" id="creds-xrpl-address" value="rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh" style="width:100%; margin:4px 0; font-family: monospace;">
                    <small>The XRPL account the bot will use for trading and signing.</small>
                </div>

                <div class="card" style="margin-top:12px;">
                    <div class="label">XRPL Account Secret (Seed)</div>
                    <form style="margin:0; padding:0;">
                        <input type="password" id="creds-xrpl-secret" value="sEd..." style="width:100%; margin:4px 0; font-family: monospace;">
                    </form>
                    <small>Never share this. Used to sign transactions on the ledger.</small>
                </div>

                <div class="card" style="margin-top:12px;">
                    <div class="label">Telegram Bot Token</div>
                    <input type="text" id="creds-telegram-token" value="123456:ABCDEF..." style="width:100%; margin:4px 0; font-family: monospace;">
                    <small>For sending alerts via Telegram (see monitoring/telegram_alerts.py).</small>
                </div>

                <div class="card" style="margin-top:12px;">
                    <div class="label">Additional Items / Keys</div>
                    <div class="label" style="margin-top:8px;">Telegram Chat ID (for alerts)</div>
                    <input type="text" id="creds-telegram-chat" value="-1001234567890" style="width:100%; margin:4px 0; font-family: monospace;">
                    <div class="label" style="margin-top:8px;">Other API Key (e.g. for secondary data / Anodos)</div>
                    <input type="text" id="creds-other-api" value="your-api-key-here" style="width:100%; margin:4px 0; font-family: monospace;">
                    <small>Any extra keys/tokens used by the WS path or external providers.</small>
                </div>

                <button id="btn-save-creds" style="margin-top:12px; padding:6px 12px;">Save Credentials (demo)</button>
                <small style="display:block; margin-top:4px; font-size:0.7rem; opacity:0.7;">This updates the HUD display only. For real runs, edit config/credentials.local.yaml and restart. Full secure form + validation is in the main Streamlit GUI.</small>
            </div>
        </div>
    </div>

    <script>
        let lastState = null;

        function setText(id, text) {
            const el = document.getElementById(id);
            if (el) el.textContent = text;
        }

        function renderLive(s) {
            if (!s) return;

            // Header mode badge (always present)
            const modeEl = document.getElementById('mode');
            if (modeEl) modeEl.textContent = s.as_mode ? `(${s.as_mode.toUpperCase()})` : '';

            // Sidebar (always present) - force update with defaults if missing
            setText('sidebar-xrp', s.balance_xrp !== undefined ? `XRP: ${parseFloat(s.balance_xrp).toFixed(2)}` : 'XRP: -');
            setText('sidebar-rlusd', s.balance_rlusd !== undefined ? `RLUSD: ${parseFloat(s.balance_rlusd).toFixed(2)}` : 'RLUSD: -');
            setText('sidebar-inventory', s.inventory_label || '-');
            const prof = s.active_profile || '-';
            setText('sidebar-profile', prof);
            const sel = document.getElementById('sidebar-profile-select');
            if (sel) sel.value = s.active_profile || '';
            const wqSide = document.getElementById('sidebar-would-quote');
            if (wqSide) {
                wqSide.textContent = s.would_quote ? 'WOULD QUOTE ✓' : 'NO QUOTE (protected)';
                wqSide.style.color = s.would_quote ? '#4ade80' : '#facc15';
            }

            // Live page cards - ALWAYS update the DOM values (visibility is controlled by CSS on #live container only)
            const bookEl = document.getElementById('book');
            if (bookEl) {
                if (s.best_bid && s.best_ask) {
                    bookEl.innerHTML = `${parseFloat(s.best_bid).toFixed(6)} / ${parseFloat(s.best_ask).toFixed(6)} <span style="font-size:0.7rem;color:#64748b;">mid ${parseFloat(s.mid || 0).toFixed(6)}</span>`;
                } else {
                    bookEl.textContent = '-';
                }
            }

            setText('spread', (s.book_spread_pct != null) ? parseFloat(s.book_spread_pct).toFixed(3) + '%' : '-');
            setText('age', (s.ws_age_s != null) ? parseFloat(s.ws_age_s).toFixed(1) + 's' : '-');
            setText('msgs', (s.ws_message_count != null) ? s.ws_message_count : '-');

            // A-S reservation + margins (guarded)
            const resEl = document.getElementById('reservation');
            if (resEl) {
                if (s.as_reservation != null) {
                    let html = parseFloat(s.as_reservation).toFixed(6);
                    if (s.best_bid && s.best_ask) {
                        const marginBid = (parseFloat(s.as_reservation) - parseFloat(s.best_bid)).toFixed(5);
                        const marginAsk = (parseFloat(s.best_ask) - parseFloat(s.as_reservation)).toFixed(5);
                        html += ` <span style="font-size:0.65rem; color:#64748b;">(bid margin ${marginBid} / ask ${marginAsk})</span>`;
                    }
                    resEl.innerHTML = html;
                } else {
                    resEl.textContent = '-';
                }
            }

            setText('as_spread', (s.as_optimal_spread_pct != null) ? parseFloat(s.as_optimal_spread_pct).toFixed(3) + '%' : '-');
            setText('params', (s.as_gamma != null && s.as_kappa != null) ? `${s.as_gamma} / ${s.as_kappa}` : '-');

            // BASE HARD GATE comparison (client-side, for demo visibility)
            const gateEl = document.getElementById('base_gate');
            if (gateEl && s.book_spread_pct != null) {
                const bookSpread = parseFloat(s.book_spread_pct);
                const wouldGateBlock = bookSpread < 0.10;
                gateEl.textContent = wouldGateBlock ? 'BASE HARD GATE: BLOCKED ✗' : 'BASE HARD GATE: WOULD ALLOW ✓';
                gateEl.style.color = wouldGateBlock ? '#f87171' : '#4ade80';
            }

            const wq = document.getElementById('would_quote');
            if (wq) {
                if (s.would_quote) {
                    wq.textContent = 'WOULD QUOTE (2 legs) ✓';
                    wq.className = 'value good';
                    wq.style.background = '#052e16';
                } else {
                    wq.textContent = 'NO QUOTE (A-S protection) ✗';
                    wq.className = 'value warn';
                    wq.style.background = '#3f1f1f';
                }
            }

            setText('bid', (s.suggested_bid != null) ? parseFloat(s.suggested_bid).toFixed(6) : '-');
            setText('ask', (s.suggested_ask != null) ? parseFloat(s.suggested_ask).toFixed(6) : '-');

            setText('last_note', s.last_note || 'Waiting for first WS update + A-S decision...');

            const recentEl = document.getElementById('recent');
            if (recentEl) {
                const notes = (s.recent_notes && s.recent_notes.length) ? s.recent_notes : (s.last_note ? [s.last_note] : []);
                recentEl.innerHTML = notes.map(n => `<div style="margin:2px 0;opacity:0.85;">${n}</div>`).join('');
            }

            // Marquee (slow scroll, color spans) - always keep fresh
            const marqueeEl = document.getElementById('marquee');
            if (marqueeEl) {
                let tickerText = `<span class="quote">PURE A-S active</span> - <span class="info">WS book feed</span>`;
                if (s.last_note) {
                    tickerText += ` - <span class="warn">${String(s.last_note).substring(0, 80)}</span>`;
                }
                if (s.recent_notes && s.recent_notes.length > 0) {
                    tickerText += ' - ' + s.recent_notes.slice(0, 1).map(n => `<span class="info">${String(n).substring(0,50)}</span>`).join(' - ');
                }
                marqueeEl.innerHTML = tickerText;
            }
        }

        async function poll() {
            const statusEl = document.getElementById('hud-poll-status');
            try {
                const res = await fetch('/state');
                if (!res.ok) throw new Error('bad status ' + res.status);
                const s = await res.json();
                lastState = s;

                renderLive(s);

                // Visible status so "no data / just the card" is never mysterious
                if (statusEl) {
                    const ts = new Date().toLocaleTimeString();
                    const age = (s.ws_age_s != null) ? s.ws_age_s.toFixed(1) + 's' : '?';
                    const msgs = (s.ws_message_count != null) ? s.ws_message_count : '?';
                    statusEl.textContent = `last poll: ${ts} - WS msgs: ${msgs} - book age: ${age} - server OK`;
                    statusEl.style.color = '#4ade80';
                }

                // Debug info in console (F12 → Console)
                console.log('[HUD] poll success, keys:', Object.keys(s || {}));
                if (s.last_note) console.log('[HUD] last_note preview:', String(s.last_note).substring(0, 120));
                if (!window.__hudFirst) {
                    window.__hudFirst = true;
                    console.log('[HUD] first data received from /state', Object.keys(s || {}));
                }
            } catch (e) {
                console.error('[HUD] poll error', e);
                if (statusEl) {
                    statusEl.textContent = 'POLL FAILED - cannot reach /state on 8765. Is the tester running with --serve-hud? (only ONE instance can bind the port)';
                    statusEl.style.color = '#f87171';
                }
            }
            setTimeout(poll, 800);
        }

        function showPage(page) {
            // Flip page visibility
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            const target = document.getElementById(page);
            if (target) target.classList.add('active');

            // Activate correct nav link using data-page (reliable)
            document.querySelectorAll('.nav a').forEach(a => {
                a.classList.remove('active');
                if (a.getAttribute('data-page') === page) a.classList.add('active');
            });

            // Immediately push last known data into the now-visible elements (no waiting for next poll tick)
            if (lastState) {
                renderLive(lastState);
            }
        }

        function saveCredentialsDemo() {
            const xrplAddr = document.getElementById('creds-xrpl-address').value || '';
            const xrplSecret = document.getElementById('creds-xrpl-secret').value || '';
            const tgToken = document.getElementById('creds-telegram-token').value || '';
            const tgChat = document.getElementById('creds-telegram-chat').value || '';
            const otherApi = document.getElementById('creds-other-api').value || '';

            const addrEl = document.getElementById('creds-address');
            if (addrEl) addrEl.textContent = xrplAddr ? (xrplAddr.substring(0, 8) + '... (demo updated)') : 'updated in demo';

            if (window._current_state) {
                window._current_state.creds_xrpl_address = xrplAddr;
                window._current_state.creds_xrpl_secret = xrplSecret ? '********' : '';
                window._current_state.creds_telegram_token = tgToken;
                window._current_state.creds_telegram_chat = tgChat;
                window._current_state.creds_other_api = otherApi;
            }

            alert('Credentials & keys saved in this demo HUD session (in-memory only for this run).\n\n' +
                  'XRPL Bot Account Address: ' + (xrplAddr || '(empty)') + '\n' +
                  'XRPL Secret: ' + (xrplSecret ? '******** (hidden for security)' : '(empty)') + '\n' +
                  'Telegram Bot Token: ' + (tgToken || '(empty)') + '\n' +
                  'Telegram Chat ID: ' + (tgChat || '(empty)') + '\n' +
                  'Other API Key: ' + (otherApi || '(empty)') + '\n\n' +
                  'These are now reflected in the HUD (e.g. sidebar address).\n' +
                  'For real/persistent use: edit config/credentials.local.yaml (never commit secrets!) and restart the tester.\n' +
                  'The main Streamlit GUI (load the ws_as_demo_runtime.json) has the full interactive tabbed forms for entering and managing all credentials and keys securely.');
        }

        function attachDemoHandlers() {
            // Engine control buttons (demo alerts only)
            const startBtn = document.getElementById('btn-start-engine');
            if (startBtn) {
                startBtn.addEventListener('click', () => {
                    alert('Start Engine - demo only. Use main Streamlit GUI + load ws_as_demo_runtime.json for full interactive controls, sidebar, and tickers.');
                });
            }
            const stopBtn = document.getElementById('btn-stop-engine');
            if (stopBtn) {
                stopBtn.addEventListener('click', () => {
                    alert('Stop Engine - demo only.');
                });
            }
            const restartBtn = document.getElementById('btn-restart-engine');
            if (restartBtn) {
                restartBtn.addEventListener('click', () => {
                    alert('Restart Engine - demo only.');
                });
            }

            // Profile select (demo only)
            const profileSel = document.getElementById('sidebar-profile-select');
            if (profileSel) {
                profileSel.addEventListener('change', () => {
                    const prof = document.getElementById('sidebar-profile');
                    if (prof) {
                        prof.textContent = profileSel.value + ' (demo - restart tester with different --profile to use)';
                    }
                });
            }

            // Config apply button (demo)
            const applyBtn = document.getElementById('btn-apply-config');
            if (applyBtn) {
                applyBtn.addEventListener('click', () => {
                    alert('Config saved (demo). In real use, this would update the running tester or config files. Restart tester to apply.');
                });
            }

            // Credentials save button
            const saveBtn = document.getElementById('btn-save-creds');
            if (saveBtn) {
                saveBtn.addEventListener('click', saveCredentialsDemo);
            }
        }

        // Boot: attach nav (data-page driven), show Live, kick off immediate poll + recurring
        function bootHud() {
            // Nav clicks
            document.querySelectorAll('.nav a').forEach(link => {
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    const page = link.getAttribute('data-page') || link.textContent.toLowerCase().trim();
                    showPage(page);
                });
            });

            // Attach the remaining demo-only button / select handlers (removes inline onclick/onchange)
            attachDemoHandlers();

            // Start on Live page (ensure class is set even if HTML had it)
            showPage('live');

            // Attach force poll button
            const forceBtn = document.getElementById('btn-force-poll');
            if (forceBtn) {
                forceBtn.addEventListener('click', () => {
                    const st = document.getElementById('hud-poll-status');
                    if (st) {
                        st.textContent = 'fetching...';
                        st.style.color = '#64748b';
                    }
                    poll();
                });
            }

            // Immediate status feedback
            const statusEl = document.getElementById('hud-poll-status');
            if (statusEl) {
                statusEl.textContent = 'connecting...';
                statusEl.style.color = '#64748b';
            }

            // Fire first poll immediately so data appears as soon as server has state
            poll();

            // Extra safety kick in case first fetch was racing server startup
            setTimeout(() => {
                if (!lastState) {
                    // one more fast attempt
                    poll();
                }
            }, 250);
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', bootHud);
        } else {
            bootHud();
        }
    </script>
</body>
</html>
        """
        resp = HTMLResponse(html)
        resp.headers["Content-Security-Policy"] = "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:;"
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
        print("   IMPORTANT: After editing real_time_as_hud.py you MUST restart this tester process to serve the updated HTML/JS.")
        return server
    else:
        print(f"[HUD] Starting real-time A-S HUD on http://{host}:{port}")
        server.run()
        return server


if __name__ == "__main__":
    run_hud(background=False)
