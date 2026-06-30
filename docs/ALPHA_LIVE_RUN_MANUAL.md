# Alpha — Aggressive Bag Growth (TA-Driven & HUD-Controlled)

**Strategy:** Grow the XRP bag. TA tells the bot what the market is doing; HUD knobs let you decide how strictly to act on it. Deploy RLUSD on dips with TA confirmation. Take profit on strength, then wait for cooldown + dip before reloading.

**HUD:** `http://YOUR_VPS:8765` — **primary tuning surface** (no terminal edits needed after initial setup)  
**There is no manual Buy button** — the engine places limit orders when all gates pass.

> **New operator?** Read **[`ALPHA_TRADERS_MANUAL.md`](ALPHA_TRADERS_MANUAL.md)** — **Part 1** walks each HUD tab and card; **Appendices** are preset recipes when Decision reason matches.

---

## Core idea (vs old Balanced Aggressive)

| Old (~55% XRP target) | New (Aggressive Bag Growth) |
|------------------------|-----------------------------|
| Large RLUSD sidelined | **75% XRP target** — minimize idle RLUSD |
| Buys on mild weakness | Buys on **2% below target** + edge + depth + **TA** |
| Re-buy anytime | After **TP**: **cooldown** → dip → TA min score |
| — | After **SL**: **longer cooldown** → stabilization → stronger TA |

---

## Order lifecycle

1. **PLACE_BID** — RLUSD deploys on dip (inventory + edge + depth + TA buy gate)
2. **Pending buy** → fill → **TP + SL** bracket sells placed automatically
3. **TP fills** (profit) → re-entry gate ON → **post_tp_cooldown** blocks all buys first
4. After cooldown: dip + weakness + `tp_min_ta_score` required
5. **SL fills** (stop) → **post_sl_cooldown** → stabilization + `sl_min_ta_score`
6. **PLACE_ASK** — strength unload when XRP-heavy; TA sell gate + weight apply

---

## Gates for PLACE_BID (all required)

| Gate | What to check |
|------|----------------|
| **Re-entry cooldown** | `post_tp_cooldown` / `post_sl_cooldown` — **cannot be bypassed** |
| Inventory | `deviation <= -alpha_weakness_deviation` (default **−0.02**) |
| Edge | Limit buy edge ≥ `alpha_min_edge_threshold_pct` |
| Depth | `insufficient_ask_depth` not in reason |
| **TA** | `ta_weight` × `min_buy_score`; blocks bearish bias when weight > 0 |
| Re-entry (post-cooldown) | Dip (TP) or stabilization (SL) + min TA scores |
| Risk | Preflight OK, no kill, not paused, `trading_enabled` |

---

## Default aggressive config (`config.example.yaml`)

```yaml
inventory_target_xrp_ratio: 0.75
alpha_weakness_deviation: 0.02
alpha_technical_analysis:
  enabled: true
  min_buy_score: 1.5
alpha_reentry_enabled: true
alpha_reentry_tp_cooldown_cycles: 4
alpha_reentry_tp_cooldown_minutes: 0
alpha_reentry_tp_dip_pct: 0.08
alpha_reentry_tp_min_ta_score: 1.5
alpha_reentry_sl_cooldown_cycles: 10
alpha_reentry_sl_cooldown_minutes: 0
alpha_reentry_sl_stabilization_pct: 0.12
alpha_reentry_sl_min_ta_score: 2.5
alpha_ta_weight: 1.0
dry_run: true
```

---

## HUD knobs (runtime overrides — no restart)

All panels use **Apply** → `PATCH /operator/config` → effective next engine cycle.

### Risk & entry (Live tab)

| Knob | Default | Purpose |
|------|---------|---------|
| `target_xrp_pct` | 75 | Inventory target — slider 0–100% |
| `weakness_deviation` | 0.02 | RLUSD deploy trigger |
| `risk_per_trade_pct` | 0.5 | Capital per bracket |
| `min_edge_threshold_pct` | 0.08 | Min spread edge for bids |
| `buy_limit_offset_pct` | 0.15 | Bid depth below mid |
| `sell_limit_offset_pct` | 0.15 | Ask offset for strength sells |
| `cycle_interval_seconds` | 15 | Seconds between engine cycles (5–60, HUD-tunable) |

### Market Conditions card (Live tab, next to chart)

| Field | Meaning |
|-------|---------|
| Overall grade | Green/yellow/red from spread + 1% depth |
| Ask/Bid depth (1%) | XRP walkable within 1% of touch |
| Max buy/sell size | Depth + risk% + leg cap recommendation |
| TA summary | buy_score, sell_score, bias |
| Cycle interval | Effective `alpha_cycle_interval_seconds` |

### TA tab

| Knob | Default | Purpose |
|------|---------|---------|
| TA enable | on | Master TA switch |
| `ta_weight` | 1.0 | Scales buy/sell score gates (0=advisory) |
| `min_buy_score` | 1.5 | Composite buy threshold |
| `min_sell_score` | 1.0 | Strength sell threshold |
| RSI / Stoch / Bollinger / Engulfing | on | Indicator contributions |

### Re-entry (Live tab)

| Knob | Default | Purpose |
|------|---------|---------|
| `reentry_enabled` | on | Patient reload after exits |
| `tp_cooldown_cycles` | **4** | Hard block after TP (spread protection) |
| `tp_cooldown_minutes` | 0 | Optional time gate (0=cycles only) |
| `tp_dip_pct` | 0.08 | Mid dip below TP exit (after cooldown) |
| `tp_min_ta_score` | 1.5 | TA bar after cooldown |
| `sl_cooldown_cycles` | **10** | Hard block after SL |
| `sl_cooldown_minutes` | 0 | Optional time gate |
| `sl_stabilization_pct` | 0.12 | Bounce above recent low |
| `sl_min_ta_score` | 2.5 | Stronger TA after SL |

---

## HUD — Live tab

| Element | Meaning |
|---------|---------|
| **Decision** | `PLACE_BID`, `PLACE_ASK`, or `HOLD` + reason (`post_tp_cooldown`, etc.) |
| **Re-entry line** | **COOLDOWN** with cycles/minutes remaining, or gate active post-cooldown |
| **TA line** | Buy/sell scores; gate uses `alpha_ta_weight` × thresholds |

---

## Re-entry rules (automatic)

### Cooldown (first — non-negotiable)

After any bracket exit, the bot blocks **all** new buys until:

1. `cycles_since_exit >= tp/sl_cooldown_cycles` (defaults **4** TP / **10** SL), **and**
2. If `*_cooldown_minutes > 0`, elapsed time since exit must exceed that value.

HUD Decision shows `post_tp_cooldown cycles=1/4` or `post_sl_cooldown minutes=2.0/15.0`.

---

## HUD — PRO tab

After an SL-heavy session, open **PRO** (nav: Activity · **PRO** · SKYNET · Config):

| Block | Use |
|-------|-----|
| **Alpha Replay** | Realized TP/SL ratio and P&amp;L — ignore session MTM for bleed diagnosis |
| **Defensive circuit** | Auto-applies bear posture when replay verdict is bad; **Release defensive** restores saved overrides |
| **Treasury** | Placeholder — manual RLUSD funding via Config until Phase 2 |

See **[Appendix W](ALPHA_TRADERS_MANUAL.md#appendix-w--sl-heavy-night-defensive-circuit-pro)** in the traders manual.

---

### After take-profit (post-cooldown)

- Mid dips below TP exit by `alpha_reentry_tp_dip_pct`
- Inventory weakness (RLUSD to deploy)
- `buy_score >= alpha_reentry_tp_min_ta_score`

### After stop-loss (post-cooldown)

- Structure not bearish / no breakout_down
- Bounce above `recent_low` by `alpha_reentry_sl_stabilization_pct`
- `buy_score >= alpha_reentry_sl_min_ta_score` + non-bearish bias
- Inventory weakness

**Goal:** Maximize spread between sell and next buy.

---

## PLACE_ASK (strength sells)

When XRP-heavy, TA gates strength sells:

- `sell_score >= min_sell_score × ta_weight`
- Deferred when **bullish** bias and buy score also passes (`ta_sell_deferred`)

---

## Going live checklist

1. `python scripts/alpha_validate.py`
2. Soak mainnet `dry_run: true` (24–48h)
3. Set **target_xrp_pct** and re-entry cooldowns on HUD
4. `ENABLE_LIVE` when ready
5. Watch Decision for `post_*_cooldown` after bracket exits

---

## Why HOLD? (quick reference)

| Reason | Meaning |
|--------|---------|
| `post_tp_cooldown` | Spread protection — wait N cycles/min after TP |
| `post_sl_cooldown` | Patience after stop-loss |
| `reentry_tp_await_dip` | Cooldown done — waiting for price dip |
| `reentry_sl_await_stabilization` | Cooldown done — trend not stable |
| `ta_buy_blocked` | TA below weighted threshold or bearish bias |
| `ta_sell_deferred` | Bullish TA — defer strength sell |
| `balanced dev=+0.02` | Not weak enough to buy |

---

## Related docs

- [`ALPHA_OPERATOR_GUIDE.md`](ALPHA_OPERATOR_GUIDE.md) — config reference
- [`ALPHA_FINAL_REPORT.md`](ALPHA_FINAL_REPORT.md) — architecture status
