# 🤖 Bot Status - MICRO-CAP MODE ACTIVE (OPTIMIZED)

**Last Updated:** October 16, 2025, 6:25 PM IST  
**Status:** ✅ **MICRO-CAP MODE - FULLY OPTIMIZED (Critical Fix Applied)**

---

## 🎯 CURRENT CONFIGURATION

### MICRO-CAP MODE (Winner-Median Optimized + Critical Fix)

```
✅ Score threshold: 5 (balanced micro-cap quality)
✅ Fetch interval: 30s (2x faster - NO FREQUENCY CAP!)
✅ Min Liquidity: $18,000 (winner median: $17,811)
✅ Min Volume: $5,000 (FIXED: was $8k - was blocking 10/10 signals!)
✅ Prelim threshold: 0 (analyze everything)
✅ MAX_24H_CHANGE: 300% (catch mid-pump)
✅ MAX_1H_CHANGE: 200% (parabolic moves OK)
✅ Min holders: 50 (early stage friendly)
✅ MAX_TOP10: 30% (micro-cap distribution)
```

---

## 📊 EXPECTED PERFORMANCE

**Signal Frequency:** 20-30/hour (NO CAP - fast detection)  
**Target Hit Rate:** 30-40% achieving 2x+ gains  
**Entry Point:** VERY EARLY (prelim 2+, $18k liquidity)  
**Upside Potential:** 2x-10x (micro-caps pump fast)  
**Risk Level:** MODERATE (micro-caps volatile but highest upside)

---

## 🚀 WHY THIS CONFIGURATION WORKS

1. **Winner Median Match**: $18k liquidity matches exactly where 2x+ winners were found ($17.8k median from data analysis)
2. **No Frequency Cap**: 30s intervals catch micro-caps the moment they start moving (2x more checks than standard)
3. **Balanced Scoring**: Score 5+ ensures quality without missing early opportunities
4. **Micro-Cap Focus**: All thresholds tuned for <$150k mcap tokens with 2x+ potential
5. **Fast Pump Detection**: 300% 24h / 200% 1h allows catching ongoing parabolic moves (micro-caps pump fast!)

---

## 📈 KEY OPTIMIZATIONS (vs Quality Mode)

| Parameter | Quality Mode | MICRO-CAP MODE | Impact |
|-----------|-------------|----------------|--------|
| **FETCH_INTERVAL** | 60s | **30s** | 🚀 2x more checks |
| **PRELIM_MIN** | 4 | **2** | 📈 Catch earlier |
| **MIN_LIQUIDITY** | $30k | **$18k** | 💰 Winner median! |
| **MIN_SCORE** | 7 | **5** | ⚖️ Balanced quality |
| **MAX_24H_CHANGE** | 150% | **300%** | 🎢 Catch mid-pump |
| **MAX_1H_CHANGE** | 100% | **200%** | ⚡ Parabolic moves |
| **VOL/MCAP_RATIO** | 30% | **15%** | 🎯 Early activity |
| **MIN_VOLUME** | $20k | **$8k** | 🔍 Micro-cap volume |
| **MIN_HOLDERS** | 100 | **50** | 👥 Early stage OK |

---

## 🔍 MONITORING

**Check Signal Quality:**
```bash
ssh root@64.227.157.221 "cd /opt/callsbotonchain/deployment && docker compose logs worker --tail 50"
```

**View Recent Alerts:**
```bash
ssh root@64.227.157.221 "cd /opt/callsbotonchain && sqlite3 deployment/var/alerted_tokens.db 'SELECT datetime(alerted_at, \"unixepoch\") as time, substr(token_address,1,10) as token, final_score FROM alerted_tokens ORDER BY alerted_at DESC LIMIT 10'"
```

---

## 📚 DOCUMENTATION

- **Full Setup:** `docs/quickstart/CURRENT_SETUP.md`
- **Performance Tracking:** `docs/performance/TRACKING_SYSTEM.md`
- **Configuration Details:** `docs/configuration/BOT_CONFIGURATION.md`
- **Deployment Guide:** `docs/deployment/QUICK_REFERENCE.md`

---

**Status:** ✅ **MICRO-CAP MODE ACTIVE - FULLY OPTIMIZED**  
**Hit Rate Target:** 30-40% (optimized for micro-cap winners)  
**Latest Fixes:** 
- MIN_VOLUME: $8k → $5k (catching more early gems)
- MAX_MARKET_CAP: $50M → $1M (MICRO-CAP ONLY!)
**Commit:** `31dce51` (Focus ONLY on sub-$1M micro-caps for maximum upside)
