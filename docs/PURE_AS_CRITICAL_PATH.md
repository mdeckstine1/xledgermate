# Pure A-S Critical Path

**Status:** Live soak on VPS — **WS + pure A-S** (`ws-engine`) · **HUD** `:8765`  
**Version:** v2.1.15 · **Branch:** `Ashigaru-Kaizen-II`  
**Last updated:** 2026-06-18

Single checklist for WS + pure A-S. Other docs link here — do not duplicate task lists.

**Soak = timed test run.** Collect fills, toxicity, markout, G6 grades under real quoting. **Soak-safe HUD work is done** — let `ws-engine` run until segment end, then one **engine-window** restart (M2–M5).

---

## Active TODO

### Now (operator — engine restart when ready)

| # | Task | Status |
|---|------|--------|
| — | **Deploy M2–M5 bundle** — `git pull` on VPS → `systemctl restart xledgermate` (brief quoting gap) | **ready** |
| — | Post-deploy: `fill_quote_age_report.py`, `ws_runtime_analysis`, `live_activation_grading --gate` | pending restart |
| — | Watch G6 tier, toxic@30s, markout@30s after restart | ongoing |
| — | **Skim Δ** directional until new fills get implied-price `profit_xrp_equiv` | ongoing |

### Segment end — one `ws-engine` restart (deploy together)

| # | Item | Notes |
|---|------|--------|
| 1 | **M2** Fill age live | **shipped** — `OfferAgeTracker` in `_sync_offers` + `_detect_fills`; HUD `effective_quote_age_at_fill_seconds` |
| 2 | **M3** Stale-cross flag | **shipped** — `reservation_crossed_after_ws_sample` pre/post intel BBO in `_run_cycle` |
| 3 | **M4** Production `sample_history` | **shipped** — `append_runtime_sample` in `_persist_cycle`; C1 soak metrics on runtime export |
| 4 | **M5** `as_safety` on production path | **confirmed** — `enforce_reservation_gate` in `pure_quote_path.py` (no engine change) |
| 5 | **Fill economics** | `fill_detection.py` implied price — **deploy with engine restart** |
| 6 | Post-deploy gates | `fill_quote_age_report.py`, `ws_runtime_analysis`, `live_activation_grading --gate` |

**Order:** deploy M2–M5 bundle → engine restart → post-deploy reports + G6 `--gate`.

### After segment (engine or separate windows)

| # | Item | Blocker |
|---|------|---------|
| P1–P3 | Per-peer history, tx correlation, full L1–L3 in runtime | Engine + soak data |
| P4–P6 | Structured `PeerBriefing`, G4 nudges, F2 engine hook | P1 + markout |
| P7 | Async submit / tx rate instrumentation (L1–L4) | M2/M3 review |
| I1–I4 | Regime channel (book-wide pressure, damped) | Empty peer lane validated |
| I7 | In-band peer automation path | Real touch-band peers |
| E3 | 11k funding + rebalance execution | Operator / dev complete |
| H3–H7 | Arb paper/live, USDC, path scanner | G6 pass + H1 monitor data |
| F4 | Grok suggestion → outcome correlation | Fill attribution |
| M6 | Per-sequence quote age | After M2 soak review |

---

## Soak-safe — complete (2026-06-17)

HUD-only deploys (`xledgermate-ws-hud` restart OK). No further soak-safe code required.

| Area | Shipped |
|------|---------|
| **M1** | Res→BBO delta, inside L1, hourly Telegram |
| **M2/M3 prep** | `fill_quote_age_report.py`, `offer_age_tracker.py`, `stale_cross.py`, analysis schema |
| **Intel HUD** | I5 side skew, I6 regime vs peer, F1 nicknames, F3a/F3b Grok briefing, F4 JSONL, F2 advisory stub |
| **Reports** | 9 soak-safe reports tab (`grok_suggestions`, `clob_amm_monitor`, …) |
| **H1/H2** | Read-only CLOB vs AMM monitor + `amm_provider.py` |
| **HUD ops** | Inventory nav restored; Metrics toxicity gray-zone fix; **Skim Δ** (not wallet/deposit); Wallet Δ on Inventory |

### Deploy discipline

| Change | Restart | During soak? |
|--------|---------|--------------|
| HUD / `ws_hud_production.py` / reports / `performance_metrics.py` | `xledgermate-ws-hud` | Yes |
| `fill_detection.py` / `fill_economics.py` (HUD CSV skim) | ws-hud only until engine pull | Yes |
| `ws_pure_engine.py` (M2–M5, fill age, `session_spread_capture_xrp`) | `xledgermate` | **No** — segment end |
| `vps_deploy_ashigaru.sh` full | ws-engine + HUD | **No** unless planned |

**Sacred rule:** `would_quote` = reservation inside live BBO. Measurement and HUD never override A-S math.

---

## Skim Δ / PnL display (operator)

| HUD field | Meaning |
|-----------|---------|
| **Skim Δ** | Session spread capture estimate from WS fills (volume × half spread when `profit_xrp_equiv` is 0) |
| **Wallet Δ** (Inventory) | Portfolio change since session start — **includes deposits** |
| **Metrics → Total capture** | CSV sum (all-time in month file); grades use toxic@30s |

Balance-delta fills often store fill@mid → `profit_xrp_equiv ≈ 0` until M2/engine implied-price fix lands. Treat Skim Δ as **directional** during soak; reconcile after segment end.

---

## Completed phases (reference)

<details>
<summary>Phase 0–G — foundation through live activation (click to expand)</summary>

- **0:** WS probe, pure A-S, sacred economics, live tester + HUD, Grok analyze
- **A:** Sacred A/B, `ws_runtime_analysis`, `as_calibration_grok`
- **B:** `PureQuotePath`, dynamic sizing, book-age modulator, zero-quote notes
- **C:** C1 pressure/presence metrics, C2 soak gate
- **D:** WS feed hardening, dry-run offers, Streamlit compare, swap readiness
- **E:** E1 live VPS ws-engine, E1.5 gate PASS, E2 merge, E4 `WsPureTradingEngine`
- **G:** G1–G6 peer lane, G2 scaler, intel JSONL, G4 quoting, G5 replay, G6 activation grading

</details>

---

## Direction

| Legacy | Committed |
|--------|-----------|
| HTTP BookOffers poll | WS `BookFeed` |
| Hard `market_edge_met` vetoes | Pure A-S reservation inside book |
| Grok as override | Advisory inputs only (vol, spread anchor, size) |

---

## Doc map

| File | Use |
|------|-----|
| **This file** | Critical path + TODO |
| [`PURE_AS_DEVELOPMENT_LOG.md`](PURE_AS_DEVELOPMENT_LOG.md) | **Posterity** — how we got here, soak learnings, decisions |
| [`WS_AS_MANUAL.md`](WS_AS_MANUAL.md) | Tester + HUD + Grok |
| [`PHASE_E_VPS_RUNBOOK.md`](PHASE_E_VPS_RUNBOOK.md) | VPS swap ladder |
| [`E2_BRANCH_DISCIPLINE.md`](E2_BRANCH_DISCIPLINE.md) | Branch roles |
| [`../experimental/ws_feed/WS_HANDOFF.md`](../experimental/ws_feed/WS_HANDOFF.md) | Architecture |
| [`../groks input/docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md`](../groks%20input/docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md) | Gate metrics |
| [`../experimental/PHASE_E_INTELLIGENCE_IMPLEMENTATION_PLAN.md`](../experimental/PHASE_E_INTELLIGENCE_IMPLEMENTATION_PLAN.md) | Phase G detail |

**Lab:**

```powershell
cd C:\Users\micha\xledgermate
.\.venv\Scripts\Activate.ps1
python -m experimental.ws_feed.live_pure_as_tester --serve-hud --seconds 0 --verbose
```

Open http://127.0.0.1:8765

---

## Key files

```
experimental/ws_feed/ws_pure_engine.py       # VPS production loop
experimental/ws_feed/ws_hud_production.py    # HUD mirror (:8765)
experimental/ws_feed/hud/index.html          # Operator UI
monitoring/fill_detection.py               # Balance-delta fill infer
monitoring/fill_economics.py               # Spread capture + skim estimate
scripts/ws_path_session_report.py          # E1.5 + session skim CSV
experimental/ws_feed/performance_metrics.py  # G3 Metrics grades
experimental/ws_feed/live_activation_grading.py  # G6 tier
experimental/ws_feed/reservation_metrics.py  # M1
experimental/ws_feed/as_safety.py          # M5 (deploy at segment end)
experimental/arb/clob_amm_monitor.py       # H1 read-only
scripts/vps_deploy_ashigaru.sh             # VPS deploy (plan segment end)
```

---

## Promotion ladder

1. Sacred replay economics — done  
2. HUD + long runs — done  
3. Dry-run WS offers — done  
4. E1 live ws-engine — done (2026-06-15)  
5. **Current:** soak → G6 gate → engine window (M2–M5) → E3 / post-soak intel

---

## Maintenance

When a checkbox ships: update this file + [`PURE_AS_DEVELOPMENT_LOG.md`](PURE_AS_DEVELOPMENT_LOG.md) (narrative) + FOR_AI milestone + THREAD. Do not commit `.env` / secrets.
