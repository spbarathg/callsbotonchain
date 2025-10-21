# 🔄 SIGNAL DETECTION FLOW - VISUAL DIAGRAM

**Date:** October 21, 2025  
**Purpose:** Visual representation of how signals flow through the detection system

---

## 📊 COMPLETE SIGNAL FLOW

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CIELO API FEED (Every 30s)                      │
│                    60-80 tokens per cycle                           │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    STEP 1: PRELIMINARY SCORING                      │
│                    (Fast Filter - No API Calls)                     │
├─────────────────────────────────────────────────────────────────────┤
│  • Base Score: 1                                                    │
│  • USD Value Check:                                                 │
│    - >$10k: +3                                                      │
│    - >$2k:  +2                                                      │
│    - >$200: +1                                                      │
│                                                                     │
│  Result: Preliminary Score 1-4                                      │
│                                                                     │
│  ❌ REJECT if prelim_score < 3                                      │
│  ✅ PASS: 10-20 tokens → Detailed Analysis                         │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│              STEP 2: FETCH DETAILED STATS                           │
│              (Cielo API + DexScreener)                              │
├─────────────────────────────────────────────────────────────────────┤
│  • Market Cap                                                       │
│  • Liquidity                                                        │
│  • 24h Volume                                                       │
│  • Price Changes (1h, 24h)                                          │
│  • Holder Count & Concentration                                     │
│  • Bundler/Insider Metrics                                          │
│  • LP Lock Status                                                   │
│  • Security Info                                                    │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    STEP 3: DETAILED SCORING                         │
│                    (Calculate Final Score 0-10)                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ MARKET CAP ANALYSIS (Data-Driven)                          │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  <$50k:      +2 (63% avg gain, 53.7% WR)                   │   │
│  │  <$100k:     +2 (207% avg gain, 68.4% WR)                  │   │
│  │  <$200k:     +3 (267% avg gain, 70.8% WR) ⭐ BEST!         │   │
│  │  <$1M:       +1 (61% avg gain, 67.2% WR)                   │   │
│  │                                                             │   │
│  │  2X SWEET SPOT ($20k-$200k): +1                            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ LIQUIDITY ANALYSIS                                          │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  ≥$50k:  +3 (VERY GOOD)                                    │   │
│  │  ≥$30k:  +2 (GOOD)                                         │   │
│  │  ≥$15k:  +1 (ACCEPTABLE)                                   │   │
│  │                                                             │   │
│  │  Winner-Tier (≥$18k): +1                                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ VOLUME ANALYSIS                                             │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  24h Volume:                                                │   │
│  │    ≥$100k: +3                                               │   │
│  │    ≥$50k:  +2                                               │   │
│  │    ≥$10k:  +1                                               │   │
│  │                                                             │   │
│  │  Vol/MCap Ratio:                                            │   │
│  │    ≥3.0: +2 (VERY HIGH activity)                           │   │
│  │    ≥1.0: +1 (HIGH activity)                                │   │
│  │    ≥0.3: +1 (GOOD activity)                                │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ MOMENTUM ANALYSIS                                           │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  1h Change:                                                 │   │
│  │    >50%: +2 (Strong pump)                                   │   │
│  │    >20%: +1 (Moderate pump)                                │   │
│  │                                                             │   │
│  │  24h Change:                                                │   │
│  │    >100%: +2 (Major pump)                                   │   │
│  │    >50%:  +1 (Good pump)                                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ HOLDER ANALYSIS                                             │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  Holder Count:                                              │   │
│  │    ≥500: +2 (Strong community)                             │   │
│  │    ≥200: +1 (Growing community)                            │   │
│  │                                                             │   │
│  │  Concentration Penalties:                                   │   │
│  │    Top10 >30%: -1                                           │   │
│  │    Bundlers >15%: -1                                        │   │
│  │    Insiders >25%: -1                                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ MULTI-BOT CONSENSUS (NEW!)                                  │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  3+ bots alerting: +2 (Strong validation)                  │   │
│  │  2 bots alerting:  +1 (Moderate validation)                │   │
│  │  0 other bots:     -1 (Solo signal, risky)                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ RISK PENALTIES                                              │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │  24h Change <-60%: -1 (Major dump risk)                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Result: Final Score 0-10                                           │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  STEP 4: SCORE THRESHOLD GATE                       │
│                  (CRITICAL QUALITY FILTER)                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  if score < GENERAL_CYCLE_MIN_SCORE (7 or 8):                      │
│      ❌ REJECT: "Score Below Threshold"                             │
│                                                                     │
│  ENFORCED FOR ALL SIGNALS (smart money or not)                     │
│                                                                     │
│  ✅ PASS: Only Score 7+ signals (top 10-15% of tokens)             │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  STEP 5: SENIOR STRICT CHECK                        │
│                  (Hard Safety Filters)                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ❌ REJECT if:                                                      │
│    • MCap < $10k (death zone - 63.9% rug rate)                     │
│    • MCap > $500k (too established)                                │
│    • Top10 Concentration > 30%                                     │
│    • Bundlers > 15%                                                │
│    • Insiders > 25%                                                │
│    • 24h Volume < $10k                                             │
│                                                                     │
│  ✅ PASS: Safe from obvious scams/rugs                             │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  STEP 6: JUNIOR STRICT CHECK                        │
│                  (Quality Filters)                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ❌ REJECT if:                                                      │
│    • Liquidity < $30k (if filter enabled)                          │
│    • Vol/MCap Ratio < 0.3 (30%)                                    │
│                                                                     │
│  NOTE: Liquidity filter DISABLED in V4 Moonshot Hunter             │
│                                                                     │
│  ✅ PASS: High-quality tradeable signal                            │
│  ❌ FAIL: Try Junior Nuanced (fallback)                            │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                    ▼                           ▼
        ┌─────────────────────┐   ┌─────────────────────────┐
        │  JUNIOR STRICT      │   │  JUNIOR NUANCED         │
        │  PASSED             │   │  (Fallback)             │
        └─────────────────────┘   └─────────────────────────┘
                    │                           │
                    │              ┌────────────┘
                    │              │
                    │              │ Relaxed Criteria:
                    │              │ • 70% liquidity
                    │              │ • 50% vol/mcap
                    │              │ • Score -2 penalty
                    │              │
                    └──────────────┴──────────────┐
                                                  ▼
                    ┌─────────────────────────────────────────┐
                    │  CONVICTION TYPE ASSIGNED               │
                    ├─────────────────────────────────────────┤
                    │  • High Confidence (Strict)             │
                    │  • Nuanced Conviction (Smart Money)     │
                    └─────────────────────────────────────────┘
                                                  │
                                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  STEP 7: SIGNAL GENERATION                          │
│                  (Create Alert & Push to Redis)                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. Store in Database (alerted_tokens.db)                           │
│  2. Send Telegram Alert (Telethon)                                  │
│  3. Push to Redis (for trader consumption)                          │
│                                                                     │
│  Alert Includes:                                                    │
│    • Token Address & Name                                           │
│    • Score (7-10)                                                   │
│    • Market Cap, Liquidity, Volume                                  │
│    • Price Changes (1h, 24h)                                        │
│    • Conviction Type                                                │
│    • Risk Tier (Moonshot/Aggressive/Calculated)                    │
│    • Position Size Recommendation                                   │
│    • Trading Strategy                                               │
│    • DexScreener & Raydium Links                                    │
│                                                                     │
│  ✅ SIGNAL GENERATED!                                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📊 SIGNAL FUNNEL (Typical Cycle)

```
┌────────────────────────────────────────┐
│  CIELO FEED: 60-80 tokens              │  100%
└────────────────────────────────────────┘
                  │
                  ▼
┌────────────────────────────────────────┐
│  Preliminary Filter: 10-20 tokens      │  15-25%
└────────────────────────────────────────┘
                  │
                  ▼
┌────────────────────────────────────────┐
│  Detailed Analysis: 10-20 tokens       │  15-25%
└────────────────────────────────────────┘
                  │
                  ▼
┌────────────────────────────────────────┐
│  Score 7+ Filter: 2-5 tokens           │  3-8%
└────────────────────────────────────────┘
                  │
                  ▼
┌────────────────────────────────────────┐
│  Senior Strict: 1-3 tokens             │  1-5%
└────────────────────────────────────────┘
                  │
                  ▼
┌────────────────────────────────────────┐
│  Junior Strict/Nuanced: 0-2 tokens     │  0-3%
└────────────────────────────────────────┘
                  │
                  ▼
┌────────────────────────────────────────┐
│  SIGNALS GENERATED: 0-2 per cycle      │  0-3%
│  (10-30 per day)                       │
└────────────────────────────────────────┘
```

**Pass Rate:** 1-3% (very selective!)

---

## 🎯 PARALLEL PROCESSES

```
┌─────────────────────────────────────────────────────────────────────┐
│                     SIGNAL AGGREGATOR                               │
│                     (Separate Container)                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Monitors 13 External Telegram Groups:                              │
│    • @MooDengPresidentCallers                                       │
│    • @AnotherBotGroup                                               │
│    • ... (11 more groups)                                           │
│                                                                     │
│  Extracts Token Addresses from Messages                             │
│                                                                     │
│  Stores in Redis:                                                   │
│    signal_aggregator:token:{address} = timestamp                    │
│                                                                     │
│  Used by Scoring System for Multi-Bot Consensus                     │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                          ┌───────────────┐
                          │     REDIS     │
                          │  (IPC Layer)  │
                          └───────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                    ▼                           ▼
        ┌─────────────────────┐   ┌─────────────────────────┐
        │  WORKER CONTAINER   │   │  TRADER CONTAINER       │
        │  (Signal Detection) │   │  (Trade Execution)      │
        └─────────────────────┘   └─────────────────────────┘
```

---

## 🔍 EXAMPLE: SIGNAL LIFECYCLE

### **Token: ABC (Market Cap $89,701)**

```
Time: 10:30:24 IST

STEP 1: Preliminary Scoring
  • USD Value: $5,000
  • Score: 1 + 2 = 3 ✅ PASS

STEP 2: Fetch Detailed Stats
  • Market Cap: $89,701
  • Liquidity: $34,268
  • 24h Volume: $786,175
  • 1h Change: +3.2%
  • 24h Change: +1.3%
  • Holders: 450

STEP 3: Detailed Scoring
  • Market Cap <$100k: +2
  • 2X Sweet Spot: +1
  • Liquidity ≥$30k: +2
  • Winner-Tier Liquidity: +1
  • Volume ≥$100k: +3
  • Vol/MCap Ratio ≥3.0: +2
  • Holders ≥200: +1
  • Multi-Bot Consensus (3 bots): +2
  
  Final Score: 10/10 ⭐

STEP 4: Score Threshold
  • Score 10 ≥ 7 ✅ PASS

STEP 5: Senior Strict
  • MCap $89,701 (within $10k-$500k) ✅
  • Top10 Concentration: 25% (<30%) ✅
  • Bundlers: 10% (<15%) ✅
  • Insiders: 20% (<25%) ✅
  • Volume $786k (>$10k) ✅
  ✅ PASS

STEP 6: Junior Strict
  • Liquidity filter DISABLED ✅
  • Vol/MCap Ratio: 8.77 (>0.3) ✅
  ✅ PASS

STEP 7: Signal Generated
  • Conviction: High Confidence (Strict)
  • Risk Tier: TIER 2 (Aggressive)
  • Position Size: 20%
  • Telegram Alert: ✅ Sent
  • Redis Push: ✅ Success
  
✅ SIGNAL COMPLETE!
```

---

## 📈 REJECTION EXAMPLES

### **Example 1: Score Too Low**

```
Token: XYZ (Market Cap $19,206)

STEP 3: Detailed Scoring
  • Market Cap <$50k: +2
  • 2X Sweet Spot: +1
  • Liquidity $8k: +0 (too low)
  • Volume $5k: +0 (too low)
  • Holders 50: +0 (too few)
  
  Final Score: 4/10

STEP 4: Score Threshold
  • Score 4 < 7 ❌ REJECT
  
Reason: "Score Below Threshold"
```

### **Example 2: Market Cap Too Low**

```
Token: DEF (Market Cap $6,032)

STEP 5: Senior Strict
  • MCap $6,032 < $10,000 ❌ REJECT
  
Reason: "MARKET CAP TOO LOW (death zone - 63.9% rug rate)"
```

### **Example 3: Holder Concentration**

```
Token: GHI (Market Cap $150,000)

STEP 5: Senior Strict
  • Top10 Concentration: 45% (>30%) ❌ REJECT
  
Reason: "Failed senior strict check (concentration)"
```

---

## ✅ KEY TAKEAWAYS

1. **Multi-Layer Filtering:** 7 steps from feed to signal
2. **Very Selective:** Only 1-3% of tokens pass
3. **Data-Driven:** Every threshold backed by performance analysis
4. **Quality Over Quantity:** 10-30 signals per day (not 100+)
5. **Consensus Validation:** Multi-bot checking reduces false positives
6. **Risk Management:** Multiple safety checks prevent rugs/scams

**Result:** High-quality signals with 30-40% expected win rate! 🚀

