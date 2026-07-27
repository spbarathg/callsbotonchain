# Trading Bot Status Report
**Generated:** 2026-01-29 15:45 UTC  
**Server:** 188.166.63.71

---

## System Health

| Container | Status |
|-----------|--------|
| callsbot-trader | ✅ Up 16 minutes (healthy) |
| callsbot-worker | ✅ Up 10 hours (healthy) |
| callsbot-web | ✅ Up 10 hours |
| callsbot-atm-ingest | ✅ Up 3 days (healthy) |
| callsbot-signal-aggregator | ✅ Up 3 days (healthy) |
| callsbot-tracker | ✅ Up 3 days (healthy) |
| callsbot-redis | ✅ Up 3 days (healthy) |
| callsbot-proxy | ✅ Up 3 days |

---

## Wallet Status

| Metric | Value |
|--------|-------|
| **SOL Balance** | 0.2225 SOL |
| **USD Value** | ~$26.00 |
| **USDC Balance** | $0.00 |

---

## Open Positions (3)

| Token | Entry Price | Quantity | Cost | Status |
|-------|-------------|----------|------|--------|
| sGGiTvmw (GITPAID) | $0.0000214 | 131,405.72 | $2.82 | ⚠️ No on-chain balance |
| 5d4FEsry | $0.0000311 | 121,063.47 | $3.76 | ✅ Active |
| 9u5HdmkQ | $0.0000412 | 105,184.17 | $4.33 | ✅ Active |

**Total Open Value:** ~$10.91

---

## Recent Performance (Last 20 Trades)

| Metric | Value |
|--------|-------|
| **Wins** | 9 |
| **Losses** | 11 |
| **Win Rate** | 45% |
| **Total Invested** | $53.08 |
| **Total Returned** | $59.51 |
| **Net P&L** | **+$6.43** |

### Notable Recent Trades

| Token | Cost | Sold | P&L | Result |
|-------|------|------|-----|--------|
| E41KCE1b | $3.36 | $9.00 | **+$5.64 (+168%)** | 🏆 Big Win |
| AYxY6Vxz | $3.26 | $6.47 | **+$3.21 (+99%)** | 🏆 Big Win |
| 3qLdCMPj | $3.92 | $6.73 | **+$2.81 (+72%)** | ✅ Win |
| PFcJrF9P | $3.72 | $6.35 | **+$2.63 (+71%)** | ✅ Win |
| Aotc1u2o | $3.44 | $5.57 | **+$2.13 (+62%)** | ✅ Win |
| 8WPerPpf | $4.57 | $0.00 | **-$4.57 (-100%)** | ❌ Ghost (not tradable) |
| ip4ExdPn | $3.24 | $1.01 | **-$2.22 (-69%)** | ❌ Loss |

---

## All-Time Performance

| Metric | Value |
|--------|-------|
| **Total Trades** | 205 |
| **Total Invested** | $1,511.76 |
| **Total Returned** | $1,322.11 |
| **Net P&L** | **-$189.65** |
| **ROI** | **-12.5%** |

---

## Current Configuration

### Exit Strategy
| Setting | Value |
|---------|-------|
| Stop Loss | 30% |
| Trail Tier 0 (0-50% profit) | 25% |
| Trail Tier 1 (50-100% profit) | 20% |
| Trail Tier 2 (100%+ profit) | 18% |

### Profit Taking (ENABLED)
| Tier | Trigger | Action |
|------|---------|--------|
| Tier 1 | +50% profit | Sell 25% |
| Tier 2 | +100% profit | Sell 25% |
| Tier 3 | +200% profit | Sell 25% |
| Tier 4 | +400% profit | Hold (moonshot) |

### Other Settings
| Setting | Value |
|---------|-------|
| Max Concurrent Positions | 5 |
| Scam Detection | OFF |
| Min Hold Time | 120 seconds |
| Ghost Position Threshold | 10 price failures |
| Price Fallback | Dexscreener (for pump.fun) |

---

## Recent Fixes Applied (2026-01-29)

### 1. Profit Taking Bug Fix
- **Issue:** Hardcoded 150% threshold ignored .env settings
- **Fix:** Now uses configured tiers (50%/100%/200%/400%)
- **Impact:** Trades like E41KCE1b (+168%) now captured

### 2. Ghost Position Detection
- **Issue:** Positions closed after just 3 price failures
- **Fix:** Increased to 10 failures + on-chain balance check
- **Impact:** Tokens won't be prematurely closed

### 3. Dexscreener Fallback
- **Issue:** Pump.fun tokens not priced by Jupiter
- **Fix:** Added Dexscreener as fallback price source
- **Impact:** Better tracking of early-stage tokens

### 4. Reconciler Auto-Close Disabled
- **Issue:** Reconciler closing valid positions on startup
- **Fix:** Disabled auto_close_missing
- **Impact:** Positions persist correctly across restarts

---

## Signal Sources

| Source | Status |
|--------|--------|
| @atmpumpfun_bot | ✅ Active |
| @atmogalgo_bot | ✅ Active |
| @atmstreamalgo_bot | ✅ Active |
| @atmogbeta_bot | ✅ Active |

---

## Known Issues

1. **sGGiTvmw position:** Shows in DB but 0 balance on-chain (orphaned)
2. **8WPerPpf trade:** Lost $4.57 because Jupiter couldn't trade it (pump.fun pre-migration)
3. **Health checks:** Some containers show "unhealthy" but function correctly

---

## Recommendations

1. Consider tightening stop loss from 30% to 25%
2. Monitor next 20-30 trades to validate profit-taking improvements
3. Clean up orphaned sGGiTvmw position from database
4. Consider adding pump.fun direct trading support for pre-migration tokens

---

*Last updated: 2026-01-29 15:45 UTC*
