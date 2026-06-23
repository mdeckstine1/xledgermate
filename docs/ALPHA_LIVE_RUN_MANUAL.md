# Alpha — Aggressive Bag Growth (TA-Driven & HUD-Controlled)

**Strategy:** Grow the XRP bag. TA tells the bot what the market is doing; HUD knobs let you decide how strictly to act on it. Deploy RLUSD on dips with TA confirmation. Take profit on strength, then wait for the next dip before reloading.

**HUD:** `http://YOUR_VPS:8765` — **primary tuning surface** (no terminal edits needed after initial setup)  
**There is no manual Buy button** — the engine places limit orders when all gates pass.
---

## Core idea (vs old Balanced Aggressive)

| Old (~55% XRP target) | New (Aggressive Bag Growth) |
|------------------------|-----------------------------|
| Large RLUSD sidelined | **75% XRP target** — minimize idle RLUSD |
| Buys on mild weakness | Buys on **2% below target** + edge + depth + **TA** |
| Re-buy anytime | After **TP**: wait for **price dip** + TA before next buy |
| — | After **SL**: wait for **stabilization** + TA (no falling knife) |

---

## Order lifecycle

1. **PLACE_BID** — RLUSD deploys on dip (inventory below 75% XRP + edge + depth + TA buy gate)
2. **Pending buy** → fill → **TP + SL** bracket sells placed automatically
3. **TP fills** (profit) → re-entry gate ON → bot waits for new dip + TA
4. **SL fills** (stop) → re-entry gate ON → bot waits for stabilization + bullish TA
5. **PLACE_ASK** — optional strength unload when XRP-heavy (no bracket on strength sells)

---

## Gates for PLACE_BID (all required)

| Gate | What to check |
|------|----------------|
| Inventory | `deviation <= -alpha_weakness_deviation` (default **−0.02** vs **75%** target) |
| Edge | Limit buy edge ≥ `alpha_min_edge_threshold_pct` |
| Depth | `insufficient_ask_depth` not in reason |
| **TA** (default **on**) | TA tab: enable, **weight**, min buy score, indicator toggles |
| Re-entry | Live tab **Re-entry** panel: TP/SL cooldowns, dip %, min TA scores |
| Risk | Preflight OK, no kill, not paused, `trading_enabled` |

---

## Default aggressive config (`config.example.yaml`)

```yaml
inventory_target_xrp_ratio: 0.75
alpha_weakness_deviation: 0.02
alpha_strength_deviation: 0.04
alpha_technical_analysis:
  enabled: true
  min_buy_score: 1.5
alpha_reentry_enabled: true
alpha_reentry_tp_dip_pct: 0.08      # re-buy after TP only when mid dips 0.08% below TP exit
alpha_reentry_sl_min_cycles: 3      # patience after stop loss
alpha_reentry_sl_stabilization_pct: 0.12
alpha_reentry_tp_min_ta_score: 1.5
alpha_reentry_sl_min_ta_score: 2.5
alpha_ta_weight: 1.0               # 0=TA advisory only; 1=full gate at min_buy_score
dry_run: true
```

---

## HUD knobs (runtime overrides — no restart)

All panels use **Apply** → `PATCH /operator/config` → effective next engine cycle.

### Risk & entry (Live tab)

| Knob | Default | Purpose |
|------|---------|---------|
| `target_xrp_pct` | 75 | Inventory target — slider 0–100% |
| `weakness_deviation` | 0.02 | How far below target before RLUSD deploy |
| `risk_per_trade_pct` | 0.5 | Capital per bracket |
| `min_edge_threshold_pct` | 0.08 | Min spread edge for bids |
| `buy_limit_offset_pct` | 0.15 | Bid depth below mid |
| `sell_limit_offset_pct` | 0.15 | Ask offset for strength sells |

### TA tab

| Knob | Default | Purpose |
|------|---------|---------|
| TA enable | on | Master TA switch |
| `ta_weight` | 1.0 | 0=display only; 1=full buy gate |
| `min_buy_score` | 1.5 | Composite buy threshold |
| RSI / Stoch / Bollinger / Engulfing | on | Indicator contributions |

### Re-entry (Live tab)

| Knob | Default | Purpose |
|------|---------|---------|
| `reentry_enabled` | on | Patient reload after exits |
| `tp_cooldown_cycles` | 1 | Wait after take-profit |
| `tp_dip_pct` | 0.08 | Mid must dip below TP exit |
| `tp_min_ta_score` | 1.5 | TA bar for post-TP re-buy |
| `sl_cooldown_cycles` | 3 | Longer wait after stop-loss |
| `sl_stabilization_pct` | 0.12 | Bounce above recent low |
| `sl_min_ta_score` | 2.5 | Stronger TA for post-SL re-buy |

---

## HUD — Live tab

| Element | Meaning |
|---------|---------|
| **Decision** | `PLACE_BID`, `PLACE_ASK`, or `HOLD` + full reason |
| **TA line** | Buy/sell scores; effective gate uses `alpha_ta_weight` × `min_buy_score` |
| **Re-entry line** | Active after TP/SL exit — exit type and cycles waited |
| **Risk & entry / Re-entry panels** | Live sliders — Apply without terminal |
| **TA tab** | Enable, weight, thresholds, indicator toggles |

---

## Re-entry rules (automatic)

### After take-profit (TP)

- Minimum **1 cycle** cooldown (configurable)
- Mid must dip **below** TP exit price by `alpha_reentry_tp_dip_pct`
- Inventory must have RLUSD to deploy (weakness vs 75% target)
- **TA buy gate must pass** — `buy_score >= alpha_reentry_tp_min_ta_score` (HUD-tunable)

### After stop-loss (SL)

- Minimum **3 cycles** cooldown (configurable)
- Structure must not be bearish / breakout_down
- Price must bounce slightly above `recent_low`
- **TA buy score** ≥ `alpha_reentry_sl_min_ta_score` + non-bearish bias
- Inventory weakness still required

**Goal:** Maximize spread between sell and next buy — no chasing momentum after TP, no catching knives after SL.

---

## Going live checklist

1. `python scripts/alpha_validate.py`
2. Soak mainnet `dry_run: true` (24–48h)
3. Confirm TA tab shows scores updating
4. `ENABLE_LIVE` on HUD when ready
5. Watch first cycles: Decision + Re-entry + TA lines

---

## Why HOLD? (quick reference)

| Reason | Meaning |
|--------|---------|
| `balanced dev=+0.02` | Near 75% target — not weak enough to buy |
| `ta_buy_blocked` | TA scores below threshold — wait or tune TA tab |
| `ta_warming_up` | Not enough price history yet |
| `reentry_tp_await_dip` | Took profit recently — waiting for dip |
| `reentry_sl_await_stabilization` | Stopped out — waiting for trend to stabilize |
| `reentry_sl_cooldown` | Minimum wait after SL not elapsed |

---

## Related docs

- [`ALPHA_OPERATOR_GUIDE.md`](ALPHA_OPERATOR_GUIDE.md) — config reference
- [`ALPHA_FINAL_REPORT.md`](ALPHA_FINAL_REPORT.md) — architecture status
