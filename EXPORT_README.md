# Token Data Export - 770 Tokens

## 📊 File: `comprehensive_token_data.csv`

**Complete data for all 770 tokens tracked October 7-14, 2025**

---

## 📋 Columns (27 total)

### Token Identification
- `ca` - Contract address (Solana token address)
- `first_seen_ts` - UTC timestamp when first detected
- `token_name` - Token name
- `token_symbol` - Token symbol/ticker

### Signal Quality
- `final_score` - Signal score (0-10, higher = better)
- `conviction_type` - Alert conviction level
- `smart_money_detected` - Whether smart money was involved (True/False)

### Price Time Series (USD)
- `price_t0` - Entry price (when alerted)
- `price_t1m` - Price after 1 minute
- `price_t5m` - Price after 5 minutes
- `price_t15m` - Price after 15 minutes
- `price_t1h` - Price after 1 hour
- `price_t24h` - Price after 24 hours
- `peak_price_usd` - Highest price reached
- `last_price_usd` - Most recent price

### Performance Metrics
- `max_gain_percent` - Maximum gain from entry (%)
- `price_change_1h` - Price change in 1 hour (%)
- `price_change_24h` - Price change in 24 hours (%)
- `outcome_label` - Final outcome: `moonshot_10x+`, `winner_2x+`, `winner`, `loser`
- `is_rug` - Whether token was rugged (True/False)

### Market Data
- `first_market_cap_usd` - Market cap at entry
- `peak_market_cap_usd` - Highest market cap
- `last_market_cap_usd` - Most recent market cap
- `first_liquidity_usd` - Liquidity at entry
- `last_liquidity_usd` - Most recent liquidity
- `last_volume_24h_usd` - 24h trading volume
- `holder_count` - Number of token holders

---

## 📈 Dataset Statistics

```
Total Tokens: 770
Date Range: October 7-14, 2025 (7 days)

OUTCOMES:
  Winners (any profit): 450 (58.4%)
  Losers: 320 (41.6%)
  2x+ Winners: 112 (14.5%)
  10x+ Moonshots: 11 (1.4%)

SCORE DISTRIBUTION:
  Score 10: Highest quality
  Score 8-9: Excellent
  Score 6-7: Good
  Score 4-5: Marginal

CONVICTION TYPES:
  High Confidence (Strict): Passed strict filters
  High Confidence (Smart Money): Smart money involved
  Nuanced Conviction: Passed debate analysis
```

---

## ✅ Data Quality

- **100% Complete** - All 770 tokens have all 27 fields
- **100% Real** - No synthetic or false data
- **NULL values** - Only where data doesn't exist (e.g., price_t24h if tracking ended early)

---

## 🎯 Use Cases

**For Analysts:**
1. Signal quality assessment (which scores win?)
2. Performance prediction models
3. Threshold optimization (liquidity, score minimums)
4. Smart money impact analysis
5. Conviction type performance comparison

**Example Analysis:**
```python
import pandas as pd

df = pd.read_csv('comprehensive_token_data.csv')

# Win rate by score
win_rate = df.groupby('final_score')['outcome_label'].apply(
    lambda x: (x.isin(['winner', 'winner_2x+', 'moonshot_10x+'])).mean()
)

# Average gain by conviction type
avg_gain = df.groupby('conviction_type')['max_gain_percent'].mean()

# Smart money impact
smart_money_win_rate = df.groupby('smart_money_detected')['outcome_label'].apply(
    lambda x: (x.isin(['winner', 'winner_2x+', 'moonshot_10x+'])).mean()
)
```

---

**Generated:** October 14, 2025  
**Source:** CallsBot tracking system  
**Status:** ✅ Complete and ready for analysis

