# Foolproof onboarding — Open Desk (v1)

**Audience:** brand-new subscribers who should never need a terminal, YAML, or “what is a trustline” lecture.  
**Stack we push (happy path):**

| Role | Tool | Why |
|------|------|-----|
| **Cold / self-custody** | [Xaman](https://xaman.app/) | Best-in-class XRPL wallet UX; RLUSD trustline is one flow |
| **Exchange + fiat on-ramp** | [Kraken](https://www.kraken.com/) | Deposit cash, buy XRP / RLUSD, withdraw to XRPL |
| **Trading bot wallet** | Fresh XRPL account used **only** by the desk | Risk capital isolation (never the cold wallet seed) |

**Affiliate / referral intent:** deep-link users through **your** Kraken referral/affiliate link and **your** preferred Xaman entry where allowed, so you get “a little sumptin sumptin” when they sign up and fund. Config lives in platform settings (not hard-coded secrets in the client).

---

## One picture (what we teach)

```text
  COLD (sleep well)              HOT (desk only)              EXCHANGE (fiat door)
  ─────────────────              ───────────────              ────────────────────
  Xaman                          Bot account                  Kraken
  long-term XRP/RLUSD            only what you risk           buy / sell / cash in
         │                              ▲                            │
         │  optional top-up             │  withdraw XRP + RLUSD      │
         └──────────────────────────────┴────────────────────────────┘
                         never put bot seed in Xaman “main” stash
                         never put cold seed into LedgerMate
```

**Rules of thumb (repeat on every screen):**

1. **Cold stays cold** — Xaman is for savings. Do not paste that seed into Open Desk.  
2. **Bot is disposable capital** — only fund the bot with money you’re willing to trade.  
3. **Kraken is the on-ramp** — cash → crypto → withdraw to bot (and optionally cold).  
4. **RLUSD needs a trustline** on any XRPL account that will hold it (bot + cold).  
5. **Green checks only** — no “live” until checklist is complete.

---

## End-to-end happy path (timeboxed)

Target: **under 30 minutes** for a motivated user (KYC may add time).

| Step | Where | User does | We show | Done when |
|------|--------|-----------|---------|-----------|
| **0** | Open Desk | Sign up (email + password) | Plan picker (Trial / Pro) | Account created |
| **1** | Kraken | Sign up via **your referral link** + KYC | “Get cash in the door” | Deposit ready |
| **2** | Kraken | Buy **XRP** (and **RLUSD** if listed for their region) | Short video / 3 bullets | Balances > 0 |
| **3** | Xaman | Install app, create **cold** wallet, backup phrase **offline** | “This is NOT the bot” | Phrase secured (self-attested) |
| **4** | Xaman | Add **RLUSD** token / Setup TrustLine | Link to Xaman help + in-app steps | RLUSD visible |
| **5** | Open Desk | **Create bot wallet** (we generate) or import advanced | Address + QR + reserve note | Bot address known |
| **6** | Bot (Xaman xApp or our deep link) | Enable **RLUSD trustline** on **bot** address | One-slide “Slide to accept” | Trustline live |
| **7** | Kraken | Withdraw **XRP** + **RLUSD** to **bot** address (XRPL network) | Copy address / network warning | First deposit seen |
| **8** | Open Desk | Optional: Telegram + Grok | Skip allowed on Trial | Preferences saved |
| **9** | Open Desk | Dry-run or Go live | Plain-English status | Desk running |

**Optional later:** move profits bot → Xaman cold (withdraw from desk / manual send with clear “to cold” destination).

---

## Screen-by-screen UX (retard-proof)

### Global UI patterns

- **Progress bar:** `Setup 3 of 9` always visible.  
- **Primary button only one** per screen (“Continue”). Secondary = “I’m stuck / help”.  
- **No jargon without a tooltip.** Trustline = “permission for this account to hold RLUSD.”  
- **Copy buttons** on every address; wrong-network warnings in red.  
- **Self-attest checkboxes** for “I wrote down my Xaman phrase” — we never see the phrase.  
- **Recommended path locked as default.** Advanced (other exchange / import seed) behind “I know what I’m doing.”

### Step 1–2 — Kraken (on-ramp)

**Copy angle:** “Buy crypto the boring way. We use Kraken so you can deposit dollars/euros and withdraw to the XRP Ledger.”

Buttons:

1. **Open Kraken with our link** → your referral/affiliate URL  
2. Checklist: Verify → Deposit cash → Buy XRP → (Buy RLUSD if available)  
3. **I’ve funded Kraken** → continue  

**Referral plumbing:**

| Program | Use |
|---------|-----|
| [Kraken Referrals](https://www.kraken.com/referrals) | Friends/family style bonuses when they sign up + trade via your invite |
| [Kraken Affiliate](https://www.kraken.com/affiliate) | Longer-term revenue share (apply; better if you market at scale) |

Store in platform config: `referral.kraken_url`, `referral_kraken_code`, `referral_label`.  
Track: `user_id`, `clicked_at`, `self_reported_funded_at` (and later webhook if Kraken provides partner APIs).

**Compliance note:** disclose “We may earn a referral fee if you sign up via our link” in small print.

### Step 3–4 — Xaman (cold)

**Copy angle:** “Xaman is your vault. We never ask for this seed.”

1. **Get Xaman** (App Store / Play / official site links only).  
2. Create wallet → **backup** → checkbox “Phrase is offline and not screenshotted.”  
3. **Add RLUSD** → follow [Xaman RLUSD trustline help](https://help.xaman.app/app/getting-started-with-xaman/how-to-create-a-rlusd-trust-line) (embed screenshots in product).  
4. Optional: deposit a little XRP to cold for reserve/fees.

**Referral:** Xaman/xApps rarely pay like exchanges; still **recommend Xaman exclusively** for cold (product quality + fewer support tickets). If an official partner program appears later, plug it the same way as Kraken.

### Step 5–6 — Bot wallet (hot)

**Default: we generate a new bot account** (encrypted secret server-side or user-held export — product decision Phase 0).

Show:

- Bot address (r…)  
- “This is the only address Kraken should withdraw to for trading.”  
- Minimum XRP for reserve + trustline (live-calculated or static safe floor, e.g. “keep ≥ 12 XRP free after trustline”).  
- **Enable RLUSD on bot** — Xaman can manage a second account / or deep-link TrustSet for that address (implementation detail).

**Advanced:** import existing bot secret — scary path, extra warnings.

### Step 7 — First fund (Kraken → bot)

Checklist with exact field labels:

1. Kraken → Withdraw → Asset **XRP** → Network **XRP Ledger** → Address **[bot]** → Amount  
2. Same for **RLUSD** on XRPL (if their Kraken entity supports RLUSD XRPL withdraw; else buy XRP only and swap later — **region matrix** in config)  
3. Open Desk **detects deposit** (poll account) → confetti / green check  

**Fail states (pre-written help):**

| Symptom | Likely cause | Fix card |
|---------|--------------|----------|
| Withdraw pending forever | Kraken review / destination tag | Wait / support Kraken |
| RLUSD withdraw fails | No trustline on bot | Re-run step 6 |
| “Insufficient reserve” | Spent all XRP on trustline | Send more XRP |
| Wrong chain | User picked ERC-20 | Big red “XRPL only” |

### Step 8 — Alerts & AI (optional)

- Telegram: BotFather 4 steps with screenshots.  
- Grok: paste key + “Test” button.  
- Trial can skip both.

### Step 9 — Go live

- Default: **Dry-run 24h** recommended.  
- Live requires: bot funded, RLUSD trustline (if strategy needs RLUSD), not halted, plan allows live.  
- One sentence status: “Desk is live — only risking bot wallet balance.”

---

## Recommended vs advanced (keep the happy path narrow)

| Topic | Recommended | Advanced (collapsed) |
|-------|-------------|----------------------|
| Cold wallet | Xaman only | Other XRPL wallets |
| Exchange / fiat | Kraken only | Coinbase, Bitstamp, etc. |
| Bot key | Generated by Open Desk | Import secret |
| RLUSD | Official issuer + Xaman “Add RLUSD” | Manual issuer paste |
| Funding | Kraken → bot | DEX-only, P2P |

Support cost drops when 95% of users never open Advanced.

---

## Affiliate / “sumptin sumptin” design

### Principles

1. **Disclose** referral relationships.  
2. **Never block** onboarding if user already has Kraken/Xaman without your link (don’t punish existing accounts).  
3. **Primary CTA** still uses your link for new users.  
4. **Track clicks** even if conversion is self-reported at first.  
5. Separate **your personal referral codes** (config) from **user’s own** future codes (if you add a user-referral program later).

### Config keys (platform)

```yaml
onboarding:
  recommended:
    cold_wallet: xaman
    exchange: kraken
  links:
    kraken_signup: "https://www.kraken.com/..."   # your referral/affiliate URL
    xaman_download: "https://xaman.app/"
    xaman_rlusd_help: "https://help.xaman.app/.../how-to-create-a-rlusd-trust-line"
  copy:
    kraken_disclosure: "We may receive a referral reward if you open Kraken via our link."
  minimums:
    bot_xrp_reserve_buffer: 12   # tune from live reserve rules
    suggest_first_xrp: 50
    suggest_first_rlusd: 100
```

### Your action items (ops, not code)

- [ ] Grab **Kraken invite link** from [Referrals](https://www.kraken.com/referrals) and/or apply to [Affiliate](https://www.kraken.com/affiliate) for higher long-term cut.  
- [ ] Confirm **your region**: can you withdraw **RLUSD on XRPL** from Kraken, or only XRP? Document both paths.  
- [ ] Confirm **RLUSD issuer** we hardcode for trustline (mainnet) matches Xaman’s listed RLUSD.  
- [ ] Decide custody: we store encrypted bot secret vs user exports only.  
- [ ] Record short **3 screen recordings**: Kraken buy, Xaman trustline, Kraken withdraw to bot.

---

## Go-live checklist (product gates)

| Gate | Required for Trial dry-run | Required for Live |
|------|----------------------------|-------------------|
| Open Desk account | ✓ | ✓ |
| Bot address exists | ✓ | ✓ |
| Bot has XRP reserve | recommended | ✓ |
| Bot RLUSD trustline | if strategy needs RLUSD | ✓ if trading RLUSD |
| First deposit detected | optional | ✓ |
| Kraken/Xaman | encouraged | encouraged |
| Telegram | optional | optional (recommended) |
| Grok | optional | optional |
| Plan paid / trial valid | ✓ | ✓ live entitlement |

---

## Support scripts (copy-paste)

**“I already have Kraken.”**  
→ Skip signup link; jump to “Buy XRP / withdraw to bot.” No referral for us; still fine.

**“I already have Xaman.”**  
→ Use it as cold; still create a **separate** bot account for the desk.

**“Can I trade from Xaman directly?”**  
→ No. Desk signs with the **bot** key only. Cold stays offline.

**“Is this a fund?”**  
→ No. Self-directed software; you control wallets and risk capital.

**“Where do I put my seed?”**  
→ **Nowhere in Open Desk for cold.** Bot key is generated or imported once under scary Advanced.

---

## Implementation order (after this plan is approved)

1. **Static setup wizard** in HUD (checklist UI + links + copy buttons) — even before multi-tenant.  
2. Platform config for Kraken/Xaman URLs + disclosure.  
3. Deposit detector on bot address (poll balances).  
4. Multi-user accounts (Phase 1) wrapping the same wizard.  
5. Affiliate click analytics.  
6. Region matrix for RLUSD-on-Kraken.

---

## Success metrics

| Metric | Target (first 90 days) |
|--------|------------------------|
| Signup → bot created | > 70% |
| Bot created → first XRPL deposit | > 40% |
| Deposit → dry-run or live within 7d | > 50% |
| Support tickets per funded user | trending down |
| Kraken link CTR | track; optimize CTA |

---

## BLUF

**One path:** Kraken for money in → Xaman for cold vault → dedicated bot wallet for Open Desk → RLUSD trustline on bot → withdraw from Kraken to bot → dry-run → live.  

**Your upside:** official recommended stack + Kraken referral/affiliate links.  

**Their safety:** cold never touches the bot; only risk capital on the desk.

---

*Branch: `open-desk` · Companion to `docs/COMMERCIAL_LAUNCH.md`*
