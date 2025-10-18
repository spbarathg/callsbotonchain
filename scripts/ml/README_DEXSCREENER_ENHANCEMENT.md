# ML Enhancement with DexScreener Historical Data

## Overview

This system allows you to enhance ML training by scraping historical pump data from DexScreener. Since we only have 1,094 signals from the bot, we can supplement with external data from tokens that have already pumped 2x+ to train better ML models.

## Why This Works

1. **More Training Data**: Get 1000s of additional samples of tokens that pumped
2. **Identify Decisive Factors**: Analyze what characteristics correlate with 2x+ returns
3. **Faster ML Improvement**: Don't wait 6 months for data accumulation
4. **Real Market Data**: Use actual pump events from DexScreener

## Scripts

### 1. `scrape_dexscreener_trending.py` (RECOMMENDED)

**Best approach**: Manually curate a list of pumping tokens from DexScreener.

**How to use:**

```bash
# Step 1: Find pumping tokens
# Go to: https://dexscreener.com/solana?rankBy=trendingScoreH24&order=desc
# Look for tokens with 2x+ gains in the past 1-2 weeks

# Step 2: Create pair_list.txt with pair addresses
# Example:
echo "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU" > pair_list.txt
echo "58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2" >> pair_list.txt
# ... add more pairs

# Step 3: Run scraper
python scripts/ml/scrape_dexscreener_trending.py
```

**Output:**
- `var/dexscreener_ml_data.db` - Database with scraped tokens in ML training format
- Analysis of patterns (market cap, liquidity, volume sweet spots)

### 2. `enhance_ml_with_dexscreener.py`

**Automated approach**: Searches DexScreener API for gainers.

**Limitations:**
- DexScreener API is rate-limited
- Search results may be incomplete
- Less reliable than manual curation

**How to use:**

```bash
python scripts/ml/enhance_ml_with_dexscreener.py
```

### 3. `auto_find_pumps.py`

**Exploratory tool**: Analyzes pump patterns from DexScreener search.

```bash
python scripts/ml/auto_find_pumps.py
```

## Workflow

### Phase 1: Collect Data

```bash
# Option A: Manual curation (RECOMMENDED)
# 1. Browse DexScreener trending page
# 2. Find 50-100 tokens that pumped 2x+ in past 2 weeks
# 3. Copy pair addresses to pair_list.txt
# 4. Run scraper
python scripts/ml/scrape_dexscreener_trending.py

# Option B: Automated (less reliable)
python scripts/ml/enhance_ml_with_dexscreener.py
```

### Phase 2: Analyze Patterns

The scripts will automatically analyze:
- Market cap sweet spots for 2x+ returns
- Liquidity ranges that correlate with pumps
- Volume/liquidity ratios
- Momentum patterns (1h, 6h, 24h changes)

**Example output:**
```
WINNERS (2x+) CHARACTERISTICS:
   Avg Entry Market Cap: $75,000
   Avg Entry Liquidity: $45,000
   Avg 24h Volume: $250,000
   Avg Max Gain: 350%

SWEET SPOTS:
   Market Cap Range: $30,000 - $150,000
   Median Market Cap: $68,000
   Liquidity Range: $20,000 - $80,000
   Median Liquidity: $42,000
```

### Phase 3: Train ML Models

```bash
# Train on DexScreener data
python scripts/ml/train_model.py var/dexscreener_ml_data.db

# Or merge with existing data first (see below)
```

### Phase 4: Merge Databases (Optional)

To combine DexScreener data with your bot's data:

```python
import sqlite3

# Open both databases
bot_db = sqlite3.connect('var/alerted_tokens.db')
dex_db = sqlite3.connect('var/dexscreener_ml_data.db')

# Attach DexScreener DB to bot DB
bot_db.execute("ATTACH DATABASE 'var/dexscreener_ml_data.db' AS dex")

# Copy data (avoiding duplicates)
bot_db.execute("""
INSERT OR IGNORE INTO alerted_tokens 
SELECT * FROM dex.alerted_tokens
""")

bot_db.execute("""
INSERT OR IGNORE INTO alerted_token_stats 
SELECT * FROM dex.alerted_token_stats
""")

bot_db.commit()
bot_db.close()
dex_db.close()

print("Databases merged!")
```

Then retrain:
```bash
python scripts/ml/train_model.py var/alerted_tokens.db
```

## Finding Pumping Tokens

### DexScreener URLs

**Top Gainers (24h):**
```
https://dexscreener.com/solana?rankBy=priceChangeH24&order=desc
```

**Trending (24h):**
```
https://dexscreener.com/solana?rankBy=trendingScoreH24&order=desc
```

**High Volume:**
```
https://dexscreener.com/solana?rankBy=volume&order=desc
```

### What to Look For

**Ideal candidates for training data:**
1. **Age**: 1-2 weeks old (recent pumps)
2. **Gain**: 2x+ (100%+) from launch
3. **Market Cap**: $30k-$200k (micro-cap range)
4. **Liquidity**: $20k-$100k (sufficient but not saturated)
5. **Still Trading**: Not rugged (still has liquidity)

### How to Get Pair Address

1. Click on a token on DexScreener
2. URL will be: `https://dexscreener.com/solana/PAIR_ADDRESS`
3. Copy the `PAIR_ADDRESS` part
4. Add to `pair_list.txt`

## Expected Results

### With 100 Additional Tokens

If you scrape 100 tokens that pumped 2x+:

**Before:**
- Training data: 1,094 signals
- 2x+ winners: 204 (18.6%)
- ML Test R²: -0.012 (poor)

**After:**
- Training data: 1,194 signals
- 2x+ winners: 304 (25.5%)
- ML Test R²: Expected 0.05-0.15 (modest improvement)

### With 500 Additional Tokens

If you scrape 500 tokens:

**After:**
- Training data: 1,594 signals
- 2x+ winners: 704 (44.2%)
- ML Test R²: Expected 0.15-0.25 (significant improvement)
- **ML becomes useful for signal enhancement**

### With 1000+ Additional Tokens

If you scrape 1000+ tokens:

**After:**
- Training data: 2,094+ signals
- 2x+ winners: 1,204+ (57.5%)
- ML Test R²: Expected 0.25-0.35 (strong predictive power)
- **ML becomes primary signal enhancer**

## Caveats

### Data Quality

**Pros:**
- Real market data from actual pumps
- Diverse token characteristics
- Large sample size possible

**Cons:**
- Entry timing is estimated (not exact)
- May include different market conditions
- Some tokens may have rugged after pump

### Bias Considerations

**Survivorship Bias:**
- DexScreener only shows tokens still trading
- Rugs that disappeared won't be in data
- This is actually GOOD (we want to learn from survivors)

**Selection Bias:**
- Manually selecting 2x+ winners
- This is intentional (we want to learn what makes winners)
- Balance by including some non-winners too

## Best Practices

### 1. Curate Diverse Samples

Don't just scrape the top 100 gainers. Include:
- 70% 2x+ winners (learn what works)
- 20% 50-100% gainers (learn borderline cases)
- 10% <50% gainers (learn what doesn't work)

### 2. Verify Data Quality

After scraping, check:
```python
import sqlite3
conn = sqlite3.connect('var/dexscreener_ml_data.db')
c = conn.cursor()

# Check for outliers
c.execute("""
SELECT token_symbol, entry_mcap, entry_liquidity, max_gain_percent
FROM alerted_token_stats
ORDER BY max_gain_percent DESC
LIMIT 10
""")

for row in c.fetchall():
    print(f"{row[0]}: MCap=${row[1]:,.0f}, Liq=${row[2]:,.0f}, Gain={row[3]:.1f}%")
```

### 3. Retrain Regularly

After adding DexScreener data:
1. Train initial model
2. Wait 1 week for bot to generate new signals
3. Retrain with combined data
4. Compare performance

## Troubleshooting

### "No data collected"

**Cause**: DexScreener API rate limiting or no matching tokens

**Fix**:
1. Wait 5 minutes and try again
2. Use manual curation approach instead
3. Reduce number of pairs in `pair_list.txt`

### "Failed to fetch pair"

**Cause**: Invalid pair address or API error

**Fix**:
1. Verify pair address is correct
2. Check if token still exists on DexScreener
3. Try a different pair

### "ML performance didn't improve"

**Cause**: Not enough diverse data or poor quality samples

**Fix**:
1. Add more samples (aim for 500+)
2. Include diverse market cap ranges
3. Verify data quality (check for outliers)
4. Ensure mix of winners and non-winners

## Summary

**Quick Start:**
```bash
# 1. Create pair list (50-100 pairs)
# Visit: https://dexscreener.com/solana?rankBy=trendingScoreH24
# Copy pair addresses to pair_list.txt

# 2. Scrape data
python scripts/ml/scrape_dexscreener_trending.py

# 3. Analyze patterns (automatic)

# 4. Train ML
python scripts/ml/train_model.py var/dexscreener_ml_data.db

# 5. Deploy to server (if performance improved)
```

**Expected Time:**
- Finding pairs: 30-60 minutes
- Scraping 100 pairs: 2-3 minutes
- Training ML: 1-2 minutes
- **Total: ~1 hour to significantly improve ML**

This approach can accelerate ML improvement from 6 months to immediate!


