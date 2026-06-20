
        let lastState = null;
        let pinnedIntelAiResult = null;  // keep full Grok analysis across /state polls
        let competitorNicknames = {};
        const HUD_BUILD = '__HUD_BUILD__';

        function ensureCacheBustUrl() {
            if (!HUD_BUILD || HUD_BUILD.indexOf('__HUD_BUILD__') >= 0) return;
            const params = new URLSearchParams(window.location.search);
            if (params.get('b') === HUD_BUILD) return;
            params.set('b', HUD_BUILD);
            window.location.replace(window.location.pathname + '?' + params.toString());
        }

        function applyProductionLabels() {
            const ladderLabel = document.getElementById('ladder-card-label');
            if (ladderLabel) ladderLabel.textContent = 'Quote ladder (L1???L3)';
            document.querySelectorAll('.label').forEach(el => {
                if (el.textContent.trim() === 'Suggested Levels (near book)') {
                    el.textContent = 'Quote ladder (L1???L3)';
                }
            });
        }

        function pollBookAgeSource(s) {
            return (s && s.ws_book_last_update_unix != null) ? 'WS tick' : 'last cycle';
        }

        /** Seconds since last book mutation; ticks up live when ws_book_last_update_unix is set. */
        function computeLiveWsAge(s) {
            if (!s) return null;
            const unix = s.ws_book_last_update_unix;
            if (unix != null && !isNaN(parseFloat(unix))) {
                return Math.max(0, Date.now() / 1000 - parseFloat(unix));
            }
            if (s.ws_age_s != null && !isNaN(parseFloat(s.ws_age_s))) {
                return Math.max(0, parseFloat(s.ws_age_s));
            }
            return null;
        }

        function formatWsAge(s) {
            const age = computeLiveWsAge(s);
            return (age != null) ? age.toFixed(1) + 's' : '-';
        }

        function wsAgeColor(age) {
            if (age == null) return '#e2e8f0';
            if (age < 5) return '#4ade80';
            if (age < 12) return '#facc15';
            return '#f87171';
        }
        let lastMid = null;
        let lastMidDirectionStyle = 'color:#e2e8f0; font-weight:600;';
        let lastDirectionArrow = '';
        let prevValues = {};

        function triggerAnim(el, className, durationMs = 500) {
            if (!el) return;
            el.classList.add(className);
            setTimeout(() => el.classList.remove(className), durationMs);
        }

        function setText(id, text) {
            const el = document.getElementById(id);
            if (el) el.textContent = text;
        }

        /** Shared peer/competitor row list ??? Intelligence + Peer Cal tabs. */
        function renderMakerPeerList(listEl, rows, emptyMsg, s, clickTargets) {
            if (!listEl) return;
            const targets = clickTargets || {};
            if (!rows || !rows.length) {
                listEl.innerHTML = emptyMsg;
                return;
            }
            const nicks = (s && s.competitor_nicknames && typeof s.competitor_nicknames === 'object')
                ? s.competitor_nicknames
                : competitorNicknames;
            listEl.innerHTML = rows.map(c => {
                const full = c.account_full || c.account;
                const nick = c.nickname || nicks[full] || '';
                const base = c.domain && c.domain !== 'no-domain' ? `${c.account} (${c.domain})` : c.account;
                const display = nick ? `${nick} ?? ${base}` : base;
                const touch = c.touch_xrp != null && c.touch_xrp > 0 ? ` | touch:${c.touch_xrp}XRP` : '';
                const fled = c.cancels != null && c.cancels > 0 ? ` | cancels:${c.cancels}` : '';
                const spread = (c.last_spread != null && c.avg_spread != null)
                    ? ` | ${c.last_spread}% / ${c.avg_spread}%`
                    : '';
                const act = c.activity != null ? ` | act:${c.activity}` : '';
                const sides = c.sides ? ` | ${c.sides}` : '';
                return `<div data-full="${full}" style="cursor:pointer; padding:2px 0;" title="Click to use this address">${display}${spread}${act}${sides}${touch}${fled}</div>`;
            }).join('');
            listEl.querySelectorAll('div[data-full]').forEach(row => {
                row.onclick = () => {
                    const fullAddr = row.getAttribute('data-full') || '';
                    const analyzeInput = document.getElementById(targets.analyzeInputId || 'intel-analyze-addr');
                    const nickInput = document.getElementById(targets.nickInputId || 'nick-address');
                    if (analyzeInput) analyzeInput.value = fullAddr;
                    if (nickInput) nickInput.value = fullAddr;
                    const analyzeBtn = document.getElementById(targets.analyzeBtnId || 'btn-analyze-addr');
                    if (analyzeBtn) {
                        analyzeBtn.style.boxShadow = '0 0 0 3px #8b5cf6';
                        setTimeout(() => { if (analyzeBtn) analyzeBtn.style.boxShadow = ''; }, 800);
                    }
                };
            });
        }

        function renderPeerCal(s) {
            if (!s) return;
            const assumption = s.shadow_e3_assumption || '11000_xrp_equiv_55_45_balanced';
            const shadowLane = s.shadow_e3_lane_xrp;
            setText('cal-assumption-badge', `Assumption: ${assumption.replace(/_/g, ' ')} ?? shadow L1 ??? ${shadowLane != null ? parseFloat(shadowLane).toFixed(1) : '???'} XRP`);

            const liveLane = s.our_lane_xrp != null ? parseFloat(s.our_lane_xrp) : null;
            setText('cal-live-lane', liveLane != null ? `${liveLane.toFixed(1)} XRP` : '???');
            setText('cal-live-band', (s.peer_lane_low_xrp != null && s.peer_lane_high_xrp != null)
                ? `${parseFloat(s.peer_lane_low_xrp).toFixed(0)}???${parseFloat(s.peer_lane_high_xrp).toFixed(0)} XRP`
                : '???');
            setText('cal-live-count', s.peer_lane_count != null ? String(s.peer_lane_count) : '???');
            setText('cal-live-pressure', s.peer_pressure_score != null
                ? parseFloat(s.peer_pressure_score).toFixed(2)
                : (s.peer_lane_count > 0 ? '???' : 'n/a'));
            setText('cal-live-g4', s.live_g4_active ? 'yes' : (s.peer_lane_count > 0 ? 'yes' : 'no (empty lane)'));

            setText('cal-shadow-lane', shadowLane != null ? `${parseFloat(shadowLane).toFixed(1)} XRP` : '???');
            setText('cal-shadow-band', (s.shadow_peer_lane_low_xrp != null && s.shadow_peer_lane_high_xrp != null)
                ? `${parseFloat(s.shadow_peer_lane_low_xrp).toFixed(0)}???${parseFloat(s.shadow_peer_lane_high_xrp).toFixed(0)} XRP`
                : '???');
            const sc = s.shadow_peer_lane_count != null ? s.shadow_peer_lane_count : '???';
            const widened = s.shadow_peer_lane_widened ? ' (widened)' : '';
            setText('cal-shadow-count', `${sc}${widened}`);
            setText('cal-shadow-pressure', s.shadow_peer_pressure_score != null
                ? parseFloat(s.shadow_peer_pressure_score).toFixed(2)
                : '???');
            setText('cal-shadow-g4', s.shadow_g4_would_activate ? 'yes' : 'no');
            const delta = s.live_vs_shadow_delta_peers;
            setText('cal-delta-peers', delta != null ? (delta >= 0 ? `+${delta}` : String(delta)) : '???');

            const partialNote = s.shadow_peer_lane_note || 'Partial: top scrape lists only.';
            const partialEl = document.getElementById('cal-partial-note');
            if (partialEl) partialEl.textContent = partialNote;

            const shadowRows = (s.shadow_top_peers && s.shadow_top_peers.length) ? s.shadow_top_peers : null;
            const liveRows = (s.top_peers && s.top_peers.length) ? s.top_peers : null;
            const shadowBand = (s.shadow_peer_lane_low_xrp != null && s.shadow_peer_lane_high_xrp != null)
                ? `${parseFloat(s.shadow_peer_lane_low_xrp).toFixed(0)}???${parseFloat(s.shadow_peer_lane_high_xrp).toFixed(0)} XRP`
                : 'band';
            renderMakerPeerList(
                document.getElementById('cal-shadow-peer-list-inner'),
                shadowRows,
                `No shadow peers in E3 band (${shadowBand}). Whales in book-wide list are outside this ruler.`,
                s,
                { analyzeInputId: 'cal-analyze-addr', nickInputId: 'cal-nick-address', analyzeBtnId: 'btn-cal-analyze' }
            );
            const liveBand = (s.peer_lane_low_xrp != null && s.peer_lane_high_xrp != null)
                ? `${parseFloat(s.peer_lane_low_xrp).toFixed(0)}???${parseFloat(s.peer_lane_high_xrp).toFixed(0)} XRP`
                : 'band';
            renderMakerPeerList(
                document.getElementById('cal-live-peer-list-inner'),
                liveRows,
                `No live peers (${liveBand} around ${liveLane != null ? liveLane.toFixed(1) : 'pilot'} XRP). Expected at pilot size.`,
                s,
                { analyzeInputId: 'cal-analyze-addr', nickInputId: 'cal-nick-address', analyzeBtnId: 'btn-cal-analyze' }
            );
        }

        function portfolioValueRlusd(s) {
            const midRaw = s.mid_price != null ? s.mid_price : s.mid_rlusd_per_xrp;
            const mid = midRaw != null ? parseFloat(midRaw) : NaN;
            const portXrp = s.portfolio_value_xrp != null ? parseFloat(s.portfolio_value_xrp) : NaN;
            if (!Number.isNaN(portXrp) && !Number.isNaN(mid) && mid > 0) {
                return portXrp * mid;
            }
            const xrp = s.balance_xrp != null ? parseFloat(s.balance_xrp) : NaN;
            const rlusd = s.balance_rlusd != null ? parseFloat(s.balance_rlusd) : NaN;
            if (!Number.isNaN(xrp) && !Number.isNaN(rlusd) && !Number.isNaN(mid) && mid > 0) {
                return rlusd + xrp * mid;
            }
            return null;
        }

        function formatPortfolioUsd(rlusdTotal) {
            if (rlusdTotal == null || Number.isNaN(rlusdTotal)) return null;
            return rlusdTotal.toLocaleString('en-US', {
                style: 'currency',
                currency: 'USD',
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            });
        }

        async function applyIntelConfigFromForm() {
            const provEl = document.getElementById('intel-ai-provider');
            const keyIn = document.getElementById('intel-ai-key');
            const modelEl = document.getElementById('intel-ai-model');
            const enEl = document.getElementById('intel-ai-enabled');
            let provider = provEl ? provEl.value : 'grok';
            const keyVal = keyIn ? keyIn.value : '';
            const model = modelEl ? modelEl.value : 'grok-3';
            const enabled = !!(enEl && enEl.checked);
            if (keyVal && provider === 'stub') provider = 'grok';
            if (!keyVal) return { ok: false, had_key: false };
            await fetch('/set_intel_config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider, key: keyVal, model, enabled }),
            });
            return { ok: true, had_key: true, provider };
        }

        // === Model discovery helpers (for Grok /list_models) ===
        // Defined early so they are available even if other code has timing issues.
        async function fetchAvailableModels() {
            const resDiv = document.getElementById('model-list-result');
            if (!resDiv) return;

            // Auto-apply current Config values so the key is in server state
            const provEl = document.getElementById('intel-ai-provider');
            const keyIn = document.getElementById('intel-ai-key');
            const modelEl = document.getElementById('intel-ai-model');
            const enEl = document.getElementById('intel-ai-enabled');

            const provider = provEl ? provEl.value : 'grok';
            const keyVal = keyIn ? keyIn.value : '';
            const model = modelEl ? modelEl.value : 'grok-3';
            const enabled = !!(enEl && enEl.checked);

            if (keyVal) {
                try {
                    await fetch('/set_intel_config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ provider, key: keyVal, model, enabled })
                    });
                    const aiKeyWrap = keyIn ? keyIn.parentElement : null;
                    if (keyIn && aiKeyWrap) {
                        keyIn.style.display = 'none';
                        let status = document.getElementById('intel-ai-key-status');
                        if (!status) {
                            status = document.createElement('span');
                            status.id = 'intel-ai-key-status';
                            status.style.fontSize = '0.75rem';
                            status.style.color = '#22c55e';
                            status.style.marginLeft = '6px';
                            aiKeyWrap.appendChild(status);
                        }
                        status.textContent = 'Key set (hidden for security) ??? length: ' + keyVal.length + ' (applied for model fetch)';
                    }
                } catch (e) {
                    console.warn('Auto-apply before model fetch failed', e);
                }
            }

            resDiv.textContent = 'Querying xAI /v1/models with the applied key...';
            try {
                const r = await fetch('/list_models');
                const data = await r.json();
                if (data.error) {
                    resDiv.innerHTML = '<span style="color:#f87171">Error: ' + data.error + '</span>';
                } else if (data.models && data.models.length > 0) {
                    // Always ensure grok-3 is available as a strong recommendation
                    let models = [...data.models];
                    if (!models.includes('grok-3')) {
                        models.unshift('grok-3');
                    }
                    // Put grok-3 first if present
                    models = models.filter(m => m !== 'grok-3');
                    models.unshift('grok-3');

                    let options = models.map(m => {
                        const label = m === 'grok-3' ? 'grok-3 (recommended)' : m;
                        return `<option value="${m}">${label}</option>`;
                    }).join('');

                    resDiv.innerHTML = (data.note ? data.note + '<br>' : '') + 
                        'Select model (auto-applies on change):<br>' +
                        `<select id="temp-model-select" style="width:100%; font-size:0.8rem; margin-top:4px;">${options}</select>`;

                    // Attach change handler after DOM update
                    setTimeout(() => {
                        const sel = document.getElementById('temp-model-select');
                        if (sel) {
                            sel.addEventListener('change', () => {
                                if (sel.value) {
                                    useModel(sel.value);
                                }
                            });
                            // Pre-select grok-3
                            sel.value = 'grok-3';
                        }
                    }, 0);
                } else {
                    resDiv.innerHTML = 'No models from API. <button onclick="useModel(\'grok-3\')">Try grok-3 (recommended)</button>';
                }
            } catch (e) {
                resDiv.innerHTML = '<span style="color:#f87171">Fetch failed: ' + e + '</span>';
            }
        }

        function useModel(modelName) {
            const modelInput = document.getElementById('intel-ai-model');
            if (modelInput) {
                modelInput.value = modelName;
                modelInput.style.background = '#1e40af';
                setTimeout(() => { if (modelInput) modelInput.style.background = ''; }, 600);
            }
            const applyBtn = document.getElementById('btn-apply-config');
            if (applyBtn) {
                applyBtn.click();
            } else {
                const provEl = document.getElementById('intel-ai-provider');
                const keyIn = document.getElementById('intel-ai-key');
                const enEl = document.getElementById('intel-ai-enabled');
                fetch('/set_intel_config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        provider: provEl ? provEl.value : 'grok',
                        key: keyIn ? keyIn.value : '',
                        model: modelName,
                        enabled: !!(enEl && enEl.checked)
                    })
                });
            }
        }

        window.fetchAvailableModels = fetchAvailableModels;
        window.useModel = useModel;

        function _intentByLevel(intents, level, side) {
            if (!intents || !Array.isArray(intents)) return null;
            return intents.find(i => (i.level || 1) === level && i.side === side) || null;
        }

        function _formatLadderPrice(price) {
            return (price != null && !isNaN(parseFloat(price))) ? parseFloat(price).toFixed(6) : '???';
        }

        function _formatLadderSize(size) {
            return (size != null && !isNaN(parseFloat(size))) ? parseFloat(size).toFixed(1) + ' XRP' : '???';
        }

        function _levelCommitText(intents, level) {
            const bid = _intentByLevel(intents, level, 'bid');
            const ask = _intentByLevel(intents, level, 'ask');
            if (!bid && !ask) return '???';
            const b = bid && bid.size_xrp != null ? parseFloat(bid.size_xrp).toFixed(1) : '???';
            const a = ask && ask.size_xrp != null ? parseFloat(ask.size_xrp).toFixed(1) : '???';
            return `bid ${b} / ask ${a} XRP`;
        }

        function _laneTouchValue(s, level, stateKey) {
            const intents = (s.quote_intents && Array.isArray(s.quote_intents)) ? s.quote_intents : [];
            let v = stateKey && s[stateKey] != null ? parseFloat(s[stateKey]) : null;
            if ((v == null || Number.isNaN(v)) && intents.length) {
                const bid = _intentByLevel(intents, level, 'bid');
                const ask = _intentByLevel(intents, level, 'ask');
                const sizes = [];
                if (bid && bid.size_xrp != null) sizes.push(parseFloat(bid.size_xrp));
                if (ask && ask.size_xrp != null) sizes.push(parseFloat(ask.size_xrp));
                if (sizes.length) v = Math.max(...sizes);
            }
            if (level === 1 && (v == null || Number.isNaN(v)) && s.our_lane_xrp != null) {
                v = parseFloat(s.our_lane_xrp);
            }
            if ((v == null || Number.isNaN(v)) && level >= 2) {
                const l1 = _laneTouchValue(s, 1, 'our_lane_xrp');
                const fracs = [1.0, 0.6, 0.3];
                if (l1 != null && !Number.isNaN(l1) && fracs[level - 1]) {
                    v = l1 * fracs[level - 1];
                }
            }
            return (v == null || Number.isNaN(v)) ? null : v;
        }

        function _findIntelProfile(addr, state, shadowMode) {
            if (!state || !addr) return null;
            const q = String(addr).trim().toLowerCase();
            if (q.length < 8) return null;
            const bot = String(state.bot_account_address || state.bot_address || '').trim().toLowerCase();
            if (bot.length >= 25 && (bot === q || bot.startsWith(q) || q.startsWith(bot))) {
                const lane = shadowMode && state.shadow_e3_lane_xrp != null
                    ? parseFloat(state.shadow_e3_lane_xrp)
                    : (state.our_lane_xrp != null ? parseFloat(state.our_lane_xrp) : 0);
                return {
                    account: bot.slice(0, 12) + '...',
                    account_full: state.bot_account_address || state.bot_address,
                    touch_xrp: lane,
                    last_spread: state.book_spread_pct != null ? state.book_spread_pct : state.as_optimal_spread_pct,
                    activity: state.open_offers_count,
                    cancels: state.cancel_per_fill,
                    domain: 'our-bot',
                    is_self: true,
                };
            }
            const lists = shadowMode
                ? [state.shadow_top_peers, state.top_peers, state.top_competitors]
                : [state.top_peers, state.top_competitors];
            for (const list of lists) {
                if (!list || !Array.isArray(list)) continue;
                for (const row of list) {
                    if (!row) continue;
                    const full = String(row.account_full || row.account || '').toLowerCase();
                    const short = full.replace(/\.\.\.$/, '').slice(0, 12);
                    if (full && (full === q || full.startsWith(q) || q.startsWith(full))) return row;
                    if (short.length >= 8 && (q.startsWith(short) || short.startsWith(q.slice(0, 12)))) return row;
                }
            }
            return null;
        }

        function _formatLaneTouch(s, level, stateKey) {
            const v = _laneTouchValue(s, level, stateKey);
            if (v == null) return '???';
            const intents = (s.quote_intents && Array.isArray(s.quote_intents)) ? s.quote_intents : [];
            const bid = _intentByLevel(intents, level, 'bid');
            const ask = _intentByLevel(intents, level, 'ask');
            const planned = level > 1 || (bid && bid.planned) || (ask && ask.planned);
            return `${v.toFixed(1)} XRP${planned ? ' (planned)' : ''}`;
        }

        function renderSuggestedLadder(s) {
            const el = document.getElementById('suggested-ladder');
            const hint = document.getElementById('ladder-hint');
            if (!el) return;

            const levels = Math.max(1, parseInt(s.order_levels, 10) || 3);
            const intents = (s.quote_intents && Array.isArray(s.quote_intents)) ? s.quote_intents : [];
            const active = !!s.would_quote;
            let html = '';

            if (!intents.length) {
                const bidP = _formatLadderPrice(s.suggested_bid);
                const askP = _formatLadderPrice(s.suggested_ask);
                html += `<div class="ladder-level inactive">
                    <div class="ladder-level-tag">L1</div>
                    <div class="metric-row"><span class="label">Bid</span><span class="value good">${bidP}<span class="ladder-size">?? ???</span></span></div>
                    <div class="metric-row"><span class="label">Ask</span><span class="value">${askP}<span class="ladder-size">?? ???</span></span></div>
                </div>`;
                for (let lv = 2; lv <= levels; lv++) {
                    html += `<div class="ladder-level planned inactive">
                        <div class="ladder-level-tag">L${lv}</div>
                        <div class="metric-row"><span class="label">Bid</span><span class="value good">???<span class="ladder-size">?? ???</span></span></div>
                        <div class="metric-row"><span class="label">Ask</span><span class="value">???<span class="ladder-size">?? ???</span></span></div>
                    </div>`;
                }
            } else {
                for (let lv = 1; lv <= levels; lv++) {
                    const bid = _intentByLevel(intents, lv, 'bid');
                    const ask = _intentByLevel(intents, lv, 'ask');
                    const planned = lv > 1 || (bid && bid.planned) || (ask && ask.planned) || (!active && lv === 1);
                    const cls = ['ladder-level'];
                    if (planned) cls.push('planned');
                    if (!active && lv === 1) cls.push('inactive');
                    html += `<div class="${cls.join(' ')}">
                        <div class="ladder-level-tag">L${lv}</div>
                        <div class="metric-row"><span class="label">Bid</span><span class="value good">${_formatLadderPrice(bid && bid.price)}<span class="ladder-size">?? ${_formatLadderSize(bid && bid.size_xrp)}</span></span></div>
                        <div class="metric-row"><span class="label">Ask</span><span class="value">${_formatLadderPrice(ask && ask.price)}<span class="ladder-size">?? ${_formatLadderSize(ask && ask.size_xrp)}</span></span></div>
                    </div>`;
                }
            }

            const ladderKey = JSON.stringify({ active, intents: intents.slice(0, 12) });
            const ladderChanged = prevValues.ladder !== ladderKey;
            prevValues.ladder = ladderKey;
            el.innerHTML = html;
            if (ladderChanged) triggerAnim(el.closest('.card') || el, 'card-updated', 400);

            if (hint) {
                if (!intents.length) {
                    hint.textContent = 'Waiting for first quote cycle???';
                } else if (active) {
                    hint.textContent = 'L1 live on ledger. L2/L3 are planned depth (config sizes; WS path places L1 today).';
                } else {
                    hint.textContent = 'No live quotes ??? reservation outside book or inventory pause.';
                }
            }
        }

        function quoteStatusCopy(s) {
            const prod = isProductionHud(s);
            const quoting = !!s.would_quote;
            const offers = (s.open_offers_count != null) ? parseInt(s.open_offers_count, 10) : 0;
            if (prod) {
                if (quoting) {
                    return {
                        headline: offers > 0 ? `QUOTING ??? ${offers} offer(s) on ledger ???` : 'QUOTING ??? placing offers ???',
                        short: 'QUOTING ???',
                        posture: offers > 0 ? `${offers} resting ?? cycle active` : 'cycle active ?? syncing offers',
                        good: true,
                    };
                }
                return {
                    headline: offers > 0 ? `PAUSED ??? ${offers} offer(s) still on ledger` : 'PAUSED ??? no live quotes',
                    short: 'PAUSED',
                    posture: offers > 0 ? `${offers} resting ?? cycle blocked` : 'reservation outside book or inventory pause',
                    good: false,
                };
            }
            if (quoting) {
                return {
                    headline: 'WOULD QUOTE (2 legs) ???',
                    short: 'WOULD QUOTE ???',
                    posture: 'lab ??? simulated quote',
                    good: true,
                };
            }
            return {
                headline: 'NO QUOTE (A-S protection) ???',
                short: 'NO QUOTE',
                posture: 'lab ??? protection active',
                good: false,
            };
        }

        function soakPillClass(el, kind) {
            if (!el) return;
            el.classList.remove('good', 'warn', 'bad', 'neutral');
            el.classList.add(kind || 'neutral');
        }

        function g6VersionShort(v) {
            if (v == null || v === '') return '';
            const s = String(v).replace(/^v/i, '');
            const parts = s.split('.');
            if (parts.length >= 2) return 'v' + parts[0] + '.' + parts[1];
            return 'v' + s;
        }

        function resolveG6Fields(s) {
            const pm = (s && s.performance_metrics) || {};
            const act = pm.activation || {};
            return {
                version: (s && s.g6_version) || act.g6_version || pm.g6_version || '',
                tier: (s && s.g6_activation_tier) || act.tier || '',
                gatePass: (s && s.g6_gate_pass != null) ? s.g6_gate_pass : act.gate_pass,
                summary: (s && s.g6_activation_summary) || act.summary || '',
            };
        }

        function g6TierPillClass(tier) {
            const t = String(tier || 'unknown');
            if (t === 'active' || t === 'scale_ready' || t === 'pilot') return 'good';
            if (t === 'hold') return 'hold';
            if (t === 'halted') return 'halted';
            if (t === 'thin_edge' || t === 'pilot_watch') return 'watch';
            if (t === 'warming_up' || t === 'paper') return 'neutral';
            return 'unknown';
        }

        function escapeHudHtml(str) {
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
        }

        function safeNum(v, fallback) {
            const n = parseFloat(v);
            return Number.isFinite(n) ? n : fallback;
        }

        function g6SoakPillClass(tier) {
            const t = String(tier || '');
            if (t === 'active' || t === 'scale_ready') return 'good';
            if (t === 'thin_edge' || t === 'pilot_watch' || t === 'pilot') return 'warn';
            if (t === 'hold' || t === 'halted') return 'bad';
            return 'neutral';
        }

        function spotMidChangePct(s) {
            const mid = sessionMid(s);
            const bm = s.session_baseline_mid != null ? parseFloat(s.session_baseline_mid) : NaN;
            if (mid == null || Number.isNaN(bm) || bm <= 0) return null;
            return 100 * (mid - bm) / bm;
        }

        function g2MarqueeKind(s) {
            const grade = String(s.g2_grade || 'neutral').toLowerCase();
            const sm = s.g2_spread_mult != null ? parseFloat(s.g2_spread_mult) : 1.0;
            if (grade === 'defensive' || grade === 'stressed' || sm > 1.15) return 'danger';
            if (grade === 'cautious' || sm > 1.0) return 'warn';
            if (grade === 'ok' || grade === 'neutral') return 'quote';
            return 'info';
        }

        function g2MarqueeText(s) {
            const grade = s.g2_grade || 'neutral';
            const sm = safeNum(s.g2_spread_mult, 1.0);
            if (grade === 'ok' || (grade === 'neutral' && sm <= 1.0)) return 'G2 ok';
            if (sm > 1.0) return `G2 ${grade} spread x${sm.toFixed(2)}`;
            return `G2 ${grade}`;
        }

        function g6MarqueeKind(tier) {
            const t = String(tier || '');
            if (t === 'hold' || t === 'halted') return 'danger';
            if (t === 'thin_edge' || t === 'pilot_watch' || t === 'warming_up') return 'warn';
            if (t === 'active' || t === 'scale_ready' || t === 'pilot') return 'quote';
            return 'info';
        }

        function g7MarqueeText(s) {
            const bid = s.g7_bid_role || '???';
            const ask = s.g7_ask_role || '???';
            let parts = [`G7 bid ${bid} ?? ask ${ask}`];
            if (s.g7_solo_acquisition) parts.push('solo acquire');
            if (s.g7_ask_sell_defense) parts.push('ask defense');
            return parts.join(' ?? ');
        }

        function g7MarqueeKind(s) {
            if (s.g7_ask_sell_defense) return 'warn';
            if (s.g7_solo_acquisition) return 'quote';
            return 'info';
        }

        function spotMarqueeText(s) {
            const mid = sessionMid(s);
            const spotPct = spotMidChangePct(s);
            const spotR = spotDeltaRlusd(s);
            if (mid == null) return 'XRP spot: ???';
            let line = `XRP ${mid.toFixed(4)} RLUSD`;
            if (spotPct != null && !Number.isNaN(spotPct)) {
                const sign = spotPct >= 0 ? '+' : '';
                line += ` ?? ??mid ${sign}${spotPct.toFixed(2)}%`;
            }
            if (spotR != null && !Number.isNaN(spotR)) {
                const sign = spotR >= 0 ? '+' : '';
                line += ` ?? spot ${sign}${spotR.toFixed(2)} RLUSD`;
            }
            return line;
        }

        function spotMarqueeKind(s) {
            const spotR = spotDeltaRlusd(s);
            if (spotR == null || Number.isNaN(spotR)) return 'info';
            if (spotR > 0.05) return 'quote';
            if (spotR < -0.05) return 'warn';
            return 'info';
        }

        function buildOperatorMarqueeHtml(s) {
            const ver = s.ws_as_version || '???';
            const fills = s.fills_session != null ? parseInt(s.fills_session, 10) : 0;
            const presence = s.as_presence_pct != null ? `${parseFloat(s.as_presence_pct).toFixed(0)}%` : '???';
            const inv = s.inventory_label || '???';
            const g6 = resolveG6Fields(s);
            const g6Tier = g6.tier ? String(g6.tier).replace(/_/g, ' ') : 'warming';
            const g6Ver = g6VersionShort(g6.version);
            const g6Label = g6Ver ? `G6 ${g6Ver}` : 'G6';

            let html = `<span class="quote">PURE A-S</span> <span class="info">v${ver}</span>`;
            html += ` <span class="info">fills ${fills}</span> <span class="info">pos ${presence}</span>`;
            html += ` <span class="info">inv ${inv}</span>`;
            html += ` <span class="${g2MarqueeKind(s)}">${g2MarqueeText(s)}</span>`;
            html += ` <span class="${g6MarqueeKind(g6.tier)}">${g6Label} ${g6Tier}</span>`;
            html += ` <span class="${g7MarqueeKind(s)}">${g7MarqueeText(s)}</span>`;
            html += ` <span class="${spotMarqueeKind(s)}">${spotMarqueeText(s)}</span>`;

            const toxic30 = s.toxic_fill_ratio_30s != null ? parseFloat(s.toxic_fill_ratio_30s) : null;
            if (toxic30 != null && !Number.isNaN(toxic30)) {
                const kind = toxic30 <= 0.15 ? 'quote' : (toxic30 <= 0.30 ? 'warn' : 'danger');
                html += ` <span class="${kind}">toxic@30s ${(toxic30 * 100).toFixed(0)}%</span>`;
            }

            const skimR = sessionSkimDeltaRlusd(s);
            if (skimR != null && !Number.isNaN(skimR)) {
                const sign = skimR >= 0 ? '+' : '';
                const kind = skimR >= 0 ? 'quote' : 'warn';
                html += ` <span class="${kind}">skim ${sign}${skimR.toFixed(2)} RLUSD</span>`;
            }

            if (s.g4_grade && s.g4_grade !== 'neutral') {
                html += ` <span class="info">G4 ${s.g4_grade}</span>`;
            }

            if (s.kill_switch_active) {
                html += ` <span class="danger">KILL SWITCH</span>`;
            } else if (s.last_note) {
                html += ` <span class="warn">${escapeHudHtml(String(s.last_note).substring(0, 48))}</span>`;
            }

            return html;
        }

        function sessionSkimDeltaXrp(s) {
            if (s.session_spread_capture_xrp != null && !Number.isNaN(parseFloat(s.session_spread_capture_xrp))) {
                return parseFloat(s.session_spread_capture_xrp);
            }
            return null;
        }

        function sessionWalletDeltaXrp(s) {
            const v = s.session_wallet_delta_xrp != null ? s.session_wallet_delta_xrp : s.session_pnl_balance_xrp;
            if (v != null && !Number.isNaN(parseFloat(v))) {
                return parseFloat(v);
            }
            return null;
        }

        function formatSignedXrp(v, digits) {
            if (v == null || Number.isNaN(v)) return '???';
            const sign = v >= 0 ? '+' : '';
            return `${sign}${v.toFixed(digits)} XRP`;
        }

        function formatSignedRlusd(v, digits) {
            if (v == null || Number.isNaN(v)) return '???';
            const sign = v >= 0 ? '+' : '';
            return `${sign}${v.toFixed(digits)} RLUSD`;
        }

        function wealthDeltaClass(v) {
            if (v == null || Number.isNaN(v)) return 'neutral';
            if (v > 0.005) return 'good';
            if (v < -0.005) return 'warn';
            return 'neutral';
        }

        function sessionMid(s) {
            const midRaw = s.mid_price != null ? s.mid_price : (s.mid != null ? s.mid : s.mid_rlusd_per_xrp);
            const mid = midRaw != null ? parseFloat(midRaw) : NaN;
            return !Number.isNaN(mid) && mid > 0 ? mid : null;
        }

        function sessionSkimDeltaRlusd(s) {
            if (s.skim_delta_rlusd != null) {
                const v = parseFloat(s.skim_delta_rlusd);
                if (!Number.isNaN(v)) return v;
            }
            const skimXrp = sessionSkimDeltaXrp(s);
            const mid = sessionMid(s);
            if (skimXrp != null && !Number.isNaN(skimXrp) && mid != null) {
                return skimXrp * mid;
            }
            return null;
        }

        function xrpValueRlusd(s) {
            if (s.xrp_value_rlusd != null) {
                const v = parseFloat(s.xrp_value_rlusd);
                if (!Number.isNaN(v)) return v;
            }
            const mid = sessionMid(s);
            const xrp = s.balance_xrp != null ? parseFloat(s.balance_xrp) : NaN;
            if (mid != null && !Number.isNaN(xrp)) return xrp * mid;
            return null;
        }

        function xrpSharePct(s) {
            if (s.xrp_share_pct != null) {
                const v = parseFloat(s.xrp_share_pct);
                if (!Number.isNaN(v)) return v;
            }
            const mid = sessionMid(s);
            const xrp = s.balance_xrp != null ? parseFloat(s.balance_xrp) : NaN;
            const rlusd = s.balance_rlusd != null ? parseFloat(s.balance_rlusd) : NaN;
            if (mid == null || Number.isNaN(xrp) || Number.isNaN(rlusd)) return null;
            const total = xrp + rlusd / mid;
            return total > 0 ? 100 * xrp / total : null;
        }

        function spotDeltaRlusd(s) {
            if (s.spot_delta_rlusd != null) {
                const v = parseFloat(s.spot_delta_rlusd);
                if (!Number.isNaN(v)) return v;
            }
            const mid = sessionMid(s);
            const bx = s.session_baseline_xrp != null ? parseFloat(s.session_baseline_xrp) : NaN;
            const bm = s.session_baseline_mid != null ? parseFloat(s.session_baseline_mid) : NaN;
            if (mid == null || Number.isNaN(bx) || Number.isNaN(bm)) return null;
            return bx * (mid - bm);
        }

        function wealthDeltaSessionRlusd(s) {
            if (s.wealth_delta_session_rlusd != null) {
                const v = parseFloat(s.wealth_delta_session_rlusd);
                if (!Number.isNaN(v)) return v;
            }
            const mid = sessionMid(s);
            const xrp = s.balance_xrp != null ? parseFloat(s.balance_xrp) : NaN;
            const rlusd = s.balance_rlusd != null ? parseFloat(s.balance_rlusd) : NaN;
            const bx = s.session_baseline_xrp != null ? parseFloat(s.session_baseline_xrp) : NaN;
            const br = s.session_baseline_rlusd != null ? parseFloat(s.session_baseline_rlusd) : NaN;
            const bm = s.session_baseline_mid != null ? parseFloat(s.session_baseline_mid) : NaN;
            if (mid == null || Number.isNaN(xrp) || Number.isNaN(rlusd) || Number.isNaN(bx) || Number.isNaN(br) || Number.isNaN(bm)) {
                return null;
            }
            const wNow = rlusd + xrp * mid;
            const wBase = br + bx * bm;
            return wNow - wBase;
        }

        function rebalanceDeltaRlusd(s) {
            if (s.rebalance_delta_rlusd != null) {
                const v = parseFloat(s.rebalance_delta_rlusd);
                if (!Number.isNaN(v)) return v;
            }
            const wDelta = wealthDeltaSessionRlusd(s);
            const skim = sessionSkimDeltaRlusd(s);
            const spot = spotDeltaRlusd(s);
            if (wDelta == null || Number.isNaN(wDelta) || skim == null || Number.isNaN(skim) || spot == null || Number.isNaN(spot)) {
                return null;
            }
            return wDelta - skim - spot;
        }

        function toxicSoakClass(ratio) {
            if (ratio == null || Number.isNaN(ratio)) return 'neutral';
            const pct = ratio * 100;
            if (pct <= 15) return 'good';
            if (pct <= 30) return 'warn';
            return 'bad';
        }

        function markoutSoakClass(pct) {
            if (pct == null || Number.isNaN(pct)) return 'neutral';
            if (pct >= -0.05) return 'good';
            if (pct >= -0.25) return 'warn';
            return 'bad';
        }

        function bookAgeSoakClass(age) {
            if (age == null || Number.isNaN(age)) return 'neutral';
            if (age < 5) return 'good';
            if (age < 15) return 'warn';
            return 'bad';
        }

        function renderSoakStrip(s) {
            const toxic30 = (s.toxic_fill_ratio_30s != null) ? parseFloat(s.toxic_fill_ratio_30s) : null;
            const markout30 = (s.mean_markout_30s_pct != null) ? parseFloat(s.mean_markout_30s_pct) : null;
            const skimDelta = sessionSkimDeltaXrp(s);
            const skimDeltaRlusd = sessionSkimDeltaRlusd(s);
            const fillsSession = (s.fills_session != null) ? parseInt(s.fills_session, 10) : 0;
            const fillsCsv = (s.ws_fills_csv != null) ? parseInt(s.ws_fills_csv, 10) : 0;
            const fillsCount = fillsSession;
            const presence = (s.as_presence_pct != null) ? parseFloat(s.as_presence_pct) : null;
            const liveAge = computeLiveWsAge(s);
            const pm = s.performance_metrics || {};
            const g6 = resolveG6Fields(s);
            const g6Ver = g6VersionShort(g6.version);
            const kill = !!(s.kill_switch_active);
            const qCopy = quoteStatusCopy(s);

            if (toxic30 != null && !Number.isNaN(toxic30)) {
                setText('soak-toxic', `${(toxic30 * 100).toFixed(0)}%`);
                soakPillClass(document.getElementById('soak-toxic-pill'), toxicSoakClass(toxic30));
            } else {
                setText('soak-toxic', '???');
                soakPillClass(document.getElementById('soak-toxic-pill'), 'neutral');
            }

            if (markout30 != null && !Number.isNaN(markout30)) {
                setText('soak-markout', `${markout30.toFixed(2)}%`);
                soakPillClass(document.getElementById('soak-markout-pill'), markoutSoakClass(markout30));
            } else {
                setText('soak-markout', '???');
                soakPillClass(document.getElementById('soak-markout-pill'), 'neutral');
            }

            if (skimDeltaRlusd != null && !Number.isNaN(skimDeltaRlusd)) {
                const sign = skimDeltaRlusd >= 0 ? '+' : '';
                setText('soak-pnl', `${sign}${skimDeltaRlusd.toFixed(2)}`);
                soakPillClass(document.getElementById('soak-pnl-pill'), skimDeltaRlusd >= 0 ? 'good' : 'warn');
            } else if (skimDelta != null && !Number.isNaN(skimDelta)) {
                const sign = skimDelta >= 0 ? '+' : '';
                setText('soak-pnl', `${sign}${skimDelta.toFixed(3)} XRP`);
                soakPillClass(document.getElementById('soak-pnl-pill'), skimDelta >= 0 ? 'good' : 'warn');
            } else {
                setText('soak-pnl', '???');
                soakPillClass(document.getElementById('soak-pnl-pill'), 'neutral');
            }

            setText('soak-fills', String(fillsCount));
            soakPillClass(document.getElementById('soak-fills-pill'), fillsCount > 0 ? 'good' : 'neutral');

            if (presence != null && !Number.isNaN(presence)) {
                setText('soak-presence', `${presence.toFixed(0)}%`);
                soakPillClass(document.getElementById('soak-presence-pill'), presence >= 75 ? 'good' : (presence >= 50 ? 'warn' : 'bad'));
            } else {
                setText('soak-presence', '???');
                soakPillClass(document.getElementById('soak-presence-pill'), 'neutral');
            }

            if (liveAge != null && !Number.isNaN(liveAge)) {
                setText('soak-book', `${liveAge.toFixed(1)}s`);
                soakPillClass(document.getElementById('soak-book-pill'), bookAgeSoakClass(liveAge));
            } else {
                setText('soak-book', formatWsAge(s));
                soakPillClass(document.getElementById('soak-book-pill'), 'neutral');
            }

            setText('soak-g6-label', g6Ver ? ('G6 ' + g6Ver) : 'G6');
            const tierDisplay = g6.tier
                ? String(g6.tier).replace(/_/g, ' ')
                : (g6.version ? '???' : 'off');
            setText('soak-g6', tierDisplay);
            soakPillClass(document.getElementById('soak-g6-pill'), g6SoakPillClass(g6.tier || ''));

            let statusTxt = kill ? 'KILL' : (qCopy.good ? 'LIVE' : 'PAUSE');
            setText('soak-status', statusTxt);
            soakPillClass(document.getElementById('soak-status-pill'), kill ? 'bad' : (qCopy.good ? 'good' : 'warn'));
        }

        function renderLive(s) {
            if (!s) return;
            try {
                renderLiveInner(s);
            } catch (e) {
                console.error('[HUD] renderLive error', e);
                const statusEl = document.getElementById('hud-poll-status');
                if (statusEl) {
                    statusEl.textContent = 'RENDER ERROR ??? check browser console (F12); engine data may still be polling';
                    statusEl.style.color = '#facc15';
                }
            }
        }

        function renderLiveInner(s) {
            if (s.competitor_nicknames && typeof s.competitor_nicknames === 'object') {
                competitorNicknames = s.competitor_nicknames;
            }

            // Apply any demo inventory movements (deposits/withdraws) so balances stay consistent across polls
            applyDemoBalancePatchToState(s);

            // Normalize data keys ??? engine sends mid_price / best_bid_rlusd_per_xrp etc.
            // for compatibility with the main Streamlit GUI. Support both.
            if (s.mid == null && s.mid_price != null) s.mid = s.mid_price;
            if (s.best_bid == null && s.best_bid_rlusd_per_xrp != null) s.best_bid = s.best_bid_rlusd_per_xrp;
            if (s.best_ask == null && s.best_ask_rlusd_per_xrp != null) s.best_ask = s.best_ask_rlusd_per_xrp;

            // Header mode badge (always present)
            const modeEl = document.getElementById('mode');
            if (modeEl) {
                if (isProductionHud(s)) {
                    modeEl.textContent = '(MAINNET ?? ws-engine)';
                } else if (s.as_mode) {
                    modeEl.textContent = `(LAB ?? ${String(s.as_mode).toUpperCase()})`;
                } else {
                    modeEl.textContent = '';
                }
            }
            updateEngineControlsUi(s);
            renderSoakStrip(s);

            const sampleCount = (s.sample_count != null)
                ? s.sample_count
                : (Array.isArray(s.sample_history) ? s.sample_history.length : null);
            const ver = s.ws_as_version || '???';
            const presence = (s.as_presence_pct != null) ? `${parseFloat(s.as_presence_pct).toFixed(1)}%` : '???';
            const fillsSession = (s.fills_session != null) ? parseInt(s.fills_session, 10) : 0;
            const fillsCsv = (s.ws_fills_csv != null) ? parseInt(s.ws_fills_csv, 10) : 0;
            const fillsCount = fillsSession;
            const fillsProcNote = (fillsCsv > fillsSession && fillsCsv > 0)
                ? ` ?? ${fillsCsv} all-time CSV`
                : '';
            const skimDelta = sessionSkimDeltaXrp(s);
            const skimDeltaRlusd = sessionSkimDeltaRlusd(s);
            const spreadCap = skimDelta;
            const markout30 = (s.mean_markout_30s_pct != null) ? parseFloat(s.mean_markout_30s_pct) : null;
            const toxic30 = (s.toxic_fill_ratio_30s != null) ? parseFloat(s.toxic_fill_ratio_30s) : null;
            const sessionLine = `v ${ver} ?? cycles ${sampleCount != null ? sampleCount : '???'}`;
            setText('header-session', sessionLine);

            // Sidebar wealth (RLUSD-stable, no mental math)
            const wealthTotal = s.wealth_rlusd != null
                ? parseFloat(s.wealth_rlusd)
                : portfolioValueRlusd(s);
            const wealthDisplay = wealthTotal != null && !Number.isNaN(wealthTotal)
                ? (formatPortfolioUsd(wealthTotal) || `${wealthTotal.toFixed(2)} RLUSD`)
                : '???';
            setText('sidebar-wealth-total', wealthDisplay);

            const wDelta = wealthDeltaSessionRlusd(s);
            const wealthDeltaEl = document.getElementById('sidebar-wealth-delta');
            if (wealthDeltaEl) {
                if (wDelta != null && !Number.isNaN(wDelta)) {
                    wealthDeltaEl.textContent = `Session ?? ${formatSignedRlusd(wDelta, 2)}`;
                    wealthDeltaEl.className = 'sidebar-value ' + wealthDeltaClass(wDelta);
                } else {
                    wealthDeltaEl.textContent = 'Session ??: ???';
                    wealthDeltaEl.className = 'sidebar-value';
                }
            }

            const skimR = s.skim_delta_rlusd != null
                ? parseFloat(s.skim_delta_rlusd)
                : skimDeltaRlusd;
            setText(
                'sidebar-skim-rlusd',
                skimR != null && !Number.isNaN(skimR)
                    ? `Skim (spread): ${formatSignedRlusd(skimR, 2)}`
                    : 'Skim (spread): ???'
            );

            const spotR = spotDeltaRlusd(s);
            setText(
                'sidebar-spot-rlusd',
                spotR != null && !Number.isNaN(spotR)
                    ? `Spot (XRP????mid): ${formatSignedRlusd(spotR, 2)}`
                    : 'Spot (XRP????mid): ???'
            );

            const rebalR = rebalanceDeltaRlusd(s);
            setText(
                'sidebar-rebal-rlusd',
                rebalR != null && !Number.isNaN(rebalR)
                    ? `Trades/rebal: ${formatSignedRlusd(rebalR, 2)}`
                    : 'Trades/rebal: ???'
            );

            const legRlusd = s.rlusd_stable_balance != null
                ? parseFloat(s.rlusd_stable_balance)
                : (s.balance_rlusd != null ? parseFloat(s.balance_rlusd) : null);
            setText(
                'sidebar-leg-rlusd',
                legRlusd != null && !Number.isNaN(legRlusd)
                    ? `RLUSD stable: ${legRlusd.toFixed(2)}`
                    : 'RLUSD stable: ???'
            );

            const legXrpVal = xrpValueRlusd(s);
            const xrpBal = s.balance_xrp != null ? parseFloat(s.balance_xrp) : null;
            if (legXrpVal != null && !Number.isNaN(legXrpVal) && xrpBal != null && !Number.isNaN(xrpBal)) {
                setText('sidebar-leg-xrp', `XRP @ mid: ${legXrpVal.toFixed(2)} (${xrpBal.toFixed(1)} XRP)`);
            } else if (legXrpVal != null && !Number.isNaN(legXrpVal)) {
                setText('sidebar-leg-xrp', `XRP @ mid: ${legXrpVal.toFixed(2)}`);
            } else {
                setText('sidebar-leg-xrp', 'XRP @ mid: ???');
            }

            const xrpShare = xrpSharePct(s);
            setText(
                'sidebar-xrp-share',
                xrpShare != null && !Number.isNaN(xrpShare)
                    ? `XRP share: ${xrpShare.toFixed(1)}%`
                    : 'XRP share: ???'
            );

            setText('sidebar-xrp', s.balance_xrp !== undefined ? `XRP: ${parseFloat(s.balance_xrp).toFixed(2)}` : 'XRP: -');
            setText('sidebar-rlusd', s.balance_rlusd !== undefined ? `RLUSD: ${parseFloat(s.balance_rlusd).toFixed(2)}` : 'RLUSD: -');
            setText('sidebar-inventory', s.inventory_label || '-');
            const configSel = document.getElementById('config-profile-select');
            if (configSel) configSel.value = s.active_profile || '';
            const qCopy = quoteStatusCopy(s);

            // Live page cards - ALWAYS update the DOM values (visibility is controlled by CSS on #live container only)
            const bookEl = document.getElementById('live-book-snippet');
            if (bookEl) {
                if (!s.best_bid && !s.best_ask && !s.mid) {
                    bookEl.innerHTML = '<span style="color:#64748b;">Connecting to live book feed???</span>';
                } else {
                    const newBook = (s.best_bid && s.best_ask)
                        ? `${parseFloat(s.best_bid).toFixed(6)} / ${parseFloat(s.best_ask).toFixed(6)} <span style="font-size:0.7rem;color:#64748b;">mid ${parseFloat(s.mid || 0).toFixed(6)}</span>`
                        : '-';
                    const bookChanged = prevValues.book !== newBook;
                    prevValues.book = newBook;
                    if (bookChanged) {
                        triggerAnim(bookEl, 'flash-up', 500);
                        const bookCard = bookEl.closest('.card');
                        if (bookCard) triggerAnim(bookCard, 'card-updated', 400);
                    }
                    bookEl.innerHTML = newBook;
                }
            }

            const spreadEl = document.getElementById('spread');
            if (spreadEl) {
                const newSpread = (s.book_spread_pct != null) ? parseFloat(s.book_spread_pct).toFixed(3) + '%' : '-';
                const spreadChanged = prevValues.spread !== newSpread;
                prevValues.spread = newSpread;
                setText('spread', newSpread);
                if (spreadChanged) triggerAnim(spreadEl, 'flash-up', 500); // treat spread change as positive visual
            }
            const ageEl = document.getElementById('age');
            if (ageEl) {
                const liveAge = computeLiveWsAge(s);
                const newAge = formatWsAge(s);
                const ageChanged = prevValues.age !== newAge;
                prevValues.age = newAge;
                ageEl.textContent = newAge;
                ageEl.style.color = wsAgeColor(liveAge);
                if (ageChanged) triggerAnim(ageEl, 'value-updated', 400);
            }
            const msgsEl = document.getElementById('msgs');
            if (msgsEl) {
                const newMsgs = (s.ws_message_count != null) ? s.ws_message_count : '-';
                const msgsChanged = prevValues.msgs !== newMsgs;
                prevValues.msgs = newMsgs;
                setText('msgs', newMsgs);
                if (msgsChanged) triggerAnim(msgsEl, 'value-updated', 400);
            }
            const volEl = document.getElementById('volatility');
            if (volEl) {
                const newVol = (s.volatility_pct != null) ? parseFloat(s.volatility_pct).toFixed(2) + '%' : '???';
                const volChanged = prevValues.vol !== newVol;
                prevValues.vol = newVol;
                setText('volatility', newVol);
                if (volChanged) triggerAnim(volEl, 'flash-up', 500);
            }

            // A-S reservation + margins (guarded)
            const resEl = document.getElementById('reservation');
            if (resEl) {
                let newRes = '-';
                if (s.as_reservation != null) {
                    let html = parseFloat(s.as_reservation).toFixed(6);
                    if (s.best_bid && s.best_ask) {
                        const marginBid = (parseFloat(s.as_reservation) - parseFloat(s.best_bid)).toFixed(5);
                        const marginAsk = (parseFloat(s.best_ask) - parseFloat(s.as_reservation)).toFixed(5);
                        html += ` <span style="font-size:0.65rem; color:#64748b;">(bid margin ${marginBid} / ask ${marginAsk})</span>`;
                    }
                    newRes = html;
                }
                const resChanged = prevValues.res !== newRes;
                prevValues.res = newRes;
                resEl.innerHTML = newRes;
                if (resChanged) triggerAnim(resEl, 'value-updated', 400);
            }

            const asSpreadEl = document.getElementById('as_spread');
            if (asSpreadEl) {
                const newAs = (s.as_optimal_spread_pct != null) ? parseFloat(s.as_optimal_spread_pct).toFixed(3) + '%' : '-';
                const asChanged = prevValues.as_spread !== newAs;
                prevValues.as_spread = newAs;
                setText('as_spread', newAs);
                if (asChanged) triggerAnim(asSpreadEl, 'value-updated', 400);
            }

            const deltaBps = s.reservation_to_bbo_delta_bps;
            const insideL1 = s.inside_l1;
            const deltaEl = document.getElementById('res-bbo-delta');
            if (deltaEl) {
                if (deltaBps != null && !Number.isNaN(parseFloat(deltaBps))) {
                    const bps = parseFloat(deltaBps);
                    const sign = bps >= 0 ? '+' : '';
                    const side = insideL1 === true ? 'inside ' : (insideL1 === false ? 'outside ' : '');
                    deltaEl.textContent = `${side}${sign}${bps.toFixed(1)} bps`;
                    deltaEl.className = 'value ' + (insideL1 ? 'good' : 'warn');
                } else {
                    deltaEl.textContent = '???';
                    deltaEl.className = 'value';
                }
            }

            const paramsEl = document.getElementById('params');
            if (paramsEl) {
                const newP = (s.as_gamma != null && s.as_kappa != null) ? `${s.as_gamma} / ${s.as_kappa}` : '-';
                const pChanged = prevValues.params !== newP;
                prevValues.params = newP;
                setText('params', newP);
                if (pChanged) triggerAnim(paramsEl, 'value-updated', 400);
            }

            const wq = document.getElementById('would_quote');
            setText('quote-posture-label', qCopy.posture);
            if (wq) {
                const wqChanged = prevValues.would_quote !== s.would_quote;
                prevValues.would_quote = s.would_quote;
                wq.textContent = qCopy.headline;
                if (qCopy.good) {
                    wq.className = 'value good';
                    wq.style.background = '#052e16';
                } else {
                    wq.className = 'value warn';
                    wq.style.background = '#3f1f1f';
                }
                if (wqChanged) {
                    triggerAnim(wq, 'status-pop', 500);
                }
            }

            const zqn = document.getElementById('zero-quote-note');
            if (zqn) {
                const note = s.would_quote
                    ? (s.tight_book_note || '')
                    : (s.zero_quote_operator_note || s.zero_quote_detail || s.zero_quote_reason || '');
                if (note) {
                    zqn.style.display = 'block';
                    zqn.textContent = note;
                    zqn.style.color = s.would_quote ? '#94a3b8' : '#fbbf24';
                } else {
                    zqn.style.display = 'none';
                    zqn.textContent = '';
                }
            }

            setText('fills-session', `${fillsCount}${fillsProcNote}`);
            const fillAgeEl = document.getElementById('fill-quote-age');
            if (fillAgeEl) {
                const fillAge = s.effective_quote_age_at_fill_seconds;
                if (fillAge != null && !Number.isNaN(parseFloat(fillAge))) {
                    fillAgeEl.textContent = `${parseFloat(fillAge).toFixed(1)}s`;
                } else {
                    fillAgeEl.textContent = '???';
                }
            }
            const fillAgeRecentEl = document.getElementById('fill-age-recent');
            if (fillAgeRecentEl) {
                const recent = Array.isArray(s.recent_fill_quote_ages) ? s.recent_fill_quote_ages : [];
                if (recent.length) {
                    const parts = recent.slice(-5).map((r) => {
                        const age = r.quote_age_seconds;
                        const side = (r.side || '').charAt(0) || '?';
                        if (age == null || Number.isNaN(parseFloat(age))) return `${side}:?`;
                        return `${side}:${parseFloat(age).toFixed(1)}s`;
                    });
                    fillAgeRecentEl.textContent = parts.reverse().join(' ?? ');
                } else {
                    fillAgeRecentEl.textContent = '???';
                }
            }
            if (skimDeltaRlusd != null && !Number.isNaN(skimDeltaRlusd)) {
                const pnlEl = document.getElementById('session-pnl');
                if (pnlEl) {
                    pnlEl.textContent = formatSignedRlusd(skimDeltaRlusd, 2);
                    pnlEl.className = 'value ' + (skimDeltaRlusd >= 0 ? 'good' : 'warn');
                }
            } else if (skimDelta != null && !Number.isNaN(skimDelta)) {
                const pnlEl = document.getElementById('session-pnl');
                if (pnlEl) {
                    pnlEl.textContent = formatSignedXrp(skimDelta, 4);
                    pnlEl.className = 'value ' + (skimDelta >= 0 ? 'good' : 'warn');
                }
            } else {
                setText('session-pnl', '???');
            }
            if (spreadCap != null && !Number.isNaN(spreadCap)) {
                setText('session-capture', formatSignedXrp(spreadCap, 4));
            } else {
                setText('session-capture', '???');
            }
            if (markout30 != null && !Number.isNaN(markout30)) {
                setText('session-markout', `${markout30.toFixed(3)}%`);
            } else {
                setText('session-markout', '???');
            }
            if (toxic30 != null && !Number.isNaN(toxic30)) {
                const toxEl = document.getElementById('session-toxic');
                const toxTxt = `${(toxic30 * 100).toFixed(1)}%`;
                if (toxEl) {
                    toxEl.textContent = toxTxt;
                    toxEl.className = 'value ' + (toxic30 <= 0.15 ? 'good' : (toxic30 <= 0.30 ? 'warn' : 'bad'));
                } else {
                    setText('session-toxic', toxTxt);
                }
            } else {
                setText('session-toxic', '???');
            }
            setText('fill-quality-note', s.execution_brakes_summary || s.g2_summary || s.fill_quality_summary || '???');
            if (s.g2_scaler_label) {
                setText('g2-scaler', s.g2_scaler_label);
            } else if (s.g2_active) {
                const g2s = s.g2_size_mult != null ? parseFloat(s.g2_size_mult) : 1;
                const g2p = s.g2_spread_mult != null ? parseFloat(s.g2_spread_mult) : 1;
                setText('g2-scaler', `${s.g2_grade || 'brake'} size??${g2s.toFixed(2)} spread??${g2p.toFixed(2)}`);
            } else {
                setText('g2-scaler', s.g2_grade === 'ok' ? 'ok (no chase)' : 'neutral');
            }
            setText('g7-scaler', s.g7_scaler_label || s.g7_summary || '???');
            const qVis = s.quote_visibility_summary
                || (s.worst_vs_touch_bps != null && s.worst_vs_touch_bps > 0
                    ? `worst ${parseFloat(s.worst_vs_touch_bps).toFixed(1)}bps off touch`
                    : (s.quotes_at_touch === true ? 'at touch' : ''));
            setText('queue-visibility', qVis || '???');

            renderSuggestedLadder(s);

            setText('last_note', s.last_note || 'Waiting for first WS update + A-S decision...');

            // === Config page: wallet balances + profile ===
            setText('config-xrp-balance', s.balance_xrp !== undefined ? `${parseFloat(s.balance_xrp).toFixed(2)} XRP` : '???');
            setText('config-rlusd-balance', s.balance_rlusd !== undefined ? `${parseFloat(s.balance_rlusd).toFixed(2)} RLUSD` : '???');

            setText('config-profile', s.active_profile || '???');
            const csel = document.getElementById('config-profile-select');
            if (csel) csel.value = s.active_profile || '';
            setText('config-min-order', '0.1');

            // Intelligence API config (advisory AI for competitor analysis via ledger addresses)
            // Protect against frequent renderLive polls clobbering user edits in the Config form.
            // User changes (dropdown, paste key, etc.) set a touched flag for a grace period.
            // We also keep the key status sticky if server now echoes a key (after the tester merge fix).
            const _intelTouched = window._intelConfigUserTouched || 0;
            const _intelInGrace = (Date.now() <= _intelTouched);
            const aiProv = document.getElementById('intel-ai-provider');
            const aiKey = document.getElementById('intel-ai-key');
            const aiKeyWrap = document.getElementById('intel-ai-key-wrap') || (aiKey ? aiKey.parentElement : null);
            const aiModel = document.getElementById('intel-ai-model');
            const aiEnabled = document.getElementById('intel-ai-enabled');

            if (_intelInGrace) {
                // During grace after edit/Apply: do not let poll clobber the form controls the user is touching
                // (but we can still refresh the status pill if server now reports a key)
            } else {
                if (aiProv && s.intel_ai_provider) aiProv.value = s.intel_ai_provider;
                if (aiModel && s.intel_ai_model) aiModel.value = s.intel_ai_model;
                if (aiEnabled) aiEnabled.checked = !!(s.intel_ai_enabled !== false);
            }

            // Key field / status is special: prefer server echo when present; during recent apply we force the "set" UI from client too.
            if (aiKey) {
                const serverHasKey = !!(s.intel_ai_key && s.intel_ai_key.length > 0);
                const recentApply = (Date.now() <= (_intelTouched + 5000)); // a bit of extra stickiness right after Apply
                if (serverHasKey || (recentApply && (window._lastAppliedAiKeyLen || 0) > 0)) {
                    if (aiKeyWrap) {
                        aiKey.style.display = 'none';
                        let status = document.getElementById('intel-ai-key-status');
                        if (!status) {
                            status = document.createElement('span');
                            status.id = 'intel-ai-key-status';
                            status.style.fontSize = '0.75rem';
                            status.style.color = '#22c55e';
                            status.style.marginLeft = '6px';
                            aiKeyWrap.appendChild(status);
                        }
                        const len = serverHasKey ? s.intel_ai_key.length : (window._lastAppliedAiKeyLen || 0);
                        status.textContent = 'Key set (hidden for security) ??? length: ' + len + (recentApply ? ' (applied)' : '');
                        let clearBtn = document.getElementById('intel-ai-key-clear');
                        if (!clearBtn) {
                            clearBtn = document.createElement('button');
                            clearBtn.id = 'intel-ai-key-clear';
                            clearBtn.textContent = 'Clear';
                            clearBtn.style.fontSize = '0.6rem';
                            clearBtn.style.marginLeft = '4px';
                            clearBtn.onclick = () => {
                                if (aiKey) aiKey.value = '';
                                if (status) status.remove();
                                if (clearBtn) clearBtn.remove();
                                if (aiKey) aiKey.style.display = '';
                                window._intelConfigUserTouched = 0;
                                window._lastAppliedAiKeyLen = 0;
                            };
                            aiKeyWrap.appendChild(clearBtn);
                        }
                    } else {
                        aiKey.value = '???????????????????????? (set)';
                    }
                } else if (!_intelInGrace) {
                    // Only clear the UI if outside grace AND server reports no key
                    aiKey.value = '';
                    aiKey.style.display = '';
                    const status = document.getElementById('intel-ai-key-status');
                    if (status) status.remove();
                    const clearBtn = document.getElementById('intel-ai-key-clear');
                    if (clearBtn) clearBtn.remove();
                }
            }

            // Remember last applied length for sticky UI even across a poll that hasn't echoed yet
            if (s.intel_ai_key && s.intel_ai_key.length > 0) {
                window._lastAppliedAiKeyLen = s.intel_ai_key.length;
            }

            // Auto-suggest model when provider changes in Config (attach listeners only once)
            if (!window._intelListenersAttached) {
                const aiProvSel = document.getElementById('intel-ai-provider');
                const aiModelIn = document.getElementById('intel-ai-model');
                const aiKeyIn = document.getElementById('intel-ai-key');
                const aiEnabledIn = document.getElementById('intel-ai-enabled');
                function markIntelUserTouched() {
                    window._intelConfigUserTouched = Date.now() + 12000; // grace so polls don't clobber while editing
                }
                if (aiProvSel && aiModelIn) {
                    aiProvSel.addEventListener('change', () => {
                        markIntelUserTouched();
                        if (aiProvSel.value === 'grok' && (!aiModelIn.value || aiModelIn.value === 'llama3' || aiModelIn.value === 'grok-beta')) {
                            aiModelIn.value = 'grok-3';
                        } else if (aiProvSel.value === 'ollama' && (!aiModelIn.value || aiModelIn.value === 'grok-beta')) {
                            aiModelIn.value = 'llama3';
                        }
                        if (aiProvSel.value === 'grok') {
                            aiModelIn.value = 'grok-3';
                        }
                    });
                }
                if (aiKeyIn) aiKeyIn.addEventListener('input', markIntelUserTouched);
                if (aiModelIn) aiModelIn.addEventListener('input', markIntelUserTouched);
                if (aiEnabledIn) aiEnabledIn.addEventListener('change', markIntelUserTouched);
                window._intelListenersAttached = true;
            }

            // L1-L3 commitments (L1 from live quote intents if available, L2/L3 demo for now)

            // === Inventory page (new tab) updates ===
            const invAddr = document.getElementById('inv-bot-address');
            const invFundAddr = document.getElementById('inv-fund-bot-address');
            const addr = s.bot_account_address || s.bot_address || 'r... (set bot_account_address)';
            if (invAddr) {
                invAddr.textContent = addr;
                invAddr.dataset.address = addr;
            }
            if (invFundAddr) {
                invFundAddr.textContent = addr;
                invFundAddr.dataset.address = addr;
            }

            const sendDest = document.getElementById('send-dest');
            if (sendDest && s.send_destination_default && !sendDest.dataset.userEdited) {
                sendDest.value = s.send_destination_default;
            }
            setText('inv-funding-status', s.funding_status_label || '???');
            const riskCap = s.risk_capital_xrp != null ? parseFloat(s.risk_capital_xrp) : null;
            if (riskCap != null && !Number.isNaN(riskCap)) {
                setText('inv-risk-capital-label', `${riskCap.toLocaleString(undefined, {maximumFractionDigits: 0})} XRP`);
            }
            const port = s.portfolio_value_xrp != null ? parseFloat(s.portfolio_value_xrp) : null;
            setText('inv-portfolio-xrp', port != null && !Number.isNaN(port) ? `${port.toFixed(2)} XRP` : '???');
            if (port != null && riskCap != null && !Number.isNaN(port) && !Number.isNaN(riskCap) && riskCap > 0) {
                const depPct = s.funding_deployed_pct != null ? parseFloat(s.funding_deployed_pct) : (port / riskCap * 100);
                setText('inv-funding-pct', `${port.toFixed(0)} / ${riskCap.toFixed(0)} XRP (${depPct.toFixed(1)}%)`);
            } else {
                setText('inv-funding-pct', '???');
            }
            setText('inv-xrp-balance', s.balance_xrp !== undefined ? `${parseFloat(s.balance_xrp).toFixed(2)} XRP` : '???');
            setText('inv-rlusd-balance', s.balance_rlusd !== undefined ? `${parseFloat(s.balance_rlusd).toFixed(2)} RLUSD` : '???');
            setText('inv-rlusd-xrp-equiv', s.rlusd_xrp_equiv != null ? `${parseFloat(s.rlusd_xrp_equiv).toFixed(2)} XRP` : '???');
            setText('inv-open-offers', s.open_offers_count != null ? String(s.open_offers_count) : '???');
            const walletDelta = sessionWalletDeltaXrp(s);
            const walletEl = document.getElementById('inv-wallet-delta');
            if (walletEl) {
                if (walletDelta != null && !Number.isNaN(walletDelta)) {
                    walletEl.textContent = formatSignedXrp(walletDelta, 2);
                    walletEl.className = 'value ' + (walletDelta >= 0 ? 'good' : 'warn');
                } else {
                    walletEl.textContent = '???';
                    walletEl.className = 'value';
                }
            }
            const xrpPct = s.inventory_xrp_ratio_pct != null ? parseFloat(s.inventory_xrp_ratio_pct) : null;
            const tgtPct = s.inventory_target_xrp_pct != null ? parseFloat(s.inventory_target_xrp_pct) : 55;
            setText('inv-xrp-target', String(tgtPct));
            if (xrpPct != null && !Number.isNaN(xrpPct)) {
                setText('inv-xrp-ratio', `${xrpPct.toFixed(1)}%`);
                const bar = document.getElementById('inv-xrp-ratio-bar');
                if (bar) bar.style.width = `${Math.min(100, Math.max(0, xrpPct))}%`;
            } else {
                setText('inv-xrp-ratio', '???');
            }
            setText('inv-label', s.inventory_label || '???');
            const ledUp = s.ledger_updated_utc || s.updated_utc;
            setText('inv-ledger-updated', ledUp ? `Ledger poll: ${ledUp.replace('T', ' ').slice(0, 19)} UTC` : 'Ledger poll: ???');

            // === Intelligence tab (full competitor scrape + skim strategy) ===
            setText('intel-observed-spread', s.competitor_observed_spread_pct != null ? `${parseFloat(s.competitor_observed_spread_pct).toFixed(3)}%` : '???');
            setText('intel-our-lane-l1', _formatLaneTouch(s, 1, 'our_lane_xrp'));
            setText('intel-our-lane-l2', _formatLaneTouch(s, 2, 'our_lane_l2_xrp'));
            setText('intel-our-lane-l3', _formatLaneTouch(s, 3, 'our_lane_l3_xrp'));
            const peerBand = (s.peer_lane_low_xrp != null && s.peer_lane_high_xrp != null)
                ? ` (${parseFloat(s.peer_lane_low_xrp).toFixed(0)}???${parseFloat(s.peer_lane_high_xrp).toFixed(0)})`
                : '';
            setText('intel-peer-count', s.peer_lane_count != null ? `${s.peer_lane_count}${peerBand}` : '???');
            setText('intel-fled', s.peer_fled_touch_count != null ? s.peer_fled_touch_count : '???');
            setText('intel-pressure', s.competitor_pressure != null ? parseFloat(s.competitor_pressure).toFixed(2) : '???');
            setText(
                'intel-peer-pressure',
                s.peer_pressure != null
                    ? parseFloat(s.peer_pressure).toFixed(2)
                    : (s.peer_lane_count > 0 ? '???' : 'n/a (empty lane)')
            );
            setText(
                'intel-book-regime-pressure',
                s.book_regime_pressure != null ? parseFloat(s.book_regime_pressure).toFixed(2) : '???'
            );
            setText(
                'intel-spread-regime-gap',
                s.spread_regime_gap_bps != null ? `${parseFloat(s.spread_regime_gap_bps).toFixed(1)} bps` : '???'
            );
            setText('intel-book-side-skew', s.book_side_skew_display || '???');
            setText('intel-active', s.num_active_mms != null ? s.num_active_mms : '???');
            setText('intel-depth', s.competitor_depth_xrp != null ? `${parseFloat(s.competitor_depth_xrp).toFixed(1)} XRP` : '???');
            setText('intel-advice', s.competitor_skim_advice || (isProductionHud(s)
                ? 'Waiting for peer-lane scrape (~15s). Use Force scrape if still empty.'
                : 'No scrape data ??? run live_pure_as_tester --serve-hud with a live WS book.'));

            function _renderIntelMakerList(listEl, rows, emptyMsg) {
                renderMakerPeerList(listEl, rows, emptyMsg, s, {
                    analyzeInputId: 'intel-analyze-addr',
                    nickInputId: 'nick-address',
                    analyzeBtnId: 'btn-analyze-addr',
                });
            }

            const peerListEl = document.getElementById('intel-peer-list-inner');
            const allMakersEl = document.getElementById('intel-all-makers-inner');
            const peerRows = (s.top_peers && Array.isArray(s.top_peers) && s.top_peers.length) ? s.top_peers : null;
            const compRows = (s.top_competitors && Array.isArray(s.top_competitors) && s.top_competitors.length) ? s.top_competitors : null;
            const laneTxt = s.our_lane_xrp != null ? `${parseFloat(s.our_lane_xrp).toFixed(1)} XRP` : 'your touch';
            const bandTxt = (s.peer_lane_low_xrp != null && s.peer_lane_high_xrp != null)
                ? `${parseFloat(s.peer_lane_low_xrp).toFixed(0)}???${parseFloat(s.peer_lane_high_xrp).toFixed(0)} XRP`
                : '0.4?????2.5?? lane';
            const peerEmpty = (s.peer_lane_count > 0)
                ? 'Peer accounts at touch but profiles still loading ??? retry in ~15s.'
                : `No peers in touch band (${bandTxt} around ${laneTxt}). Whales in the book-wide list are outside this band.`;
            _renderIntelMakerList(peerListEl, peerRows, peerEmpty);
            _renderIntelMakerList(
                allMakersEl,
                compRows,
                'No competitor profiles yet ??? production HUD scrapes the book every ~15s.'
            );

            const selfAnalyzeBtn = document.getElementById('btn-analyze-self');
            if (selfAnalyzeBtn) {
                const botAddr = String(s.bot_account_address || s.bot_address || '').trim();
                const hasBot = botAddr.length >= 25;
                selfAnalyzeBtn.disabled = !hasBot;
                selfAnalyzeBtn.style.opacity = hasBot ? '1' : '0.45';
                selfAnalyzeBtn.style.cursor = hasBot ? 'pointer' : 'not-allowed';
                selfAnalyzeBtn.title = hasBot
                    ? `Grok self-audit for ${botAddr.slice(0, 12)}??? (visibility, vs-touch, inventory)`
                    : 'bot_account_address not in HUD state yet';
            }

            // AI fields in Intelligence tab
            setText('intel-ai-quality', s.ai_edge_quality != null ? parseFloat(s.ai_edge_quality).toFixed(2) : '???');
            setText('intel-ai-skimmable', s.ai_is_skimmable != null ? (s.ai_is_skimmable ? 'YES' : 'NO') : '???');
            const volM = s.ai_advisory_vol_mult != null ? parseFloat(s.ai_advisory_vol_mult).toFixed(2) : null;
            const szM = s.ai_advisory_size_mult != null ? parseFloat(s.ai_advisory_size_mult).toFixed(2) : null;
            setText('intel-ai-advisory-mults', (volM && szM) ? `${volM} / ${szM}` : '???');
            const ratEl = document.getElementById('intel-ai-rationale');
            if (ratEl) ratEl.textContent = s.ai_advisory_rationale || s.ai_rationale || 'F2 rate-limited HUD stub from scrape pressure (advisory only).';
            setText('intel-ai-rationale', s.ai_rationale || '???');
            setText('intel-ai-posture', s.ai_suggested_posture || '???');

            if (pinnedIntelAiResult) {
                const aiResultEl = document.getElementById('intel-ai-result');
                if (aiResultEl && aiResultEl.textContent !== pinnedIntelAiResult) {
                    aiResultEl.textContent = pinnedIntelAiResult;
                }
            }

            renderMetrics(s);
            renderBook(s);
            renderPeerCal(s);

            const recentEl = document.getElementById('recent');
            if (recentEl) {
                const notes = (s.recent_notes && s.recent_notes.length) ? s.recent_notes : (s.last_note ? [s.last_note] : []);
                recentEl.innerHTML = notes.map(n => `<div class="new-decision" style="margin:2px 0;opacity:0.85;">${n}</div>`).join('');
            }

            // Marquee (slow scroll, color spans) - operator posture strip
            const marqueeEl = document.getElementById('marquee');
            if (marqueeEl) {
                try {
                    const base = buildOperatorMarqueeHtml(s);
                    const sep = '   |   ';
                    const unit = base + sep + base + sep + base + sep + base;
                    marqueeEl.innerHTML = unit + unit;
                    marqueeEl.style.animation = 'marquee-seamless 60s linear infinite';
                } catch (e) {
                    console.error('[HUD] marquee error', e);
                    marqueeEl.textContent = 'PURE A-S WS ??? marquee recover; fills ' + (s.fills_session != null ? s.fills_session : '???');
                }
            }

            // === Bottom live market ticker (order book top + price direction) ===
            // Shows on every page. Red for falling mid, green for rising.
            const midVal = (s.mid != null) ? parseFloat(s.mid) : null;
            const bidVal = (s.best_bid != null) ? parseFloat(s.best_bid).toFixed(6) : '???';
            const askVal = (s.best_ask != null) ? parseFloat(s.best_ask).toFixed(6) : '???';
            const spreadVal = (s.book_spread_pct != null) ? parseFloat(s.book_spread_pct).toFixed(3) + '%' : '???';
            const ageVal = formatWsAge(s);

            let midDisplay = midVal !== null ? midVal.toFixed(6) : '???';
            if (midVal !== null && lastMid !== null) {
                if (midVal > lastMid) {
                    lastMidDirectionStyle = 'color:#4ade80; font-weight:700; background:rgba(74,222,128,0.15); padding:0 4px; border-radius:2px;';
                    lastDirectionArrow = ' ???';
                } else if (midVal < lastMid) {
                    lastMidDirectionStyle = 'color:#f87171; font-weight:700; background:rgba(248,113,113,0.15); padding:0 4px; border-radius:2px;';
                    lastDirectionArrow = ' ???';
                }
                // else: hold previous direction style and arrow
            }
            if (midVal !== null) lastMid = midVal;

            if (midVal !== null) {
                midDisplay = midVal.toFixed(6) + lastDirectionArrow;
            }

            let base = `Mid <span style="${lastMidDirectionStyle}">${midDisplay}</span>   Bid ${bidVal}   Ask ${askVal}   Spread ${spreadVal}   WS ${ageVal}`;
            const spotPct = spotMidChangePct(s);
            const spotR = spotDeltaRlusd(s);
            if (spotPct != null && !Number.isNaN(spotPct)) {
                const sign = spotPct >= 0 ? '+' : '';
                const spotStyle = spotPct >= 0 ? 'color:#4ade80;' : 'color:#facc15;';
                base += `   Spot ??mid <span style="${spotStyle}">${sign}${spotPct.toFixed(2)}%</span>`;
            }
            if (spotR != null && !Number.isNaN(spotR)) {
                const sign = spotR >= 0 ? '+' : '';
                base += `   Spot P&L ${sign}${spotR.toFixed(2)} RLUSD`;
            }
            const sep = "     ???     ";
            const unit = base + sep + base;  // two instances per visible block
            const full = unit + unit;  // duplicate the block for seamless constant scroll (4 total instances)
            document.querySelectorAll('.market-ticker').forEach(el => {
                el.innerHTML = full;
                el.style.animation = 'marquee-seamless 90s linear infinite';
            });
        }

        function bookNormalizeLevels(s) {
            let bids = Array.isArray(s.book_bids) ? s.book_bids.slice() : [];
            let asks = Array.isArray(s.book_asks) ? s.book_asks.slice() : [];
            const bbRaw = s.best_bid != null ? s.best_bid : s.best_bid_rlusd_per_xrp;
            const baRaw = s.best_ask != null ? s.best_ask : s.best_ask_rlusd_per_xrp;
            const bb = bbRaw != null ? parseFloat(bbRaw) : null;
            const ba = baRaw != null ? parseFloat(baRaw) : null;
            const mid = sessionMid(s);
            const hasDepth = bids.length > 0 || asks.length > 0;
            const touchOnly = !hasDepth;
            const normSide = (rows, side) => rows
                .map(r => ({
                    price: parseFloat(r.price != null ? r.price : r.p),
                    size: parseFloat(r.size != null ? r.size : (r.sz != null ? r.sz : 0)),
                    side,
                }))
                .filter(r => !Number.isNaN(r.price) && r.price > 0);
            bids = normSide(bids, 'bid').sort((a, b) => b.price - a.price);
            asks = normSide(asks, 'ask').sort((a, b) => a.price - b.price);
            if (touchOnly && bb != null && !Number.isNaN(bb)) {
                bids = [{ price: bb, size: 0, side: 'bid' }];
            }
            if (touchOnly && ba != null && !Number.isNaN(ba)) {
                asks = [{ price: ba, size: 0, side: 'ask' }];
            }
            return { bids, asks, mid, touchOnly, bb, ba, hasDepth };
        }

        function bookQuoteLadder(s) {
            const levels = Math.max(1, parseInt(s.order_levels, 10) || 3);
            const intents = Array.isArray(s.quote_intents) ? s.quote_intents : [];
            const rows = [];
            for (let lv = 1; lv <= levels; lv++) {
                ['bid', 'ask'].forEach(side => {
                    const row = _intentByLevel(intents, lv, side);
                    if (!row || row.price == null) return;
                    const price = parseFloat(row.price);
                    if (Number.isNaN(price)) return;
                    const planned = lv > 1 || !!row.planned;
                    rows.push({
                        level: lv,
                        side,
                        price,
                        size: row.size_xrp != null ? parseFloat(row.size_xrp) : null,
                        planned,
                    });
                });
            }
            return rows;
        }

        function bookOurQuoteAtPrice(price, side, ladder) {
            if (price == null || Number.isNaN(price) || !ladder.length) return null;
            const tol = 0.000002;
            const hits = ladder.filter(q => q.side === side && Math.abs(q.price - price) <= tol);
            return hits.length ? hits.sort((a, b) => a.level - b.level)[0] : null;
        }

        function bookFormatPrice(p) {
            if (p == null || Number.isNaN(p)) return '???';
            return p.toFixed(6);
        }

        function bookFormatSize(sz, touchOnly) {
            if (sz == null || Number.isNaN(sz) || sz <= 0) {
                return touchOnly ? 'touch' : '???';
            }
            return sz >= 100 ? sz.toFixed(1) : sz.toFixed(2);
        }

        function renderBookDepthCanvas(s) {
            const canvas = document.getElementById('book-depth-canvas');
            const legend = document.getElementById('book-depth-legend');
            if (!canvas) return;
            const wrap = canvas.parentElement;
            const dpr = window.devicePixelRatio || 1;
            const w = Math.max(300, wrap ? Math.floor(wrap.clientWidth - 8) : 640);
            const h = 300;
            canvas.width = Math.floor(w * dpr);
            canvas.height = Math.floor(h * dpr);
            canvas.style.width = w + 'px';
            canvas.style.height = h + 'px';
            const ctx = canvas.getContext('2d');
            if (!ctx) return;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.fillStyle = '#0f172a';
            ctx.fillRect(0, 0, w, h);

            const { bids, asks, mid, touchOnly, bb, ba, hasDepth } = bookNormalizeLevels(s);
            const prices = [];
            bids.forEach(r => prices.push(r.price));
            asks.forEach(r => prices.push(r.price));
            if (mid != null) prices.push(mid);
            if (s.as_reservation != null) {
                const res = parseFloat(s.as_reservation);
                if (!Number.isNaN(res)) prices.push(res);
            }
            if (!prices.length) {
                ctx.fillStyle = '#64748b';
                ctx.font = '13px system-ui, sans-serif';
                ctx.fillText('Waiting for book data???', 16, 28);
                if (legend) legend.innerHTML = '';
                return;
            }

            const padT = 14;
            const padB = 22;
            const padL = 12;
            const padR = 12;
            const midX = Math.floor(w / 2);
            const plotH = h - padT - padB;
            const halfW = midX - padL - 8;
            let pMin = Math.min(...prices);
            let pMax = Math.max(...prices);
            if (pMax - pMin < 1e-8) {
                pMin -= 0.00005;
                pMax += 0.00005;
            } else {
                const padP = (pMax - pMin) * 0.08;
                pMin -= padP;
                pMax += padP;
            }
            const yForPrice = (price) => padT + ((pMax - price) / (pMax - pMin)) * plotH;

            const maxSize = Math.max(
                1,
                ...bids.map(r => r.size || 0),
                ...asks.map(r => r.size || 0)
            );

            // mid vertical
            ctx.strokeStyle = '#60a5fa';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(midX, padT);
            ctx.lineTo(midX, h - padB);
            ctx.stroke();

            const drawBar = (row, isBid) => {
                const y = yForPrice(row.price);
                const barH = Math.max(3, Math.min(14, plotH / Math.max(bids.length, asks.length, 8)));
                const size = row.size > 0 ? row.size : (touchOnly ? maxSize * 0.15 : maxSize * 0.05);
                const barW = Math.max(4, (size / maxSize) * halfW);
                ctx.fillStyle = isBid ? 'rgba(34,197,94,0.55)' : 'rgba(248,113,113,0.55)';
                if (isBid) {
                    ctx.fillRect(midX - barW, y - barH / 2, barW, barH);
                } else {
                    ctx.fillRect(midX, y - barH / 2, barW, barH);
                }
            };

            bids.forEach(r => drawBar(r, true));
            asks.forEach(r => drawBar(r, false));

            const ladder = bookQuoteLadder(s);
            ladder.forEach(q => {
                if (q.price < pMin || q.price > pMax) return;
                const y = yForPrice(q.price);
                const isBid = q.side === 'bid';
                ctx.strokeStyle = q.planned ? 'rgba(147,197,253,0.85)' : '#93c5fd';
                ctx.lineWidth = q.planned ? 1 : 1.5;
                if (q.planned) ctx.setLineDash([3, 3]);
                ctx.beginPath();
                if (isBid) {
                    ctx.moveTo(midX - halfW - 4, y);
                    ctx.lineTo(midX - 6, y);
                } else {
                    ctx.moveTo(midX + 6, y);
                    ctx.lineTo(midX + halfW + 4, y);
                }
                ctx.stroke();
                ctx.setLineDash([]);
                ctx.fillStyle = '#93c5fd';
                ctx.font = '9px ui-monospace, monospace';
                const label = `L${q.level}${q.planned ? '*' : ''}`;
                ctx.fillText(label, isBid ? padL : midX + halfW + 8, y + 3);
            });

            if (s.as_reservation != null) {
                const res = parseFloat(s.as_reservation);
                if (!Number.isNaN(res) && res >= pMin && res <= pMax) {
                    const ry = yForPrice(res);
                    ctx.strokeStyle = '#fbbf24';
                    ctx.setLineDash([5, 4]);
                    ctx.beginPath();
                    ctx.moveTo(padL, ry);
                    ctx.lineTo(w - padR, ry);
                    ctx.stroke();
                    ctx.setLineDash([]);
                }
            }

            // price axis labels
            ctx.fillStyle = '#94a3b8';
            ctx.font = '10px ui-monospace, monospace';
            ctx.fillText(bookFormatPrice(pMax), padL, padT + 8);
            ctx.fillText(bookFormatPrice(pMin), padL, h - padB + 4);
            if (mid != null) {
                const my = yForPrice(mid);
                ctx.fillStyle = '#60a5fa';
                ctx.fillText('mid ' + bookFormatPrice(mid), midX - 36, Math.min(h - padB - 2, my - 4));
            }

            if (legend) {
                const depthNote = hasDepth
                    ? `${bids.length} bids ?? ${asks.length} asks`
                    : 'Touch only (BBO) ??? full depth after ws-engine restart';
                legend.innerHTML = `
                    <span><span class="swatch" style="background:#22c55e"></span>Bids</span>
                    <span><span class="swatch" style="background:#f87171"></span>Asks</span>
                    <span><span class="swatch" style="background:#60a5fa"></span>Mid</span>
                    <span><span class="swatch" style="background:#fbbf24"></span>Reservation</span>
                    <span><span class="swatch" style="background:#93c5fd"></span>Our L1???L3 (* planned)</span>
                    <span>${depthNote}</span>
                `;
            }
        }

        function renderBookOurLadder(s) {
            const el = document.getElementById('book-our-ladder');
            if (!el) return;
            const levels = Math.max(1, parseInt(s.order_levels, 10) || 3);
            const ladder = bookQuoteLadder(s);
            if (!ladder.length) {
                el.innerHTML = '<div style="color:#64748b;font-size:0.72rem;">Waiting for quote_intents???</div>';
                return;
            }
            let html = '';
            for (let lv = 1; lv <= levels; lv++) {
                const bid = ladder.find(q => q.level === lv && q.side === 'bid');
                const ask = ladder.find(q => q.level === lv && q.side === 'ask');
                const planned = (bid && bid.planned) || (ask && ask.planned);
                const status = planned
                    ? '<span style="color:#94a3b8;font-size:0.58rem;">planned</span>'
                    : '<span style="color:#4ade80;font-size:0.58rem;">on ledger</span>';
                const bidTxt = bid
                    ? `${bookFormatPrice(bid.price)} ?? ${bid.size != null && !Number.isNaN(bid.size) ? bid.size.toFixed(1) + ' XRP' : '???'}`
                    : '???';
                const askTxt = ask
                    ? `${bookFormatPrice(ask.price)} ?? ${ask.size != null && !Number.isNaN(ask.size) ? ask.size.toFixed(1) + ' XRP' : '???'}`
                    : '???';
                html += `<div class="book-our-lv">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                        <strong>L${lv}</strong>${status}
                    </div>
                    <div class="metric-row" style="padding:2px 0;"><span class="label">Bid</span><span class="value good">${bidTxt}</span></div>
                    <div class="metric-row" style="padding:2px 0;"><span class="label">Ask</span><span class="value warn">${askTxt}</span></div>
                </div>`;
            }
            el.innerHTML = html;
        }

        function renderBookSplit(s) {
            const { bids, asks, mid, touchOnly, bb, ba, hasDepth } = bookNormalizeLevels(s);
            const ladder = bookQuoteLadder(s);
            const maxRows = 18;
            const bidRows = bids.slice(0, maxRows);
            const askRows = asks.slice(0, maxRows);

            const rowHtml = (rows, side) => rows.map((r) => {
                const hit = bookOurQuoteAtPrice(r.price, side, ladder);
                const isTouch = (side === 'bid' && bb != null && Math.abs(r.price - bb) < 1e-6)
                    || (side === 'ask' && ba != null && Math.abs(r.price - ba) < 1e-6);
                const cls = ['book-level-row'];
                if (hit) cls.push(hit.planned ? 'ours-planned' : 'ours');
                if (isTouch) cls.push('touch');
                const tag = hit ? `<span class="book-lv-tag">L${hit.level}${hit.planned ? '*' : ''}</span>` : '';
                return `<div class="${cls.join(' ')}"><span>${tag}${bookFormatPrice(r.price)}</span><span>${bookFormatSize(r.size, touchOnly)}</span></div>`;
            }).join('') || '<div style="color:#64748b;">???</div>';

            const bidsEl = document.getElementById('book-split-bids');
            const asksEl = document.getElementById('book-split-asks');
            const midEl = document.getElementById('book-split-mid');
            if (bidsEl) bidsEl.innerHTML = rowHtml(bidRows, 'bid');
            if (asksEl) asksEl.innerHTML = rowHtml(askRows, 'ask');
            if (midEl) {
                const spread = s.book_spread_pct != null ? parseFloat(s.book_spread_pct) : null;
                const spreadTxt = spread != null && !Number.isNaN(spread) ? spread.toFixed(3) + '%' : '???';
                midEl.innerHTML = `
                    <div style="font-size:0.6rem;color:#94a3b8;text-transform:uppercase;margin-bottom:4px;">Mid</div>
                    <div class="mid-val">${mid != null ? bookFormatPrice(mid) : '???'}</div>
                    <div style="font-size:0.65rem;color:#94a3b8;margin-top:8px;">Spread</div>
                    <div style="font-weight:600;">${spreadTxt}</div>
                    ${s.as_reservation != null ? `<div style="font-size:0.65rem;color:#fbbf24;margin-top:8px;">Res ${bookFormatPrice(parseFloat(s.as_reservation))}</div>` : ''}
                `;
            }

            setText('book-touch-bid', bb != null ? bookFormatPrice(bb) : '???');
            setText('book-touch-mid', mid != null ? bookFormatPrice(mid) : '???');
            setText('book-touch-ask', ba != null ? bookFormatPrice(ba) : '???');
            const spreadEl = document.getElementById('book-touch-spread');
            if (spreadEl) {
                const sp = s.book_spread_pct != null ? parseFloat(s.book_spread_pct) : null;
                spreadEl.textContent = sp != null && !Number.isNaN(sp) ? sp.toFixed(3) + '%' : '???';
            }
            const ageEl = document.getElementById('book-touch-age');
            if (ageEl) {
                const liveAge = computeLiveWsAge(s);
                ageEl.textContent = formatWsAge(s);
                ageEl.style.color = wsAgeColor(liveAge);
            }

            setText('book-our-res', s.as_reservation != null ? bookFormatPrice(parseFloat(s.as_reservation)) : '???');
            const resDeltaEl = document.getElementById('book-our-res-delta');
            if (resDeltaEl) {
                const d = s.reservation_to_bbo_delta_bps;
                if (d != null && !Number.isNaN(parseFloat(d))) {
                    const bps = parseFloat(d);
                    const sign = bps >= 0 ? '+' : '';
                    const side = s.inside_l1 === true ? 'inside ' : (s.inside_l1 === false ? 'outside ' : '');
                    resDeltaEl.textContent = `${side}${sign}${bps.toFixed(1)} bps`;
                    resDeltaEl.className = 'value ' + (s.inside_l1 ? 'good' : 'warn');
                } else {
                    resDeltaEl.textContent = '???';
                    resDeltaEl.className = 'value';
                }
            }
            renderBookOurLadder(s);
            setText(
                'book-depth-levels',
                hasDepth ? `${bids.length} / ${asks.length}` : 'BBO only'
            );

            const hint = document.getElementById('book-depth-hint');
            if (hint) {
                const lv = Math.max(1, parseInt(s.order_levels, 10) || 3);
                hint.textContent = hasDepth
                    ? `Live WS ladder: ${bids.length} bids ?? ${asks.length} asks. Our L1???L${lv} from quote_intents (* = planned until multi-level sync).`
                    : `Touch (BBO) + our L1???L${lv} ladder (* = L2/L3 planned). Full CLOB depth on next ws-engine restart.`;
            }
        }

        function renderBook(s) {
            if (!s) return;
            renderBookDepthCanvas(s);
            renderBookSplit(s);
        }

        function renderMetrics(s) {
            const pm = s.performance_metrics || {};
            const gradesEl = document.getElementById('metrics-grades');
            if (gradesEl) {
                const grades = pm.grades || [];
                if (!grades.length) {
                    gradesEl.innerHTML = '<div style="font-size:0.75rem;color:#64748b;">Waiting for metrics...</div>';
                } else {
                    gradesEl.innerHTML = grades.map(g => {
                        const pill = g.grade || 'unknown';
                        return `<div class="metric-grade">
                            <div><strong>${g.label}</strong><br><span style="color:#cbd5e1">${g.value}</span><br><small style="opacity:0.65">${g.detail || ''}</small></div>
                            <span class="grade-pill grade-${pill}">${pill}</span>
                        </div>`;
                    }).join('');
                }
            }
            const cap = pm.capture || {};
            const g6 = resolveG6Fields(s);
            const act = pm.activation || {};
            const tierEl = document.getElementById('metrics-g6-tier');
            const tier = g6.tier || act.tier || 'unknown';
            const verEl = document.getElementById('metrics-g6-version');
            if (verEl) {
                const ver = g6VersionShort(g6.version);
                verEl.textContent = ver ? ('(' + ver + ')') : '(version unknown)';
            }
            const cardEl = document.getElementById('metrics-g6-card');
            if (cardEl) {
                cardEl.classList.remove('g6-hold', 'g6-halted', 'g6-watch', 'g6-good');
                if (tier === 'hold') cardEl.classList.add('g6-hold');
                else if (tier === 'halted') cardEl.classList.add('g6-halted');
                else if (tier === 'pilot_watch' || tier === 'thin_edge') cardEl.classList.add('g6-watch');
                else if (tier === 'active' || tier === 'scale_ready') cardEl.classList.add('g6-good');
            }
            if (tierEl) {
                tierEl.textContent = tier.replace(/_/g, ' ');
                tierEl.className = 'grade-pill grade-' + g6TierPillClass(tier);
            }
            const sumEl = document.getElementById('metrics-g6-summary');
            if (sumEl) {
                sumEl.textContent = g6.summary || act.summary || (pm.grades && pm.grades.length ? '???' : 'Waiting for activation grade???');
                if (tier === 'hold' || tier === 'halted') {
                    sumEl.style.color = '#fca5a5';
                } else if (tier === 'pilot_watch' || tier === 'thin_edge') {
                    sumEl.style.color = '#fbbf24';
                } else {
                    sumEl.style.color = '#94a3b8';
                }
            }
            const attnEl = document.getElementById('metrics-g6-attention');
            if (attnEl) {
                const attentionOn = act.attention_on || (pm.grades || []).filter(g => g.grade === 'attention').map(g => g.label || g.id);
                if (tier === 'hold' && attentionOn.length) {
                    attnEl.style.display = 'block';
                    attnEl.textContent = 'Attention on: ' + attentionOn.join(' ?? ');
                } else if (tier === 'pilot_watch' && attentionOn.length) {
                    attnEl.style.display = 'block';
                    attnEl.textContent = 'Watching: ' + attentionOn.join(' ?? ');
                } else if (tier === 'thin_edge') {
                    attnEl.style.display = 'block';
                    attnEl.textContent = 'Thin edge ??? solo book / join floor; gate pass, not scale_ready';
                } else {
                    attnEl.style.display = 'none';
                    attnEl.textContent = '';
                }
            }
            const metaEl = document.getElementById('metrics-g6-meta');
            if (metaEl) {
                const fills = act.ws_fills != null ? act.ws_fills : cap.ws_fills;
                const scope = pm.metrics_scope || (act.scope === 'session' ? 'session' : 'cumulative');
                const gatePass = g6.gatePass;
                const gateTxt = gatePass === false ? 'G6 gate: FAIL' : (gatePass === true ? 'G6 gate: PASS' : '');
                const parts = [];
                const ver = g6VersionShort(g6.version);
                if (ver) parts.push(ver);
                if (fills != null) {
                    parts.push(scope === 'session'
                        ? `${fills} session fills (since boot)`
                        : `${fills} WS fills (CSV)`);
                }
                if (scope === 'session' && pm.capture_cumulative && pm.capture_cumulative.ws_fills != null) {
                    parts.push(`cumulative ${pm.capture_cumulative.ws_fills} fills`);
                }
                if (gateTxt) parts.push(gateTxt);
                metaEl.textContent = parts.join(' ?? ');
            }
            setText('metrics-ws-fills', cap.ws_fills != null ? String(cap.ws_fills) : '???');
            setText('metrics-total-cap', cap.total_capture_xrp != null ? (cap.total_capture_xrp >= 0 ? '+' : '') + cap.total_capture_xrp + ' XRP' : '???');
            setText('metrics-pos-pct', cap.positive_capture_pct != null ? cap.positive_capture_pct + '%' : '???');
            setText('metrics-avg-bps', cap.avg_capture_bps != null ? cap.avg_capture_bps + ' bps' : '???');
            setText('metrics-intel-lines', pm.intel_log_lines != null ? String(pm.intel_log_lines) : '???');
            setText(
                'metrics-obs-spread',
                s.competitor_observed_spread_pct != null
                    ? `${parseFloat(s.competitor_observed_spread_pct).toFixed(3)}%`
                    : '???'
            );
            setText(
                'metrics-comp-pressure',
                s.competitor_pressure != null ? parseFloat(s.competitor_pressure).toFixed(2) : '???'
            );
            setText(
                'metrics-peer-pressure',
                s.peer_pressure != null
                    ? parseFloat(s.peer_pressure).toFixed(2)
                    : (s.peer_lane_count > 0 ? '???' : 'n/a')
            );
            setText(
                'metrics-book-regime-pressure',
                s.book_regime_pressure != null ? parseFloat(s.book_regime_pressure).toFixed(2) : '???'
            );
            setText(
                'metrics-spread-regime-gap',
                s.spread_regime_gap_bps != null ? `${parseFloat(s.spread_regime_gap_bps).toFixed(1)} bps` : '???'
            );
            setText('metrics-book-side-skew', s.book_side_skew_display || '???');
            setText('metrics-clob-amm', s.clob_amm_monitor_display || '???');
            setText('metrics-active-makers', s.num_active_mms != null ? String(s.num_active_mms) : '???');
            const tailEl = document.getElementById('metrics-intel-tail');
            if (tailEl) {
                const rows = pm.recent_intel || [];
                if (!rows.length) {
                    tailEl.textContent = 'No intel_decisions.jsonl yet ??? engine + HUD will append each cycle.';
                } else {
                    tailEl.innerHTML = rows.map(r => {
                        const k = r.kind || '?';
                        const ts = (r.ts_utc || '').slice(11, 19) || '???';
                        if (k === 'peer_scrape') {
                            const skew = r.book_side_skew_label ? ` skew=${r.book_side_skew_label}` : '';
                            return `<div class="intel-log-line">[${ts}] peer peers=${r.peer_lane_count} lane=${r.our_lane_xrp} pressure=${r.peer_pressure_score}${skew}</div>`;
                        }
                        if (k === 'grok_suggestion') {
                            const addr = (r.address || '?').slice(0, 12);
                            return `<div class="intel-log-line">[${ts}] grok ${addr}??? lane=${r.in_peer_lane ? 'in' : 'out'} status=${r.outcome_status || 'pending'}</div>`;
                        }
                        if (k === 'advisory_signal') {
                            return `<div class="intel-log-line">[${ts}] advisory vol??=${r.vol_mult} size??=${r.size_mult} skim=${r.skim_harder}</div>`;
                        }
                        return `<div class="intel-log-line">[${ts}] cycle ${r.cycle} inv=${r.inventory_label} pause_a=${r.pause_asks} g2=${r.g2_grade}</div>`;
                    }).join('');
                }
            }
        }

        async function poll() {
            const statusEl = document.getElementById('hud-poll-status');
            try {
                const res = await fetch('/state', { credentials: 'same-origin' });
                if (!res.ok) throw new Error('bad status ' + res.status);
                const s = await res.json();
                lastState = s;

                renderLive(s);

                // Visible status so "no data / just the card" is never mysterious
                if (statusEl) {
                    const ts = new Date().toLocaleTimeString();
                    const age = formatWsAge(s);
                    const msgs = (s.ws_message_count != null) ? s.ws_message_count : '?';
                    const src = pollBookAgeSource(s);
                    statusEl.textContent = `HUD ${HUD_BUILD} ?? poll ${ts} ?? WS msgs ${msgs} ?? book age ${age} (${src}) ?? OK`;
                    statusEl.style.color = '#4ade80';
                }

                // Debug info in console (F12 ??? Console)
                console.log('[HUD] poll success, keys:', Object.keys(s || {}));
                if (s.last_note) console.log('[HUD] last_note preview:', String(s.last_note).substring(0, 120));
                if (!window.__hudFirst) {
                    window.__hudFirst = true;
                    console.log('[HUD] first data received from /state', Object.keys(s || {}));
                }
            } catch (e) {
                console.error('[HUD] poll error', e);
                if (statusEl) {
                    const msg = (e && e.message && String(e.message).indexOf('401') >= 0)
                        ? 'AUTH REQUIRED ??? re-login at /login then reopen Live tab'
                        : 'POLL FAILED ??? keep SSH tunnel open: ssh -L 8765:127.0.0.1:8765 root@VPS (then http://localhost:8765)';
                    statusEl.textContent = msg;
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
            if (page === 'config') {
                loadTelegramConfig();
            }
            if (page === 'reports') {
                loadReportsCatalog();
            }
        }

        async function loadReportsCatalog() {
            const statusEl = document.getElementById('reports-catalog-status');
            const container = document.getElementById('reports-catalog');
            if (!container) return;
            if (statusEl) statusEl.textContent = 'Loading report catalog???';
            try {
                const resp = await fetch('/reports/catalog');
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                const data = await resp.json();
                renderReportsCatalog(data.reports || []);
                if (statusEl) {
                    statusEl.textContent = `${(data.reports || []).length} reports available ?? opens read-only from logs/`;
                }
            } catch (e) {
                if (statusEl) statusEl.textContent = 'Could not load reports catalog.';
                container.innerHTML = '<div style="color:#f87171;font-size:0.85rem;">Failed to fetch /reports/catalog ??? is ws-hud running?</div>';
            }
        }

        function renderReportsCatalog(reports) {
            const container = document.getElementById('reports-catalog');
            if (!container) return;
            if (!reports.length) {
                container.innerHTML = '<div style="color:#64748b;">No reports configured.</div>';
                return;
            }
            const byCategory = {};
            reports.forEach(r => {
                const cat = r.category || 'Other';
                if (!byCategory[cat]) byCategory[cat] = [];
                byCategory[cat].push(r);
            });
            const order = ['Operator', 'Gates', 'Soak analysis', 'Other'];
            let html = '';
            order.forEach(cat => {
                const rows = byCategory[cat];
                if (!rows || !rows.length) return;
                html += `<div class="card full-width" style="margin-bottom:10px;"><div class="label">${cat}</div>`;
                rows.forEach(r => {
                    const soak = r.soak_safe
                        ? '<span style="background:#14532d;color:#86efac;font-size:0.65rem;padding:2px 6px;border-radius:3px;margin-right:6px;">Soak-safe</span>'
                        : '<span style="background:#7f1d1d;color:#fca5a5;font-size:0.65rem;padding:2px 6px;border-radius:3px;margin-right:6px;">Engine change</span>';
                    const restart = r.engine_restart
                        ? '<span style="color:#fbbf24;font-size:0.68rem;">Requires ws-engine restart</span>'
                        : '<span style="color:#93c5fd;font-size:0.68rem;">No ws-engine restart</span>';
                    html += `<div style="border-top:1px solid #334155;padding:10px 0;">
                        <div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;justify-content:space-between;">
                            <div>
                                <strong style="color:#f1f5f9;">${r.title}</strong>
                                <span style="font-size:0.7rem;color:#64748b;margin-left:8px;">ID: <code>${r.id}</code></span>
                                <div style="font-size:0.75rem;color:#94a3b8;margin-top:2px;">${r.subtitle}</div>
                            </div>
                            <button type="button" class="report-open-btn" data-report-id="${r.id}"
                                style="background:#2563eb;color:#fff;border:none;border-radius:4px;padding:6px 12px;font-size:0.75rem;cursor:pointer;white-space:nowrap;">
                                Open in new tab ???
                            </button>
                        </div>
                        <div style="margin-top:6px;">${soak} ${restart}</div>
                        <div style="font-size:0.78rem;color:#cbd5e1;margin-top:6px;">${r.description}</div>
                        <div style="font-size:0.68rem;color:#64748b;margin-top:4px;">${r.phase_ref ? r.phase_ref + ' ?? ' : ''}CLI: <code>${r.cli_command}</code></div>
                    </div>`;
                });
                html += '</div>';
            });
            container.innerHTML = html;
            container.querySelectorAll('.report-open-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const id = btn.getAttribute('data-report-id');
                    if (id) openReportInNewTab(id);
                });
            });
        }

        function openReportInNewTab(reportId) {
            const url = '/report/' + encodeURIComponent(reportId) + '?t=' + Date.now();
            window.open(url, '_blank', 'noopener,noreferrer');
        }

        function _populateHourSelect(selectId) {
            const sel = document.getElementById(selectId);
            if (!sel || sel.options.length) return;
            for (let h = 0; h < 24; h++) {
                const opt = document.createElement('option');
                opt.value = String(h);
                opt.textContent = `${String(h).padStart(2, '0')}:00 UTC`;
                sel.appendChild(opt);
            }
        }

        function _updateTelegramScheduleStatus(snap) {
            const el = document.getElementById('tg-schedule-status');
            if (!el || !snap) return;
            const label = snap.telegram_quiet_label || '';
            if (!snap.telegram_quiet_hours_enabled) {
                el.textContent = snap.telegram_configured
                    ? 'Reports allowed 24/7 (quiet hours off).'
                    : 'Telegram not fully configured ??? set token + chat ID in credentials.';
                el.style.color = snap.telegram_configured ? '#94a3b8' : '#fbbf24';
                return;
            }
            if (snap.hourly_report_allowed_now) {
                el.textContent = `Outside quiet window (${label}) ??? hourly reports will send.`;
                el.style.color = '#4ade80';
            } else {
                el.textContent = `Quiet now (${label}) ??? hourly reports suppressed.`;
                el.style.color = '#fbbf24';
            }
        }

        async function loadTelegramConfig() {
            _populateHourSelect('tg-quiet-start');
            _populateHourSelect('tg-quiet-end');
            try {
                const resp = await fetch('/get_telegram_config');
                if (!resp.ok) return;
                const snap = await resp.json();
                const hourly = document.getElementById('tg-hourly-enabled');
                const kill = document.getElementById('tg-kill-alerts-enabled');
                const hudUrl = document.getElementById('tg-hud-url');
                const quiet = document.getElementById('tg-quiet-enabled');
                const qStart = document.getElementById('tg-quiet-start');
                const qEnd = document.getElementById('tg-quiet-end');
                if (hourly) hourly.checked = !!snap.telegram_hourly_report_enabled;
                if (kill) kill.checked = !!snap.telegram_kill_alerts_enabled;
                if (hudUrl) hudUrl.value = snap.telegram_hud_url || '';
                if (quiet) quiet.checked = !!snap.telegram_quiet_hours_enabled;
                if (qStart) qStart.value = String(snap.telegram_quiet_start_hour ?? 22);
                if (qEnd) qEnd.value = String(snap.telegram_quiet_end_hour ?? 7);
                _updateTelegramScheduleStatus(snap);
            } catch (e) {
                const el = document.getElementById('tg-schedule-status');
                if (el) el.textContent = 'Could not load Telegram settings.';
            }
        }

        async function loadCompetitorNicknames() {
            try {
                const resp = await fetch('/competitor_nicknames');
                if (!resp.ok) return;
                const data = await resp.json();
                competitorNicknames = data.nicknames || {};
            } catch (e) {
                /* optional ??? /state may include nicknames on next poll */
            }
        }

        async function applyTelegramConfig() {
            const hourly = document.getElementById('tg-hourly-enabled');
            const kill = document.getElementById('tg-kill-alerts-enabled');
            const hudUrl = document.getElementById('tg-hud-url');
            const quiet = document.getElementById('tg-quiet-enabled');
            const qStart = document.getElementById('tg-quiet-start');
            const qEnd = document.getElementById('tg-quiet-end');
            const statusEl = document.getElementById('tg-schedule-status');
            const payload = {
                hourly_enabled: !!(hourly && hourly.checked),
                kill_alerts_enabled: !!(kill && kill.checked),
                hud_url: hudUrl ? hudUrl.value.trim() : '',
                quiet_hours_enabled: !!(quiet && quiet.checked),
                quiet_start_hour: qStart ? parseInt(qStart.value, 10) : 22,
                quiet_end_hour: qEnd ? parseInt(qEnd.value, 10) : 7,
            };
            if (statusEl) statusEl.textContent = 'Saving???';
            try {
                const resp = await fetch('/set_telegram_config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const snap = await resp.json();
                _updateTelegramScheduleStatus(snap);
                let msg = 'Telegram settings saved to config.yaml.';
                if (snap.timer_message) {
                    msg += snap.timer_ok ? ` Timer: ${snap.timer_message}.` : ` Timer: ${snap.timer_message}`;
                }
                if (statusEl) statusEl.textContent = msg;
            } catch (e) {
                if (statusEl) statusEl.textContent = 'Save failed ??? check HUD logs.';
            }
        }

        function saveCredentialsDemo() {
            const xrplAddrEl = document.getElementById('inv-bot-address');
            const xrplAddr = (xrplAddrEl && xrplAddrEl.dataset.address) || (xrplAddrEl ? xrplAddrEl.textContent : '') || '';
            const xrplSecret = document.getElementById('creds-xrpl-secret').value || '';
            const tgToken = document.getElementById('creds-telegram-token').value || '';
            const tgChat = document.getElementById('creds-telegram-chat').value || '';
            const otherApi = document.getElementById('creds-other-api').value || '';

            if (window._current_state) {
                window._current_state.creds_xrpl_address = xrplAddr;
                window._current_state.creds_xrpl_secret = xrplSecret ? '********' : '';
                window._current_state.creds_telegram_token = tgToken;
                window._current_state.creds_telegram_chat = tgChat;
                window._current_state.creds_other_api = otherApi;
            }

            alert('Credentials saved in this HUD session only (not written to disk).\n\n' +
                  'XRPL Bot Account Address: ' + (xrplAddr || '(empty)') + '\n' +
                  'XRPL Secret: ' + (xrplSecret ? '******** (hidden)' : '(empty)') + '\n' +
                  'Telegram Bot Token: ' + (tgToken || '(empty)') + '\n' +
                  'Telegram Chat ID: ' + (tgChat || '(empty)') + '\n' +
                  'Other API Key: ' + (otherApi || '(empty)') + '\n\n' +
                  'For persistent credentials: edit config/credentials.local.yaml (never commit secrets) and restart xledgermate.\n' +
                  'Full account setup: Streamlit GUI (python main.py --mode gui).');
        }

        // --- Inventory tab helpers (funding / QR / demo send) ---
        let demoBalancePatch = { xrp: null, rlusd: null };  // client-side overrides so demo txs feel live

        function getEffectiveBalance(s, key) {
            if (!s) return null;
            if (key === 'xrp' && demoBalancePatch.xrp != null) return demoBalancePatch.xrp;
            if (key === 'rlusd' && demoBalancePatch.rlusd != null) return demoBalancePatch.rlusd;
            return s.balance_xrp != null && key==='xrp' ? parseFloat(s.balance_xrp) : (s.balance_rlusd != null && key==='rlusd' ? parseFloat(s.balance_rlusd) : null);
        }

        function applyDemoBalancePatchToState(s) {
            if (!s) return;
            if (demoBalancePatch.xrp != null) s.balance_xrp = demoBalancePatch.xrp;
            if (demoBalancePatch.rlusd != null) s.balance_rlusd = demoBalancePatch.rlusd;
        }

        function copyToClipboard(text) {
            if (!text) return;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(() => {
                    const orig = event && event.target ? event.target.textContent : '';
                    // quick visual feedback
                }).catch(() => {});
            } else {
                // fallback
                const ta = document.createElement('textarea');
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
            }
        }

        function showQRModal(addr) {
            if (!addr) addr = 'rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh';
            const modal = document.getElementById('qr-modal');
            const img = document.getElementById('qr-img');
            const addrEl = document.getElementById('qr-addr');
            const statusEl = document.getElementById('qr-status');
            if (addrEl) addrEl.textContent = addr;
            if (statusEl) statusEl.textContent = '';
            if (img) {
                img.style.display = 'block';
                // Real QR from server (scannable).
                img.src = '/qr?text=' + encodeURIComponent(addr);
                img.alt = 'QR for ' + addr;

                const checkSize = () => {
                    // If server fell back to 1x1 placeholder (not restarted after pip install), warn the user
                    if (img.naturalWidth <= 2 || img.naturalHeight <= 2) {
                        img.style.display = 'none';
                        if (statusEl) {
                            statusEl.textContent = 'QR unavailable ??? restart xledgermate-ws-hud after: pip install qrcode pillow';
                            statusEl.style.color = '#f87171';
                        }
                    } else if (statusEl) {
                        statusEl.textContent = 'Real scannable QR (works with Xaman etc.)';
                        statusEl.style.color = '#4ade80';
                    }
                };

                img.onload = checkSize;
                img.onerror = () => {
                    img.style.display = 'none';
                    if (statusEl) {
                        statusEl.textContent = 'Could not load QR image. Is the HUD server running on 8765?';
                        statusEl.style.color = '#f87171';
                    }
                };
            }
            if (modal) modal.classList.add('show');
        }

        function closeQRModal() {
            const modal = document.getElementById('qr-modal');
            if (modal) modal.classList.remove('show');
        }

        function appendTxLog(message) {
            const log = document.getElementById('inv-tx-log');
            if (!log) return;
            const ts = new Date().toLocaleTimeString();
            const line = `[${ts}] ${message}\n`;
            if (log.textContent.indexOf('No sends') === 0) log.textContent = '';
            log.textContent = line + log.textContent;
            const lines = log.textContent.trim().split('\n');
            if (lines.length > 12) log.textContent = lines.slice(0, 12).join('\n') + '\n';
        }

        async function performLiveSend(asset, amount, dest) {
            const resEl = document.getElementById('send-result');
            const confirmRunning = !!(document.getElementById('send-confirm-running') || {}).checked;
            const confirmText = (document.getElementById('send-confirm-text') || {}).value || '';
            if (resEl) {
                resEl.style.color = '#94a3b8';
                resEl.textContent = 'Submitting payment???';
            }
            try {
                const r = await fetch('/send_funds', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        destination: dest,
                        amount: amount,
                        asset: asset,
                        confirm_engine_running: confirmRunning,
                        confirm_text: confirmText,
                    }),
                });
                const j = await r.json();
                if (!resEl) return;
                if (j.ok) {
                    resEl.style.color = '#4ade80';
                    resEl.textContent = (j.message || 'Sent.') + (j.tx_hash ? ` tx=${j.tx_hash}` : '');
                    appendTxLog(`${j.message}${j.tx_hash ? ' ?? ' + j.tx_hash : ''}`);
                    const confirmInput = document.getElementById('send-confirm-text');
                    if (confirmInput) confirmInput.value = '';
                } else {
                    resEl.style.color = '#f87171';
                    resEl.textContent = j.message || 'Send failed.';
                }
            } catch (e) {
                if (resEl) {
                    resEl.style.color = '#f87171';
                    resEl.textContent = 'Send failed: ' + e;
                }
            }
        }

        function isProductionHud(s) {
            return s && s.production_source === 'ws-engine';
        }

        async function productionEngineAction(action) {
            if (lastState && isProductionHud(lastState) && (action === 'stop' || action === 'restart')) {
                const verb = action === 'stop' ? 'Stop' : 'Restart';
                const ok = confirm(
                    `${verb} ws-engine?\n\nThis pauses live quoting and breaks soak continuity. ` +
                    'Offers may be pulled. Only do this if you mean to.'
                );
                if (!ok) return;
            }
            try {
                const r = await fetch('/engine/' + action, { method: 'POST' });
                const j = await r.json();
                alert(j.message || (j.ok ? 'OK' : 'Failed'));
            } catch (e) {
                alert('Engine control failed: ' + e + '\n\nKeep SSH tunnel open (port 8765).');
            }
        }

        function updateEngineControlsUi(s) {
            const hint = document.getElementById('engine-controls-hint');
            const label = document.getElementById('engine-controls-label');
            if (!hint) return;
            if (isProductionHud(s)) {
                if (label) label.textContent = 'Engine Controls';
                const live = s.dry_run === false;
                hint.textContent = live
                    ? 'Mainnet live ??? offers on ledger. Controls systemd xledgermate.'
                    : 'Paper mode (dry_run=true) ??? no live offers. Set dry_run=false in config to go live.';
            } else {
                if (label) label.textContent = 'Engine Controls (local lab)';
                hint.textContent = 'Local lab ??? run live_pure_as_tester --serve-hud.';
            }
        }

        function attachDemoHandlers() {
            const startBtn = document.getElementById('btn-start-engine');
            if (startBtn) {
                startBtn.addEventListener('click', () => {
                    triggerAnim(startBtn, 'btn-press', 150);
                    if (lastState && isProductionHud(lastState)) {
                        productionEngineAction('start');
                    } else {
                        alert('Lab HUD only. On VPS production, use the tunnel to :8765 with ws-engine running.');
                    }
                });
            }
            const stopBtn = document.getElementById('btn-stop-engine');
            if (stopBtn) {
                stopBtn.addEventListener('click', () => {
                    triggerAnim(stopBtn, 'btn-press', 150);
                    if (lastState && isProductionHud(lastState)) {
                        productionEngineAction('stop');
                    } else {
                        alert('Lab HUD only.');
                    }
                });
            }
            const restartBtn = document.getElementById('btn-restart-engine');
            if (restartBtn) {
                restartBtn.addEventListener('click', () => {
                    triggerAnim(restartBtn, 'btn-press', 150);
                    if (lastState && isProductionHud(lastState)) {
                        productionEngineAction('restart');
                    } else {
                        alert('Lab HUD only.');
                    }
                });
            }

            // Profile select (demo only)
            const profileSel = document.getElementById('config-profile-select');
            if (profileSel) {
                profileSel.addEventListener('change', () => {
                    const prof = document.getElementById('config-profile');
                    if (prof) {
                        prof.textContent = profileSel.value + (isProductionHud(lastState || {})
                            ? ' ??? change active_profile in config.yaml and restart engine'
                            : ' ??? restart lab tester with --profile to apply');
                    }
                });
            }

            // Fetch available models for the current intel key (uses the /list_models backend)
            async function fetchAvailableModels() {
                const resDiv = document.getElementById('model-list-result');
                if (!resDiv) return;

                // First, push the current form values (provider + key + model + enabled) to the server
                // so /list_models sees the key that the user just typed.
                const provEl = document.getElementById('intel-ai-provider');
                const keyIn = document.getElementById('intel-ai-key');
                const modelEl = document.getElementById('intel-ai-model');
                const enEl = document.getElementById('intel-ai-enabled');

                const provider = provEl ? provEl.value : 'grok';
                const keyVal = keyIn ? keyIn.value : '';
                const model = modelEl ? modelEl.value : 'grok-3';
                const enabled = !!(enEl && enEl.checked);

                if (keyVal) {
                    try {
                        await fetch('/set_intel_config', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ provider, key: keyVal, model, enabled })
                        });
                        // Update the green "Key set" status immediately (same logic as Apply button)
                        const aiKeyWrap = keyIn ? keyIn.parentElement : null;
                        if (keyIn && aiKeyWrap) {
                            keyIn.style.display = 'none';
                            let status = document.getElementById('intel-ai-key-status');
                            if (!status) {
                                status = document.createElement('span');
                                status.id = 'intel-ai-key-status';
                                status.style.fontSize = '0.75rem';
                                status.style.color = '#22c55e';
                                status.style.marginLeft = '6px';
                                aiKeyWrap.appendChild(status);
                            }
                            status.textContent = 'Key set (hidden for security) ??? length: ' + keyVal.length + ' (applied for model fetch)';
                        }
                    } catch (e) {
                        console.warn('Auto-apply before model fetch failed', e);
                    }
                }

                resDiv.textContent = 'Querying xAI /v1/models with the applied key...';
                try {
                    const r = await fetch('/list_models');
                    const data = await r.json();
                    if (data.error) {
                        resDiv.innerHTML = '<span style="color:#f87171">Error: ' + data.error + '</span>';
                    } else if (data.models && data.models.length > 0) {
                        // Always ensure grok-3 is available as a strong recommendation
                        let models = [...data.models];
                        if (!models.includes('grok-3')) {
                            models.unshift('grok-3');
                        }
                        // Put grok-3 first
                        models = models.filter(m => m !== 'grok-3');
                        models.unshift('grok-3');

                        let options = models.map(m => {
                            const label = m === 'grok-3' ? 'grok-3 (recommended)' : m;
                            return `<option value="${m}">${label}</option>`;
                        }).join('');

                        resDiv.innerHTML = (data.note ? data.note + '<br>' : '') + 
                            'Select model (auto-applies on change):<br>' +
                            `<select id="temp-model-select" style="width:100%; font-size:0.8rem; margin-top:4px;">${options}</select>`;

                        setTimeout(() => {
                            const sel = document.getElementById('temp-model-select');
                            if (sel) {
                                sel.addEventListener('change', () => {
                                    if (sel.value) {
                                        useModel(sel.value);
                                    }
                                });
                                sel.value = 'grok-3';
                            }
                        }, 0);
                    } else {
                        resDiv.innerHTML = 'No models from API. <button onclick="useModel(\'grok-3\')">Try grok-3 (recommended)</button>';
                    }
                } catch (e) {
                    resDiv.innerHTML = '<span style="color:#f87171">Fetch failed: ' + e + '</span>';
                }
            }

            function useModel(modelName) {
                const modelInput = document.getElementById('intel-ai-model');
                if (modelInput) {
                    modelInput.value = modelName;
                    // flash to show it changed
                    modelInput.style.background = '#1e40af';
                    setTimeout(() => { if (modelInput) modelInput.style.background = ''; }, 600);
                }
                // Also auto-apply so the Analyze button immediately uses the chosen model
                const applyBtn = document.getElementById('btn-apply-config');
                if (applyBtn) {
                    applyBtn.click();
                } else {
                    // Fallback: do the POST ourselves
                    const provEl = document.getElementById('intel-ai-provider');
                    const keyIn = document.getElementById('intel-ai-key');
                    const enEl = document.getElementById('intel-ai-enabled');
                    fetch('/set_intel_config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            provider: provEl ? provEl.value : 'grok',
                            key: keyIn ? keyIn.value : '',
                            model: modelName,
                            enabled: !!(enEl && enEl.checked)
                        })
                    });
                }
            }

            // Make sure the helpers are available globally too (defensive for any inline or timing issues)
            window.fetchAvailableModels = fetchAvailableModels;
            window.useModel = useModel;

            // Wire the fetch models button (using addEventListener for reliable scope)
            const fetchModelsBtn = document.getElementById('btn-fetch-models');
            if (fetchModelsBtn) {
                fetchModelsBtn.addEventListener('click', () => {
                    if (typeof window.fetchAvailableModels === 'function') {
                        window.fetchAvailableModels();
                    } else {
                        console.error('fetchAvailableModels not available');
                        const resDiv = document.getElementById('model-list-result');
                        if (resDiv) resDiv.textContent = 'Error: function not loaded. Hard refresh the page (Ctrl+Shift+R) or restart ws-hud.';
                    }
                });
            }

            // Config apply button (demo)
            const applyBtn = document.getElementById('btn-apply-config');
            const applyTgBtn = document.getElementById('btn-apply-telegram');
            if (applyTgBtn) {
                applyTgBtn.addEventListener('click', () => {
                    if (typeof applyTelegramConfig === 'function') applyTelegramConfig();
                });
            }
            _populateHourSelect('tg-quiet-start');
            _populateHourSelect('tg-quiet-end');
            if (applyBtn) {
                applyBtn.addEventListener('click', () => {
                    const provEl = document.getElementById('intel-ai-provider');
                    const keyIn = document.getElementById('intel-ai-key');
                    const modelEl = document.getElementById('intel-ai-model');
                    const enEl = document.getElementById('intel-ai-enabled');

                    const provider = provEl ? provEl.value : 'stub';
                    const keyVal = keyIn ? keyIn.value : '';
                    const model = modelEl ? modelEl.value : 'grok-3';
                    const enabled = !!(enEl && enEl.checked);

                    const intelConfig = { provider: provider, key: keyVal ? '********' : '', model: model, enabled: enabled };

                    if (window._current_state) {
                        window._current_state.intel_ai_provider = provider;
                        window._current_state.intel_ai_key = keyVal;
                        window._current_state.intel_ai_model = model;
                        window._current_state.intel_ai_enabled = enabled;
                    }

                    // Push to server (updates _current_state immediately; /analyze uses it right away)
                    fetch('/set_intel_config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ provider: provider, key: keyVal, model: model, enabled: enabled })
                    }).then(() => {
                        // Immediate client feedback + force values so "grok" + key status hold visibly even before next poll
                        if (provEl) provEl.value = provider;
                        if (modelEl) {
                            if (provider === 'grok' && (!modelEl.value || modelEl.value === 'llama3')) {
                                modelEl.value = 'grok-3';
                            } else {
                                modelEl.value = model;
                            }
                        }
                        const aiKey = document.getElementById('intel-ai-key');
                        const aiKeyWrap = document.getElementById('intel-ai-key-wrap') || (aiKey ? aiKey.parentElement : null);
                        if (keyVal.length > 0 && aiKey && aiKeyWrap) {
                            aiKey.style.display = 'none';
                            window._lastAppliedAiKeyLen = keyVal.length;
                            let status = document.getElementById('intel-ai-key-status');
                            if (!status) {
                                status = document.createElement('span');
                                status.id = 'intel-ai-key-status';
                                status.style.fontSize = '0.75rem';
                                status.style.color = '#22c55e';
                                status.style.marginLeft = '6px';
                                aiKeyWrap.appendChild(status);
                            }
                            status.textContent = 'Key set (hidden for security) ??? length: ' + keyVal.length + ' (applied)';
                            let clearBtn = document.getElementById('intel-ai-key-clear');
                            if (!clearBtn) {
                                clearBtn = document.createElement('button');
                                clearBtn.id = 'intel-ai-key-clear';
                                clearBtn.textContent = 'Clear';
                                clearBtn.style.fontSize = '0.6rem';
                                clearBtn.style.marginLeft = '4px';
                                clearBtn.onclick = () => {
                                    if (aiKey) aiKey.value = '';
                                    if (status) status.remove();
                                    if (clearBtn) clearBtn.remove();
                                    if (aiKey) aiKey.style.display = '';
                                    window._intelConfigUserTouched = 0;
                                    window._lastAppliedAiKeyLen = 0;
                                };
                                aiKeyWrap.appendChild(clearBtn);
                            }
                        }
                        // Long grace so renderLive population cannot clobber the visual right after commit (tester push race)
                        window._intelConfigUserTouched = Date.now() + 45000; // 45s
                    }).catch(() => {});

                    // Also immediately extend grace on click (before promise resolves) so very next 800ms poll is less likely to race the .then
                    window._intelConfigUserTouched = Date.now() + 45000;

                    const prod = lastState && isProductionHud(lastState);
                    alert((prod
                        ? 'Intelligence settings saved to logs/hud_intel_config.json.\n\n'
                        : 'Intelligence settings captured (lab session).\n\n') +
                          JSON.stringify(intelConfig, null, 2) +
                          '\n\nTrading params (L1???L3 sizes, risk capital, inventory target): config/config.yaml or Streamlit GUI.\n\nAI is advisory only ??? it does not override A-S reservation or the inside-book guard.');
                });
            }

            // Credentials save button
            const saveBtn = document.getElementById('btn-save-creds');
            if (saveBtn) {
                saveBtn.addEventListener('click', saveCredentialsDemo);
            }

            // === Inventory tab wiring ===
            const copyBtn = document.getElementById('btn-copy-address');
            if (copyBtn) {
                copyBtn.addEventListener('click', (e) => {
                    triggerAnim(copyBtn, 'btn-press', 120);
                    const addrBox = document.getElementById('inv-bot-address');
                    const addr = (addrBox && addrBox.dataset.address) || (addrBox ? addrBox.textContent : '');
                    copyToClipboard(addr);
                    const old = copyBtn.textContent;
                    copyBtn.textContent = '??? Copied';
                    setTimeout(() => { if (copyBtn) copyBtn.textContent = old; }, 1200);
                });
            }

            const qrBtn = document.getElementById('btn-show-qr');
            if (qrBtn) {
                qrBtn.addEventListener('click', () => {
                    triggerAnim(qrBtn, 'btn-press', 120);
                    const addrBox = document.getElementById('inv-bot-address');
                    const addr = (addrBox && addrBox.dataset.address) || (addrBox ? addrBox.textContent : 'rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh');
                    showQRModal(addr);
                });
            }

            const closeQr = document.getElementById('btn-close-qr');
            if (closeQr) closeQr.addEventListener('click', closeQRModal);

            // Also close modal on background click
            const qrModal = document.getElementById('qr-modal');
            if (qrModal) {
                qrModal.addEventListener('click', (e) => { if (e.target === qrModal) closeQRModal(); });
                document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && qrModal.classList.contains('show')) closeQRModal(); });
            }

            const sendBtn = document.getElementById('btn-live-send');
            if (sendBtn) {
                sendBtn.addEventListener('click', () => {
                    triggerAnim(sendBtn, 'btn-press', 120);
                    const asset = (document.getElementById('send-asset') || {}).value || 'XRP';
                    const amt = parseFloat((document.getElementById('send-amount') || {}).value || '0');
                    const dest = ((document.getElementById('send-dest') || {}).value || '').trim();
                    if (!dest.startsWith('r')) {
                        const res = document.getElementById('send-result');
                        if (res) {
                            res.style.color = '#f87171';
                            res.textContent = 'Enter a valid destination address (r...).';
                        }
                        return;
                    }
                    if (!(amt > 0)) {
                        const res = document.getElementById('send-result');
                        if (res) res.textContent = 'Amount must be > 0.';
                        return;
                    }
                    if (!confirm(`Send ${amt} ${asset} to ${dest}?\n\nThis is a LIVE on-ledger payment from the bot account.`)) {
                        return;
                    }
                    performLiveSend(asset, amt, dest);
                });
            }
            const sendDestInput = document.getElementById('send-dest');
            if (sendDestInput) {
                sendDestInput.addEventListener('input', () => {
                    sendDestInput.dataset.userEdited = '1';
                });
            }

            // Intelligence tab demo controls (simulate harder scraping since real is in Python provider)
            const forceBtn = document.getElementById('btn-force-comp-scrape');
            if (forceBtn) {
                forceBtn.addEventListener('click', async () => {
                    triggerAnim(forceBtn, 'btn-press', 120);
                    const log = document.getElementById('intel-scrape-log');
                    if (lastState && isProductionHud(lastState)) {
                        if (log) log.textContent = 'Refreshing HUD state ??? production engine scrapes peer lane every ~15s.';
                        try {
                            const res = await fetch('/state');
                            if (res.ok) {
                                lastState = await res.json();
                                renderLive(lastState);
                            }
                        } catch (e) { /* next poll will recover */ }
                        return;
                    }
                    if (lastState) {
                        lastState.competitor_pressure = Math.random() * 0.6;
                        lastState.competitor_skim_advice = lastState.competitor_pressure < 0.3
                            ? 'SCRAPE HARDER: Low pressure ??? A-S can lean more aggressive.'
                            : 'Monitor pressure ??? A-S math decides presence.';
                        lastState.top_competitors = [
                            {account: 'rDemoM1???', account_full: 'rDemoMaker1AddressForGrokAnalysisTest123456789', last_spread: 0.075, avg_spread: 0.085, activity: 650, sides: 'b180/a95'},
                            {account: 'rDemoM2???', account_full: 'rDemoMaker2AddressForGrokAnalysisTest987654321', last_spread: 0.12, avg_spread: 0.105, activity: 420, sides: 'b55/a210'},
                        ];
                        renderLive(lastState);
                    }
                    if (log) log.textContent = 'Lab scrape simulated ??? use production HUD for real on-chain peer lane.';
                });
            }

            const histBtn = document.getElementById('btn-sim-historical');
            if (histBtn) {
                histBtn.addEventListener('click', () => {
                    triggerAnim(histBtn, 'btn-press', 120);
                    const log = document.getElementById('intel-scrape-log');
                    if (lastState && isProductionHud(lastState)) {
                        if (log) log.textContent = 'Historical walk is lab-only ??? production uses live peer-lane scrape.';
                        return;
                    }
                    if (log) log.textContent = 'Lab: simulated 1h historical context (extend scrape_historical() for real ledger walk).';
                    // Populate some demo top competitors
                    if (lastState) {
                        // Use plausible full-length fake r-addresses so "Analyze with AI" has something real-looking to send
                        lastState.top_competitors = [
                            {account: "rComp1...", account_full: "rComp1DemoAddressForTestingAIBotAnalysis123456", last_spread: 0.082, avg_spread: 0.091, activity: 1240, sides: "b312/a289"},
                            {account: "rComp2...", account_full: "rComp2DemoAddressForTestingAIBotAnalysis654321", last_spread: 0.067, avg_spread: 0.071, activity: 890, sides: "b201/a177"},
                        ];
                        lastState.competitor_depth_xrp = 142.3;
                        renderLive(lastState);
                    }
                });
            }

            // Intelligence API: analyze a specific competitor address using Config tab settings (real Grok if configured)
            async function runIntelAnalyze(addr, options = {}) {
                const shadowMode = !!options.shadowMode;
                const resultEl = document.getElementById(
                    options.resultElId || (shadowMode ? 'cal-ai-result' : 'intel-ai-result')
                );
                const addrInput = document.getElementById(
                    options.addrInputId || (shadowMode ? 'cal-analyze-addr' : 'intel-analyze-addr')
                );
                if (options.triggerBtn) {
                    triggerAnim(options.triggerBtn, 'btn-press', 120);
                }
                if (addrInput && addr) {
                    addrInput.value = addr;
                }
                if (!addr || addr.length < 25) {
                    if (resultEl) {
                        resultEl.textContent = 'No valid r-address ??? set bot_account_address in config or pick a peer from the list.';
                    }
                    return;
                }
                if (resultEl) {
                    if (!shadowMode) pinnedIntelAiResult = null;
                    const prov = (document.getElementById('intel-ai-provider') || {}).value || 'AI';
                    const mode = options.selfAudit ? 'self-audit' : (shadowMode ? 'shadow E3 calibration' : 'competitor');
                    resultEl.textContent = `Applying API config, then calling ${prov} (${mode}) for ${addr}...`;
                    resultEl.scrollTop = 0;
                    try {
                        await applyIntelConfigFromForm();
                        const payload = { address: addr };
                        if (shadowMode) {
                            payload.analysis_context = 'shadow_e3_calibration';
                        }
                        if (lastState) {
                            if (lastState.competitor_pressure != null) payload.competitor_pressure = lastState.competitor_pressure;
                            if (lastState.competitor_observed_spread_pct != null) payload.observed_spread_pct = lastState.competitor_observed_spread_pct;
                            if (lastState.competitor_depth_xrp != null) payload.competitor_depth_xrp = lastState.competitor_depth_xrp;
                            if (lastState.inventory_label) payload.inventory_label = lastState.inventory_label;
                            if (shadowMode && lastState.shadow_e3_lane_xrp != null) {
                                payload.our_lane_xrp = lastState.shadow_e3_lane_xrp;
                                payload.peer_lane_low_xrp = lastState.shadow_peer_lane_low_xrp;
                                payload.peer_lane_high_xrp = lastState.shadow_peer_lane_high_xrp;
                                payload.peer_lane_count = lastState.shadow_peer_lane_count;
                                payload.peer_pressure_score = lastState.shadow_peer_pressure_score;
                            } else {
                                if (lastState.our_lane_xrp != null) payload.our_lane_xrp = lastState.our_lane_xrp;
                                if (lastState.peer_lane_low_xrp != null) payload.peer_lane_low_xrp = lastState.peer_lane_low_xrp;
                                if (lastState.peer_lane_high_xrp != null) payload.peer_lane_high_xrp = lastState.peer_lane_high_xrp;
                                if (lastState.peer_lane_count != null) payload.peer_lane_count = lastState.peer_lane_count;
                            }
                            if (lastState.as_reservation != null) payload.as_reservation = lastState.as_reservation;
                            if (lastState.as_optimal_spread_pct != null) payload.as_optimal_spread_pct = lastState.as_optimal_spread_pct;
                            if (lastState.peer_fled_events) payload.peer_fled_events = lastState.peer_fled_events;
                            if (lastState.bot_account_address) payload.bot_account_address = lastState.bot_account_address;
                            if (lastState.bot_address) payload.bot_address = lastState.bot_address;
                            if (lastState.g7_summary) payload.g7_summary = lastState.g7_summary;
                            if (lastState.worst_vs_touch_bps != null) payload.worst_vs_touch_bps = lastState.worst_vs_touch_bps;
                            if (lastState.quote_visibility_summary) payload.quote_visibility_summary = lastState.quote_visibility_summary;
                            if (lastState.cancel_per_fill != null) payload.cancel_per_fill = lastState.cancel_per_fill;
                            if (lastState.open_offers_count != null) payload.open_offers_count = lastState.open_offers_count;
                            const prof = _findIntelProfile(addr, lastState, shadowMode);
                            if (prof) payload.target_profile = prof;
                        }
                        const resp = await fetch('/analyze_competitor', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(payload)
                        });
                        const data = await resp.json();
                        const resultText = data.result || 'No result from analysis.';
                        if (!shadowMode) pinnedIntelAiResult = resultText;
                        if (data.debug) console.log('[HUD analyze]', data.debug);
                        const briefingDetails = document.getElementById(
                            shadowMode ? 'cal-briefing-details' : 'intel-briefing-details'
                        );
                        const briefingJson = document.getElementById(
                            shadowMode ? 'cal-briefing-json' : 'intel-briefing-json'
                        );
                        const sb = data.briefing && data.briefing.structured_briefing;
                        if (briefingDetails && briefingJson && sb) {
                            briefingDetails.style.display = 'block';
                            briefingJson.textContent = JSON.stringify(sb, null, 2);
                        } else if (briefingDetails) {
                            briefingDetails.style.display = 'none';
                        }
                        resultEl.textContent = resultText;
                        resultEl.scrollTop = 0;
                        resultEl.classList.add('new-decision');
                        setTimeout(() => resultEl.classList.remove('new-decision'), 400);
                    } catch (e) {
                        const err = `Error calling /analyze_competitor: ${e}. (HUD must be running with Grok configured.)`;
                        if (!shadowMode) pinnedIntelAiResult = err;
                        resultEl.textContent = err;
                        resultEl.scrollTop = 0;
                    }
                }
            }

            const analyzeBtn = document.getElementById('btn-analyze-addr');
            if (analyzeBtn) {
                analyzeBtn.addEventListener('click', async () => {
                    let addrInput = (document.getElementById('intel-analyze-addr') || {}).value || '';
                    // If empty or placeholder/demo, try to pull first real full r-address.
                    // Prefer data-full attributes on the (now clickable) list items.
                    if (!addrInput || addrInput.includes('Demo') || addrInput.includes('r...') || addrInput.length < 25) {
                        const peerEl = document.getElementById('intel-peer-list-inner');
                        const allEl = document.getElementById('intel-all-makers-inner');
                        const pickFrom = (el) => {
                            if (!el) return null;
                            const row = el.querySelector('div[data-full]');
                            return row ? row.getAttribute('data-full') : null;
                        };
                        addrInput = pickFrom(peerEl) || pickFrom(allEl) || addrInput;
                        if ((!addrInput || addrInput.length < 25) && allEl && allEl.textContent) {
                            const match = allEl.textContent.match(/r[a-zA-Z0-9]{25,}/);
                            if (match) addrInput = match[0];
                        }
                    }
                    await runIntelAnalyze(addrInput || 'rDemoCompetitorAddress', { triggerBtn: analyzeBtn });
                });
            }

            const selfAnalyzeBtn = document.getElementById('btn-analyze-self');
            if (selfAnalyzeBtn) {
                selfAnalyzeBtn.addEventListener('click', async () => {
                    const botAddr = lastState
                        ? String(lastState.bot_account_address || lastState.bot_address || '').trim()
                        : '';
                    await runIntelAnalyze(botAddr, { triggerBtn: selfAnalyzeBtn, selfAudit: true });
                });
            }

            const calAnalyzeBtn = document.getElementById('btn-cal-analyze');
            if (calAnalyzeBtn) {
                calAnalyzeBtn.addEventListener('click', async () => {
                    const addr = (document.getElementById('cal-analyze-addr') || {}).value || '';
                    await runIntelAnalyze(addr, { triggerBtn: calAnalyzeBtn, shadowMode: true });
                });
            }

            const calNickBtn = document.getElementById('btn-cal-save-nickname');
            if (calNickBtn) {
                calNickBtn.addEventListener('click', async () => {
                    const addrEl = document.getElementById('cal-nick-address');
                    const labelEl = document.getElementById('cal-nick-label');
                    const statusEl = document.getElementById('cal-nick-status');
                    const address = addrEl ? addrEl.value.trim() : '';
                    const nickname = labelEl ? labelEl.value.trim() : '';
                    if (!address || address.length < 25) {
                        if (statusEl) statusEl.textContent = 'Enter a valid r-address.';
                        return;
                    }
                    try {
                        const resp = await fetch('/competitor_nicknames', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ address, nickname }),
                        });
                        const data = await resp.json();
                        competitorNicknames = data.nicknames || {};
                        if (statusEl) {
                            statusEl.textContent = nickname
                                ? `Saved "${nickname}" for ${address.slice(0, 12)}???`
                                : `Removed nickname for ${address.slice(0, 12)}???`;
                        }
                        if (lastState) {
                            lastState.competitor_nicknames = competitorNicknames;
                            renderPeerCal(lastState);
                        }
                    } catch (e) {
                        if (statusEl) statusEl.textContent = `Save failed: ${e}`;
                    }
                });
            }

            const nickBtn = document.getElementById('btn-save-nickname');
            if (nickBtn) {
                nickBtn.addEventListener('click', async () => {
                    const addrEl = document.getElementById('nick-address');
                    const labelEl = document.getElementById('nick-label');
                    const statusEl = document.getElementById('nick-status');
                    const address = addrEl ? addrEl.value.trim() : '';
                    const nickname = labelEl ? labelEl.value.trim() : '';
                    if (!address) {
                        if (statusEl) statusEl.textContent = 'Enter an r-address first.';
                        return;
                    }
                    if (statusEl) statusEl.textContent = 'Saving???';
                    try {
                        const resp = await fetch('/competitor_nicknames', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ address, nickname }),
                        });
                        const data = await resp.json();
                        if (!data.ok) {
                            if (statusEl) statusEl.textContent = data.error || 'Save failed.';
                            return;
                        }
                        competitorNicknames = data.nicknames || {};
                        if (statusEl) {
                            statusEl.textContent = nickname
                                ? `Saved "${nickname}" for ${address.slice(0, 12)}???`
                                : `Removed nickname for ${address.slice(0, 12)}???`;
                        }
                        if (lastState) {
                            lastState.competitor_nicknames = competitorNicknames;
                            renderLive(lastState);
                        }
                    } catch (e) {
                        if (statusEl) statusEl.textContent = `Save failed: ${e}`;
                    }
                });
            }
        }

        function initCollapsibles() {
            document.querySelectorAll('.collapsible-header').forEach(header => {
                const targetId = header.getAttribute('data-target');
                const content = document.getElementById(targetId);
                if (!content) return;

                const storageKey = 'hud_collapse_' + targetId;
                const saved = localStorage.getItem(storageKey);
                const isCollapsed = saved === 'true';

                if (isCollapsed) {
                    header.classList.add('collapsed');
                    content.classList.add('collapsed');
                }

                header.addEventListener('click', () => {
                    const collapsed = header.classList.toggle('collapsed');
                    content.classList.toggle('collapsed', collapsed);
                    localStorage.setItem(storageKey, collapsed);
                });
            });
        }

        // Boot: attach nav (data-page driven), show Live, kick off immediate poll + recurring
        function bootHud() {
            ensureCacheBustUrl();
            applyProductionLabels();

            // Nav clicks
            document.querySelectorAll('.nav a').forEach(link => {
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    const page = link.getAttribute('data-page') || link.textContent.toLowerCase().trim();
                    showPage(page);
                });
            });
            document.querySelectorAll('a.nav-jump').forEach(link => {
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    const page = link.getAttribute('data-page');
                    if (page) showPage(page);
                });
            });

            // Attach the remaining demo-only button / select handlers (removes inline onclick/onchange)
            attachDemoHandlers();
            loadTelegramConfig();
            loadCompetitorNicknames();

            // Initialize collapsible sections (Last Decision Note + Recent Decisions)
            initCollapsibles();

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

            // Tick WS age upward between /state polls (uses ws_book_last_update_unix anchor)
            setInterval(() => {
                if (!lastState || lastState.ws_book_last_update_unix == null) return;
                const ageEl = document.getElementById('age');
                if (!ageEl) return;
                const liveAge = computeLiveWsAge(lastState);
                if (liveAge == null) return;
                ageEl.textContent = liveAge.toFixed(1) + 's';
                ageEl.style.color = wsAgeColor(liveAge);
            }, 250);
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', bootHud);
        } else {
            bootHud();
        }
    