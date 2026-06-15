# Phase E — VPS swap runbook

**Branch:** `Ashigaru` · **Engine:** `python main.py --mode ws-engine`  
**HUD:** `xledgermate-ws-hud` → `:8765` (production; retire Streamlit `:8502` for MM ops)  
**Sacred corpus:** `grok-tier-2-collab` (Gate 2 labeled data + replay; **E2 merged** 2026-06-15)

This runbook is the operator ladder for **E1–E3** in [`PURE_AS_CRITICAL_PATH.md`](PURE_AS_CRITICAL_PATH.md).

---

## E1 — Wholesale VPS replace (WS + pure A-S)

### Current state (2026-06-15)

| Item | Status |
|------|--------|
| Code | `WsPureTradingEngine` v2.1.0 (G1 peer lane + G2 scaler) |
| VPS systemd | `xledgermate` → `--mode ws-engine`; `xledgermate-ws-hud` → `:8765` |
| Kill switch | Clear (catastrophe-only; G2 dimmer for adverse selection) |
| Mode | **`dry_run: false`** — live MM on bot ledger (~234 XRP-equiv pilot) |
| E1.5 | PASS — `scripts/ws_path_session_report.py --gate-full` (CSV fills authoritative) |
| E2 | **Done** — Ashigaru merged into `grok-tier-2-collab`; VPS stays Ashigaru |
| Legacy GUI | `:8502` Streamlit — not production MM path |

### E1 ladder

| Step | Action | Done when |
|------|--------|-----------|
| **E1.1** | VPS on Ashigaru, ws-engine running | `systemctl is-active xledgermate` |
| **E1.2** | Dry-run smoke ≥30 cycles | `runtime_state.cycle_count` ≥ 30 |
| **E1.3** | WS book fresh + pure path | `as_mode=pure`, `price_source=ws_book_feed`, `ws_book_age_s` &lt; 15 |
| **E1.4** | Sign-off script PASS | `python scripts/vps_ws_engine_signoff.py --gate` |
| **E1.5** | Flip live | `dry_run: false` + `systemctl restart xledgermate` |
| **E1.6** | Monitor ≥50 fills | `fills_session` + trades CSV; markout TBD |
| **E1.7** | E1 complete | Operator sign-off + checkbox in critical path |

### Commands (VPS)

```bash
cd /root/xledgermate
bash scripts/vps_deploy_ashigaru.sh
# Or manually:
git fetch && git checkout Ashigaru && git pull
systemctl restart xledgermate xledgermate-ws-hud
```

After deploy, HUD shows `ws_as_version` from `experimental/ws_feed/WS_AS_VERSION` (re-read on each `/state` poll). Engine logs `WsPureTradingEngine v…` on restart.

```bash
python scripts/vps_ws_engine_signoff.py
python scripts/vps_ws_engine_signoff.py --gate   # exit 1 if not ready

# Go live (operator only)
cp -a config/config.yaml config/config.yaml.bak-pre-live
perl -pi -e 's/^dry_run: true/dry_run: false/' config/config.yaml
systemctl restart xledgermate
journalctl -u xledgermate -f
```

### Commands (local → tunnel GUI)

```powershell
ssh -i $env:USERPROFILE\.ssh\hetzner_xledgermate -L 8502:127.0.0.1:8502 root@188.245.50.229
# http://localhost:8502
```

### E1 abort / rollback

```bash
perl -pi -e 's/^dry_run: false/dry_run: true/' config/config.yaml
python main.py --mode cancel-offers
systemctl restart xledgermate
# Or revert systemd to legacy poll (not recommended):
# perl -pi -e 's/--mode ws-engine/--mode engine/' /etc/systemd/system/xledgermate.service
```

### E1 sign-off criteria (automation)

`scripts/vps_ws_engine_signoff.py` checks:

- `as_mode: pure`, `price_source: ws_book_feed`
- Kill switch clear
- `dry_run: true` (pre-live mode)
- `cycle_count` ≥ 30
- `ws_book_age_s` ≤ 15
- ≥35% `would_quote` on recent pure `decisions.jsonl` lines
- Wiring parity ≥10/15 export keys

Post-live: run with `--live` (expects `dry_run: false`).

---

## E2 — Merge `Ashigaru` → `grok-tier-2-collab` ✓ (2026-06-15)

**Purpose:** Unify **live WS + pure A-S code** with the **sacred Gate 2 corpus** branch. E2 is a **git merge + docs** step — **no VPS runtime change**.

| Step | Action | Status |
|------|--------|--------|
| **E2.1** | Merge Ashigaru (ws-engine, G1, G2, HUD) into `grok-tier-2-collab` | ✓ |
| **E2.2** | Fast-forward Ashigaru from collab; resolve doc conflicts | ✓ |
| **E2.3** | P0 `market_edge_met` stays on **legacy** `trading_engine` for replay baseline only | ✓ |
| **E2.4** | `FOR_AI`, `THREAD`, `E2_BRANCH_DISCIPLINE.md`, critical path updated | ✓ |

**Discipline after E2:**

- **VPS live MM:** always deploy **`Ashigaru`** — `ws-engine` + HUD `:8765`
- **Sacred replay / economics:** run on either branch (same WS code); corpus labels stay on collab
- **Do not** switch VPS to legacy `--mode engine` poll path for production quoting

See [`E2_BRANCH_DISCIPLINE.md`](E2_BRANCH_DISCIPLINE.md).

---

## E3 — 11k-only funding / predator P&L (hypothesis)

**Not live until E1.6 fills validate.** Advisory + sizing only — never overrides reservation.

| Hypothesis | Config / lab knob |
|------------|-------------------|
| XRP-heavy start (~11k XRP) | `fund_with_xrp_only: true` (legacy); pure path uses inventory skew in `PureQuotePath` |
| Ask-heavy rebalance | Low ask-pressure + high XRP skew → ask size boost (`dynamic_sizing.py`) |
| Predator P&L claims | Blocked until A1 sacred A/B + ≥50 WS live fills |

**Lab simulate 11k:**

```powershell
python -m experimental.ws_feed.live_pure_as_tester --serve-hud --seconds 300 --verbose
# HUD: set xrp_bal / rlusd_bal or use competitor intel tab
```

**VPS:** Current wallet ~241 XRP equiv — E3 is a **scale hypothesis**, not today's deploy blocker.

---

## Phase E vs Phase G (naming)

| Checklist | Meaning |
|-----------|---------|
| **Phase E** (this doc) | VPS wholesale swap E1–E4 |
| **Phase G** (critical path) | Peer-lane intel G1–G6 — G4+ blocked until E1.7 |

---

## Related

- [`PURE_AS_CRITICAL_PATH.md`](PURE_AS_CRITICAL_PATH.md)
- [`WS_AS_MANUAL.md`](WS_AS_MANUAL.md)
- `scripts/vps_ws_engine_signoff.py`
- `scripts/vps_deploy_ws_engine.sh`
