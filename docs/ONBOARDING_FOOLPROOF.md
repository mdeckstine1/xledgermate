# Foolproof onboarding — Open Desk (v1)

**Audience:** brand-new subscribers who should never need a terminal, YAML, or “what is a trustline” lecture.  
**Funding philosophy:** **Fund with RLUSD.** The bot’s job is bag growth / XRP–RLUSD work — users should not micro-manage inventory.  
**Stack we push (happy path):**

| Role | Tool | Why |
|------|------|-----|
| **Cold / self-custody** | [Xaman](https://xaman.app/) | Best-in-class XRPL wallet UX; RLUSD trustline is one flow |
| **Exchange + fiat on-ramp** | [Kraken](https://www.kraken.com/) | Deposit cash → buy **RLUSD** → withdraw XRPL |
| **Trading bot wallet** | Fresh XRPL account used **only** by the desk | Risk capital isolation (never the cold wallet seed) |

**Affiliate / referral intent:** deep-link users through **your** Kraken referral/affiliate link and preferred Xaman entry where allowed. Config lives in platform settings (not hard-coded secrets in the client).

---

## Funding model (locked)

| What user sends to the **bot** | Why |
|--------------------------------|-----|
| **RLUSD (primary)** | Risk capital. Desk trades / rebalances from here. “Let the bot do its job.” |
| **XRP (gas only)** | XRPL base reserve + trustline + fees. Small one-time top-up — **not** the investment thesis. |

**Do not teach:** “Buy a pile of XRP and RLUSD and balance them yourself.”  
**Do teach:** “Load **RLUSD** as your stake. Keep a little **XRP** so the account can live on-ledger. The desk handles the rest.”

```text
  CASH (fiat)          RLUSD STAKE              BOT DOES THE WORK
  ───────────          ───────────              ─────────────────
  Bank → Kraken   →    withdraw RLUSD      →    bot wallet (hot)
                       (+ small XRP gas)        strategy / bag growth
                              │                        │
                              │                        ▼
                         Xaman cold ◄──────── optional profit / sleep money
```

**Rules of thumb (repeat on every screen):**

1. **Fund the desk with RLUSD** — that’s your risk capital.  
2. **XRP is gas** — enough reserve/fees only (we show the number).  
3. **Cold stays cold** — Xaman is the vault; never paste that seed into Open Desk.  
4. **Bot is disposable capital** — only what you’re willing to put at risk.  
5. **Kraken is the on-ramp** — cash → RLUSD → bot address on **XRP Ledger**.  
6. **RLUSD needs a trustline** on the bot (and on cold if you store RLUSD there).  
7. **Green checks only** — no live until checklist is complete.

---

## End-to-end happy path (timeboxed)

Target: **under 30 minutes** (KYC may add time).

| Step | Where | User does | We show | Done when |
|------|--------|-----------|---------|-----------|
| **0** | Open Desk | Sign up (email + password) | Plan picker (Trial / Pro) | Account created |
| **1** | Kraken | Sign up via **your referral link** + KYC | “Get cash in the door” | Deposit ready |
| **2** | Kraken | Buy **RLUSD** (main). Optional tiny XRP only if we need gas offline | “RLUSD is your stake” | RLUSD balance > 0 |
| **3** | Xaman | Install, create **cold** wallet, backup phrase offline | “This is NOT the bot” | Phrase secured (self-attested) |
| **4** | Xaman | Add **RLUSD** on cold (optional but recommended for withdrawals later) | Xaman RLUSD help | Cold can receive RLUSD |
| **5** | Open Desk | **Create bot wallet** (we generate) | Address + QR | Bot address known |
| **6** | Bot | Enable **RLUSD trustline** on **bot** | One-slide accept | Trustline live |
| **7a** | Kraken → bot | Withdraw **small XRP** for gas/reserve (once) | Exact min amount we calculate | Reserve OK |
| **7b** | Kraken → bot | Withdraw **RLUSD** (stake) to **bot** on XRPL | Big primary CTA | RLUSD deposit detected |
| **8** | Open Desk | Optional: Telegram + Grok | Skip allowed on Trial | Preferences saved |
| **9** | Open Desk | Dry-run → Go live | “Desk is working your RLUSD” | Desk running |

**Optional later:** take profit bot → Xaman cold as **RLUSD** (and/or XRP if the bot earned it — user doesn’t need to plan that).

---

## Screen-by-screen UX (foolproof)

### Global UI patterns

- **Progress bar:** `Setup 3 of 9` always visible.  
- **One primary button** per screen. Secondary = “I’m stuck / help”.  
- **Trustline** tooltip: “permission for this account to hold RLUSD.”  
- **Copy buttons** on every address; **XRPL only** in red if they pick the wrong network.  
- Self-attest: “I wrote down my Xaman phrase” — we never see the phrase.  
- **Recommended path locked.** Advanced collapsed.

### Step 1–2 — Kraken (on-ramp = RLUSD)

**Copy angle:** “Turn cash into **RLUSD**. That’s what funds the desk. The bot handles XRP.”

Buttons:

1. **Open Kraken with our link** → your referral/affiliate URL  
2. Checklist: Verify → Deposit cash → **Buy RLUSD**  
3. (Helper only if needed) “Also buy ~N XRP for network gas — not for trading”  
4. **I’ve got RLUSD on Kraken** → continue  

**Region matrix (config):** if Kraken entity cannot withdraw RLUSD on XRPL, show **blocked with alternative** (don’t silently switch the product story to “fund with XRP”). Prefer: waitlist / different venue for RLUSD XRPL / guided workaround labeled Advanced.

**Referral plumbing:**

| Program | Use |
|---------|-----|
| [Kraken Referrals](https://www.kraken.com/referrals) | Invite bonuses |
| [Kraken Affiliate](https://www.kraken.com/affiliate) | Ongoing cut at scale |

Store: `referral.kraken_url`, disclosure copy.  
Disclose: “We may earn a referral fee if you sign up via our link.”

### Step 3–4 — Xaman (cold)

**Copy angle:** “Xaman is your vault. We never ask for this seed. Park profits here later — preferably as RLUSD.”

1. Get Xaman (official links only).  
2. Create + backup + checkbox.  
3. Add RLUSD trustline on cold ([Xaman help](https://help.xaman.app/app/getting-started-with-xaman/how-to-create-a-rlusd-trust-line)).  
4. Optional small XRP on cold for fees only.

### Step 5–6 — Bot wallet (hot)

**Default: generate bot account.**

Show:

- Bot address (r…)  
- “Send **RLUSD** here. This is trading capital.”  
- “Also send **~N XRP once** so the account can pay fees / reserves — gas, not your stake.”  
- Enable RLUSD trustline on bot (required before RLUSD withdraw).

### Step 7 — Fund bot (RLUSD-first)

**Order matters:**

1. **Gas first (if empty):** Kraken → Withdraw **XRP** → XRPL → bot → amount = our **gas target** (e.g. enough for reserve + trustline + buffer).  
2. **Trustline** if not already done.  
3. **Stake:** Kraken → Withdraw **RLUSD** → XRPL → bot → user’s risk amount.  
4. Open Desk detects **RLUSD** on bot → green check / confetti.  

**Primary success metric:** `bot_rlusd_balance >= min_stake` (config).  
XRP only needs `>= gas_floor`.

**Fail cards:**

| Symptom | Cause | Fix |
|---------|--------|-----|
| RLUSD withdraw fails | No bot trustline | Step 6 |
| RLUSD on wrong chain | ERC-20 etc. | “Must be XRP Ledger” |
| Account can’t do anything | No XRP reserve | Send gas XRP (7a) |
| Pending forever | Kraken review | Wait / Kraken support |

### Step 8 — Alerts & AI (optional)

Telegram + Grok; skip on Trial OK.

### Step 9 — Go live

- Recommend **dry-run** until first RLUSD is seen and strategy would trade.  
- Live copy: **“Desk is live — working your RLUSD stake. XRP inventory is the bot’s job.”**  
- Live requires: RLUSD trustline, RLUSD ≥ min (or explicit override), XRP ≥ gas floor, plan allows live.

---

## Recommended vs advanced

| Topic | Recommended | Advanced |
|-------|-------------|----------|
| Stake asset | **RLUSD only** | Manual XRP+RLUSD inventory |
| Cold | Xaman | Other wallets |
| Exchange | Kraken | Other ramps |
| Bot key | Generated | Import secret |
| Gas XRP | One small withdraw we specify | User guesses |

---

## Affiliate / “sumptin sumptin”

Same as before: Kraken link primary; disclose; don’t block existing Kraken users.

### Config keys

```yaml
onboarding:
  funding_mode: rlusd_primary   # locked product story
  recommended:
    cold_wallet: xaman
    exchange: kraken
  links:
    kraken_signup: "https://www.kraken.com/..."  # your referral URL
    xaman_download: "https://xaman.app/"
    xaman_rlusd_help: "https://help.xaman.app/.../how-to-create-a-rlusd-trust-line"
  copy:
    kraken_disclosure: "We may receive a referral reward if you open Kraken via our link."
    stake_headline: "Fund with RLUSD. Let the bot do its job."
  minimums:
    bot_xrp_gas_floor: 12       # reserve + fees buffer (tune live)
    bot_rlusd_min_stake: 50     # below this = “add more stake”
    suggest_first_rlusd: 100    # soft suggestion in UI
  region:
    kraken_rlusd_xrpl_withdraw: true   # set false → show blocked path, not XRP-stake story
```

### Your ops checklist

- [ ] Kraken referral/affiliate URL in config  
- [ ] Confirm **RLUSD withdraw on XRPL** from your Kraken entity  
- [ ] Confirm RLUSD issuer matches Xaman  
- [ ] Bot key custody decision  
- [ ] Three clips: buy RLUSD, bot trustline, withdraw RLUSD to bot  
- [ ] Gas XRP amount tested on mainnet once  

---

## Go-live checklist (product gates)

| Gate | Trial dry-run | Live |
|------|---------------|------|
| Open Desk account | ✓ | ✓ |
| Bot address | ✓ | ✓ |
| Bot RLUSD trustline | ✓ | ✓ |
| Bot XRP ≥ gas floor | recommended | ✓ |
| **Bot RLUSD ≥ min stake** | optional | **✓** |
| Kraken / Xaman | encouraged | encouraged |
| Telegram / Grok | optional | optional |
| Plan / entitlement | ✓ | ✓ live |

---

## Support scripts

**“Do I need to buy XRP to trade?”**  
→ Only a little for **network gas**. Your **stake is RLUSD**. The bot manages XRP as part of its job.

**“How much RLUSD?”**  
→ Start with what you can risk. We suggest $N; minimum to go live is $M.

**“I already have Kraken.”**  
→ Skip referral signup; buy RLUSD → withdraw to bot.

**“Can I just send XRP?”**  
→ Advanced only. Happy path is RLUSD. (If they send XRP anyway, desk can still run — don’t brick them — but UI keeps RLUSD-first messaging.)

**“Can I trade from Xaman?”**  
→ No. Cold vault only. Bot key signs trades.

**“Where does my seed go?”**  
→ Cold seed: nowhere in Open Desk. Bot key: generated or Advanced import.

---

## Implementation order

1. Wizard UI with **RLUSD-first** copy + gas XRP helper  
2. Platform links (Kraken/Xaman) + disclosure  
3. Deposit detector: prioritize **RLUSD balance** green check  
4. Multi-user accounts  
5. Affiliate click tracking  
6. Region flag for RLUSD XRPL withdraw  

---

## Success metrics

| Metric | Target (first 90 days) |
|--------|------------------------|
| Signup → bot + trustline | > 70% |
| Trustline → **first RLUSD deposit** | > 40% |
| RLUSD funded → dry-run/live in 7d | > 50% |
| Support: “how much XRP do I need?” | should fall after gas helper ships |
| Kraken CTA CTR | track |

---

## BLUF

**Fund with RLUSD. Gas with a little XRP. Let the bot do its job.**  

Path: Kraken cash → **RLUSD** → bot (after trustline) → desk works the bag → optional profits to Xaman cold.  

Xaman = cold. Kraken = ramp (+ your referral). Bot = hot risk capital in RLUSD.

---

*Branch: `open-desk` · Companion to `docs/COMMERCIAL_LAUNCH.md` · Funding mode: `rlusd_primary`*
