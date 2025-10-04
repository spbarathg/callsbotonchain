# Signal Bot Tuning Changes V2 - October 5, 2025

## Executive Summary

Applied critical configuration changes to address **5.4% win rate** and **63% rug rate** identified through signal performance analysis.

---

## 🎯 Changes Applied

### 1. **Score Threshold (CRITICAL)**
**Before:** `HIGH_CONFIDENCE_SCORE=8`  
**After:** `HIGH_CONFIDENCE_SCORE=9`  
**Reason:** Be more selective with signals. Only the highest quality tokens should trigger alerts.

### 2. **Holder Concentration (ANTI-RUG)**
**Before:** `MAX_TOP10_CONCENTRATION=30`  
**After:** `MAX_TOP10_CONCENTRATION=18`  
**Reason:** Reject tokens where top 10 wallets hold >18%. High concentration = rug risk. Reduced from 30% to 18% to filter out likely rugs.

### 3. **Security Verification (ANTI-RUG)**
**Before:** `ALLOW_UNKNOWN_SECURITY=true`  
**After:** `ALLOW_UNKNOWN_SECURITY=false`  
**Reason:** Only alert on tokens with verified security status (LP locked, mint revoked). No more gambling on unverified tokens.

### 4. **Minimum Liquidity (QUALITY FILTER)**
**Before:** `MIN_LIQUIDITY_USD=15000`  
**After:** `MIN_LIQUIDITY_USD=20000`  
**Reason:** Increase minimum liquidity requirement. Higher liquidity = more serious projects, harder to manipulate.

### 5. **Volume-to-Market-Cap Ratio (ANTI-WASH-TRADING)**
**Before:** `VOL_TO_MCAP_RATIO_MIN=0.15`  
**After:** `VOL_TO_MCAP_RATIO_MIN=0.20`  
**Reason:** Require higher volume relative to market cap. Filters out tokens with fake/wash trading volume.

### 6. **Minimum Transaction Size (NOISE FILTER)**
**Before:** `MIN_USD_VALUE=200`  
**After:** `MIN_USD_VALUE=300`  
**Reason:** Ignore small transactions. Focus on meaningful trades from real participants.

### 7. **Preliminary Score Requirement (QUALITY GATE)**
**Before:** `PRELIM_DETAILED_MIN=2`  
**After:** `PRELIM_DETAILED_MIN=3`  
**Reason:** Require more preliminary positive signals before triggering detailed analysis. Reduces false positives.

### 8. **Market Cap Ceiling (FOCUS ADJUSTMENT)**
**Before:** `MAX_MARKET_CAP_FOR_DEFAULT_ALERT=1000000`  
**After:** `MAX_MARKET_CAP_FOR_DEFAULT_ALERT=750000`  
**Reason:** Focus on earlier-stage tokens (under $750k mcap) where gains are larger. Tokens over $1M often already pumped.

---

## 📊 Expected Impact

### Signal Volume
- **Expected:** 40-60% reduction in signal volume
- **Reason:** Stricter filters will reject more tokens
- **Benefit:** Higher quality over quantity

### Win Rate
- **Current:** 5.4%
- **Target:** 10-15% (conservative) to 20%+ (optimistic)
- **Drivers:** Better rug filtering, higher quality tokens

### Rug Rate
- **Current:** 63% (235/373 tokens)
- **Target:** <30% (ideally <20%)
- **Drivers:** 
  - Holder concentration filter (18% max)
  - Security verification required
  - Higher liquidity requirement
  - Better volume/mcap ratio

### Smart Money Performance
- **Current:** -6.1% disadvantage (worse than non-smart-money)
- **Action Taken:** No longer requiring smart money for alerts
- **Status:** Smart money detection needs separate audit (future work)

---

## 🔍 Monitoring & Validation

### Immediate Checks (Next 1-2 Hours)
1. ✅ Worker restarted successfully
2. Monitor signal volume - should drop significantly
3. Check for any configuration errors in logs
4. Verify first few alerts meet new criteria

### 24-Hour Analysis
Run signal analysis after 24 hours:
```bash
python monitoring/unified_monitor.py
```

Look for:
- Win rate improvement (target: >10%)
- Rug rate reduction (target: <30%)
- Total signals (expect 5-15 signals vs 373)
- Average gain on wins

### 7-Day Review
After one week, analyze:
- Win rate stability
- Average time to peak
- Maximum gains achieved
- Rug pattern changes
- Need for further tuning

---

## 🛠️ Rollback Instructions

If performance worsens or signals stop completely:

```bash
# SSH to server
ssh root@64.227.157.221

# Restore backup
cd /opt/callsbotonchain
cp .env.backup_tuning_v2 .env

# Restart worker
docker compose restart worker
```

---

## 📋 Configuration Summary

### Current Active Settings (Post-Change)
```bash
# Core Gates
HIGH_CONFIDENCE_SCORE=9
MIN_LIQUIDITY_USD=20000
VOL_TO_MCAP_RATIO_MIN=0.20
MAX_MARKET_CAP_FOR_DEFAULT_ALERT=750000
PRELIM_DETAILED_MIN=3

# Anti-Rug Filters
MAX_TOP10_CONCENTRATION=18
ALLOW_UNKNOWN_SECURITY=false
REQUIRE_LP_LOCKED=true
REQUIRE_MINT_REVOKED=true

# Transaction Filters
MIN_USD_VALUE=300

# Smart Money (Not Required)
REQUIRE_SMART_MONEY_FOR_ALERT=false
```

---

## 🎯 Success Criteria

These changes will be considered **successful** if after 24-48 hours:

1. ✅ **Win Rate:** Increases from 5.4% to at least 10%
2. ✅ **Rug Rate:** Decreases from 63% to under 35%
3. ✅ **Signal Volume:** Drops to 5-20 signals per 24h (quality over quantity)
4. ✅ **Smart Money Advantage:** Becomes positive or neutral (not negative)
5. ✅ **No Critical Issues:** Worker remains stable, no crashes

---

## 📝 Notes

- **Backup Created:** `.env.backup_tuning_v2`
- **Applied:** October 5, 2025 at 02:19 UTC
- **Worker Restarted:** Yes
- **Monitoring Active:** unified_monitor.py running
- **Analysis Window:** 24 hours for next review

---

## 🔮 Future Improvements (Not in This Change)

1. **Smart Money Detection Audit**
   - Current smart money has -6% advantage (broken)
   - Need to audit wallet list for bots/rugs
   - Consider time-based wallet scoring

2. **Holder Quality Scoring**
   - Check wallet age
   - Check wallet history (serial ruggers?)
   - Bonus for known good actors

3. **Honeypot Detection**
   - Pre-check sell tax before alerting
   - Test token transferability
   - Check for hidden restrictions

4. **Liquidity Lock Verification**
   - Not just "locked" but verify lock duration
   - Check lock contract reputation
   - Verify LP tokens are actually locked

5. **Time-Based Filters**
   - Token age requirements
   - Recent activity patterns
   - Launch detection (catch them earlier)

---

## Contact

For questions or issues:
- Check logs: `ssh root@64.227.157.221 "cd /opt/callsbotonchain && docker compose logs worker"`
- View monitoring: Dashboard at http://64.227.157.221
- Analysis: `python monitoring/analyze_signals.py`
