# Comprehensive Token Data - Data Dictionary

## 📊 **EXPORT FILES**

### **1. comprehensive_token_data.csv**
- **Format:** CSV (Comma-Separated Values)
- **Size:** ~770 rows (one per token)
- **Purpose:** Summary data for quick analysis in Excel/Python/R
- **Use Case:** Statistical analysis, outcome prediction, feature correlation

### **2. comprehensive_token_data_complete.json**
- **Format:** JSON (JavaScript Object Notation)
- **Size:** ~770 tokens with complete time series
- **Purpose:** Full historical data with all snapshots
- **Use Case:** Time series analysis, pattern detection, deep learning

---

## 📋 **CSV COLUMNS (Summary Data)**

### **Token Identification**

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `ca` | string | Contract address (Solana token address) | `F3hQ4u4AsNMSXkhWSRFcPkVbEZwGoSJurviLdbcxpump` |
| `first_seen_ts` | datetime | UTC timestamp when first detected | `2025-10-14 08:33:34` |
| `token_name` | string | Token name | `Quantify Trading` |
| `token_symbol` | string | Token symbol/ticker | `QUANT` |

### **Signal Quality**

| Column | Type | Description | Range/Values |
|--------|------|-------------|--------------|
| `final_score` | integer | Final signal score (higher = better) | 0-10 |
| `conviction_type` | string | Alert conviction level | `High Confidence (Smart Money)`, `High Confidence (Strict)`, `Nuanced Conviction` |
| `smart_money_detected` | boolean | Whether smart money was involved | `True`/`False` |

### **Price Time Series (USD)**

| Column | Type | Description | Notes |
|--------|------|-------------|-------|
| `price_t0` | float | Entry price (when alerted) | First price USD |
| `price_t1m` | float | Price after 1 minute | May be NULL if no snapshot |
| `price_t5m` | float | Price after 5 minutes | May be NULL if no snapshot |
| `price_t15m` | float | Price after 15 minutes | May be NULL if no snapshot |
| `price_t1h` | float | Price after 1 hour | May be NULL if no snapshot |
| `price_t24h` | float | Price after 24 hours | May be NULL if no snapshot |
| `peak_price_usd` | float | Highest price reached | Peak during tracking |
| `last_price_usd` | float | Most recent price | Latest snapshot |

### **Performance Metrics**

| Column | Type | Description | Calculation |
|--------|------|-------------|-------------|
| `max_gain_percent` | float | Maximum gain from entry | `(peak_price / price_t0 - 1) * 100` |
| `price_change_1h` | float | Price change in 1 hour (%) | Percentage change |
| `price_change_24h` | float | Price change in 24 hours (%) | Percentage change |
| `outcome_label` | string | Final outcome classification | See below |
| `is_rug` | boolean | Whether token was rugged | `True`/`False` |

**Outcome Labels:**
- `moonshot_10x+`: max_gain_percent >= 1000% (10x or more)
- `winner_2x+`: max_gain_percent >= 100% (2x or more)
- `winner`: max_gain_percent > 0% (any profit)
- `loser`: max_gain_percent <= 0% (loss)
- `unknown`: No performance data

### **Market Data**

| Column | Type | Description | Units |
|--------|------|-------------|-------|
| `first_market_cap_usd` | float | Market cap at entry | USD |
| `peak_market_cap_usd` | float | Highest market cap | USD |
| `last_market_cap_usd` | float | Most recent market cap | USD |
| `first_liquidity_usd` | float | Liquidity at entry | USD |
| `last_liquidity_usd` | float | Most recent liquidity | USD |
| `last_volume_24h_usd` | float | 24h trading volume | USD |
| `holder_count` | integer | Number of token holders | Count |

### **Tracking Statistics**

| Column | Type | Description | Notes |
|--------|------|-------------|-------|
| `snapshot_count` | integer | Number of price snapshots | ~87 average per token |
| `tx_count` | integer | Number of transaction snapshots | Usually 0-1 (limited data) |
| `wallet_count` | integer | Number of wallet first buys | Usually 0-1 (limited data) |

---

## 📦 **JSON STRUCTURE (Complete Data)**

Each token in the JSON file contains:

```json
{
  "ca": "F3hQ4u4AsNMSXkhWSRFcPkVbEZwGoSJurviLdbcxpump",
  "first_seen_ts": "2025-10-14 08:33:34",
  "token_name": "Quantify Trading",
  "token_symbol": "QUANT",
  "final_score": 8,
  "conviction_type": "High Confidence (Smart Money)",
  "smart_money_detected": true,
  
  // All CSV columns included...
  
  // PLUS time series data:
  
  "liquidity_snapshots": [
    {
      "ts": 1728901414.0,
      "liquidity_usd": 23695.72,
      "liquidity_sol": 157.97
    },
    // ... more snapshots every 30 seconds
  ],
  
  "price_snapshots": [
    {
      "ts": 1728901414.0,
      "price_usd": 0.00004026
    },
    // ... more snapshots every 30 seconds
  ],
  
  "holders_count_ts": [
    {
      "ts": 1728901414.0,
      "holders": 45
    },
    // ... more snapshots
  ],
  
  "tx_snapshots": [
    {
      "signature": "2MJLXjCVys56nyBM...",
      "ts": 1728901414.0,
      "from_wallet": "5B52w1ZW9tuwUduueP5J...",
      "to_wallet": "5B52w1ZW9tuwUduueP5J...",
      "amount": null,
      "amount_usd": 2003.08,
      "tx_type": "swap",
      "dex": "PumpSwap",
      "is_smart_money": false
    }
    // NOTE: Usually only 0-1 transactions (initial alert tx)
  ],
  
  "wallet_first_buys": [
    {
      "wallet": "5B52w1ZW9tuwUduueP5J...",
      "ts": 1728901414.0,
      "amount": null,
      "amount_usd": 2003.08,
      "price_usd": 0.00004026,
      "is_smart_money": false
    }
    // NOTE: Usually only 0-1 wallets (initial buyer)
  ]
}
```

---

## 📊 **DATA QUALITY & COMPLETENESS**

### **✅ Fully Tracked (100% Coverage)**

| Data Point | Coverage | Quality |
|------------|----------|---------|
| Contract address | 770/770 (100%) | ✅ Complete |
| First seen timestamp | 770/770 (100%) | ✅ Complete |
| Token metadata | 770/770 (100%) | ✅ Complete |
| Price snapshots | 67,511 total | ✅ Excellent (87 per token avg) |
| Liquidity snapshots | 67,511 total | ✅ Excellent |
| Holder count snapshots | 67,511 total | ✅ Excellent |
| Outcome labels | 770/770 (100%) | ✅ Complete |

### **⚠️ Partially Tracked (Limited Data)**

| Data Point | Coverage | Reason |
|------------|----------|--------|
| Transaction snapshots | 55/770 (7.1%) | Only initial alert tx tracked |
| Wallet first buys | 55/770 (7.1%) | Only initial buyer tracked |
| Price at specific intervals | Varies | Depends on tracking duration |

**Why Limited?**
- Transaction history requires paid APIs (Helius/Birdeye) or complex RPC calls
- Free APIs (DexScreener, Jupiter) don't provide transaction history
- Current system tracks only the initial transaction that triggered the alert

---

## 🎯 **RECOMMENDED ANALYSIS**

### **For Analysts**

1. **Outcome Prediction Model**
   - Features: `final_score`, `conviction_type`, `smart_money_detected`, `first_liquidity_usd`, `first_market_cap_usd`
   - Target: `outcome_label` (winner vs loser)
   - Model: Logistic regression, Random Forest, XGBoost

2. **Time to Peak Analysis**
   - Use `price_snapshots` to calculate time from entry to peak
   - Correlate with `final_score` and `conviction_type`

3. **Liquidity Impact**
   - Analyze `liquidity_snapshots` vs `price_snapshots`
   - Identify liquidity thresholds for success

4. **Smart Money Performance**
   - Compare `smart_money_detected=True` vs `False`
   - Calculate win rates and average gains

### **Key Metrics to Calculate**

```python
# Win rate by score
win_rate_by_score = df.groupby('final_score')['outcome_label'].apply(
    lambda x: (x.isin(['winner', 'winner_2x+', 'moonshot_10x+'])).mean()
)

# Average gain by conviction type
avg_gain_by_conviction = df.groupby('conviction_type')['max_gain_percent'].mean()

# Liquidity threshold analysis
df['high_liquidity'] = df['first_liquidity_usd'] > 30000
win_rate_by_liquidity = df.groupby('high_liquidity')['outcome_label'].apply(
    lambda x: (x.isin(['winner', 'winner_2x+', 'moonshot_10x+'])).mean()
)
```

---

## 📈 **CURRENT DATASET STATISTICS**

```
Total Tokens: 770
Date Range: October 7-14, 2025 (7 days)

Outcome Distribution:
  Winners (any profit): 450 (58.4%)
  Losers: 320 (41.6%)
  2x+ Winners: 112 (14.5%)
  10x+ Moonshots: 11 (1.4%)

Price Snapshots: 67,511 total
  Average per token: 87.5 snapshots
  Frequency: Every 30 seconds
  Average tracking duration: ~44 minutes

Transaction Data: 55 transactions (7.1% coverage)
Wallet Data: 55 wallets (7.1% coverage)

Score Distribution:
  Score 10: Highest quality signals
  Score 8-9: Excellent signals
  Score 6-7: Good signals
  Score 4-5: Marginal signals

Conviction Types:
  High Confidence (Strict): Passed strict filters
  High Confidence (Smart Money): Smart money involved
  Nuanced Conviction: Passed debate/nuanced analysis
```

---

## ⚠️ **DATA LIMITATIONS**

1. **Transaction History**: Only initial alert transaction tracked (not ongoing activity)
2. **Wallet Buyers**: Only first buyer tracked (not first N buyers)
3. **Time Intervals**: May have NULL values if token wasn't tracked long enough
4. **Decimals/Supply**: Not currently tracked (fields would be NULL)
5. **Wallet PnL**: Not currently tracked (would be NULL)

---

## 📁 **FILE LOCATIONS**

- **CSV:** `comprehensive_token_data.csv` (in root directory)
- **JSON:** `comprehensive_token_data_complete.json` (in root directory)
- **Database:** `var/alerted_tokens.db` (SQLite database, 44 MB)

---

## 🔧 **REGENERATING THE EXPORT**

To regenerate with latest data:

```bash
# On server
cd /opt/callsbotonchain/deployment
python3 scripts/export_comprehensive_data.py

# Or locally (after downloading database)
scp root@64.227.157.221:/opt/callsbotonchain/deployment/var/alerted_tokens.db var/
python scripts/export_comprehensive_data.py
```

---

**Generated:** 2025-10-14 15:00 IST  
**Data Version:** v1.0  
**Total Records:** 770 tokens, 67,511 snapshots

