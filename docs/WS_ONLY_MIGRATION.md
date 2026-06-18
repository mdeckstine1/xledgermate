# WS-only migration

**Branch:** `ws-only-migration` (safety fork from `Ashigaru-Kaizen-II`)  
**Production today:** `main.py --mode ws-engine` + `main.py --mode ws-hud` on VPS  
**SSOT:** `logs/runtime_state.json` (`price_source=ws_book_feed`, `as_mode=pure`)

---

## How we got here (why legacy code still exists)

1. **Sacred Gate 2 first** — HTTP BookOffers poll + `market_edge_met` hard gate + replay corpus (`decisions.jsonl`, `grokster`, `replay_long_run`) proved economics before live risk.
2. **E2 dual-branch discipline** — `grok-tier-2-collab` kept sacred replay; `Ashigaru-Kaizen` built WS + pure A-S in parallel without deleting the old engine.
3. **E1 live flip (2026-06-15)** — VPS `systemctl` migrated `engine` → `ws-engine` via one-shot scripts; **codebase defaults were never flipped**.
4. **Soak-safe policy** — HUD/reports shipped without engine restarts; shared `main.py`, `trades_*.csv`, `decisions.jsonl` filenames; lab tester kept writing `ws_as_demo_runtime.json`.
5. **Lab = live MM now** — Production soak *is* the lab. Sacred replay stays for **calibration history**, not operator path.

Result: **VPS runs WS-only; repo still presents HTTP-poll as default** in `main.py`, `run.ps1`, analysis CLIs, and docs.

---

## Conflicting logic map

| Concern | Legacy (HTTP poll) | WS production | Conflict |
|---------|-------------------|---------------|----------|
| Entry | `--mode engine` | `--mode ws-engine` | Default still `engine` |
| Book | `fetch_xrp_rlusd_order_book()` loop | `WsBookFeed` | Two loops in repo |
| Quote decision | `quote_decision.py` + profiles | `pure_quote_path.py` | `market_edge_met` vs `would_quote` |
| Hard gate | `order_manager` blocks if no edge | Reservation inside BBO only | Different zero-quote reasons |
| Fills | `LedgerFillScanner` + balance-Δ | Balance-Δ only | CSV same format, different detect |
| Runtime JSON | N/A (poll export) | `runtime_state.json` | Analysis defaults to `ws_as_demo_runtime.json` |
| Operator UI | Streamlit `:8501` | HUD `:8765` | `run.ps1` starts both legacy |
| Profiles | `safe` / `tight_spread` | `ws_pure` (ignored) | `config.active_profile` misleading |

**No conflict on VPS today** — only one engine process. Risk is **accidental start** of legacy path or **wrong script** reading lab artifacts.

---

## Migration phases (this branch)

### Phase 1 — Defaults & labels (this PR) ✓ target

- `main.py` default `--mode ws-engine`; deprecate `engine`/`once` with warnings
- `run.ps1` / `.vscode/tasks.json` → ws-engine + ws-hud
- Analysis CLIs default `runtime_state.json`; `--lab` for tester export
- `ws_compare_snapshot.py` → production vs lab labels
- Committed `scripts/xledgermate.service` template
- README + operator pointers

### Phase 2 — Shared utilities (next)

- `operator_health`, `session_insights`, `analyze_session` → WS fields first
- `decisions.jsonl` — document ws-engine row shape; stop parsing hard-gate strings in ops scripts
- Streamlit: banner “lab analysis — production is HUD :8765”

### Phase 3 — Legacy quarantine (later)

- Move `engine/trading_engine.py` stack to `legacy/` or `experimental/legacy_poll/`
- `--mode engine` → exit with pointer to replay tools
- Remove `market_edge_met` from production runtime export (keep for HUD compat one release)

### Keep forever (calibration, not production)

- `replay_long_run.py`, `grokster.py`, `sacred_economics.py`
- `live_pure_as_tester.py` for local dry-run soak
- `http_poll_feed.py`, `run_probe.py`

---

## Production checklist

```bash
# VPS (canonical)
systemctl start xledgermate          # ws-engine
systemctl start xledgermate-ws-hud   # :8765

# Local dev
python main.py --mode ws-engine
python main.py --mode ws-hud

# Analysis (production artifact)
python -m experimental.ws_runtime_analysis --path logs/runtime_state.json
python scripts/soak_dashboard_report.py
```

---

## See also

- [`PURE_AS_CRITICAL_PATH.md`](PURE_AS_CRITICAL_PATH.md) — live soak TODO
- [`E2_BRANCH_DISCIPLINE.md`](E2_BRANCH_DISCIPLINE.md) — why dual path existed
