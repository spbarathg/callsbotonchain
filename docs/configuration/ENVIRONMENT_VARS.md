# Environment Variables Reference

**Complete guide to all configuration options in `.env` file.**

---

## 🔴 Critical Settings (Must Configure)

### Security & Access
```bash
# Telegram notifications
TELEGRAM_BOT_TOKEN=your_token          # Required for alerts
TELEGRAM_CHAT_ID=your_chat_id          # Required for alerts

# API Access
CIELO_API_KEY=your_key                 # Required for token data
```

---

## ⚙️ Bot Behavior Settings

### Score & Filtering
```bash
# Score thresholds
HIGH_CONFIDENCE_SCORE=7                # Min score to alert (1-10)
GENERAL_CYCLE_MIN_SCORE=7              # Min score for non-smart-money signals

# Smart money
SMART_MONEY_SCORE_BONUS=0              # Bonus points for smart money (0 recommended)
REQUIRE_SMART_MONEY_FOR_ALERT=false    # Only alert on smart money signals
```

**Recommended Values:**
- `HIGH_CONFIDENCE_SCORE=7` (based on 2,189 signal analysis)
- `GENERAL_CYCLE_MIN_SCORE=7` (score 7 = 20% win rate historically)
- `SMART_MONEY_SCORE_BONUS=0` (non-predictive per analysis)

---

### Liquidity & Volume Filters
```bash
# Liquidity requirements
MIN_LIQUIDITY_USD=30000                # Minimum liquidity in USD
RUG_MIN_LIQUIDITY_USD=1                # Threshold for rug detection

# Volume requirements
VOL_24H_MIN_FOR_ALERT=0                # Minimum 24h volume (0 = disabled)
VOL_TO_MCAP_RATIO_MIN=0.40             # Min volume/marketcap ratio
VOL_VERY_HIGH=60000                    # Threshold for "very high" volume
VOL_HIGH=30000                         # Threshold for "high" volume
VOL_MED=5000                           # Threshold for "medium" volume
```

**Recommended Values:**
- `MIN_LIQUIDITY_USD=30000` (moonshots had $117k median)
- `VOL_TO_MCAP_RATIO_MIN=0.40` (quality filter)
- Volume thresholds based on October 2025 market analysis

---

### Market Cap Filters
```bash
# Market cap limits
MAX_MARKET_CAP_FOR_DEFAULT_ALERT=750000    # Max mcap for auto-alert
MCAP_MICRO_MAX=50000                       # Micro cap threshold
MCAP_SMALL_MAX=500000                      # Small cap threshold
MCAP_MID_MAX=5000000                       # Mid cap threshold
MICROCAP_SWEET_MIN=10000                   # Microcap sweet spot min
MICROCAP_SWEET_MAX=100000                  # Microcap sweet spot max
```

---

### Security Requirements ⚠️ CRITICAL
```bash
# Token security checks
REQUIRE_MINT_REVOKED=false             # ⚠️ MUST BE FALSE for pump.fun tokens
REQUIRE_LP_LOCKED=false                # ⚠️ MUST BE FALSE for new tokens
ALLOW_UNKNOWN_SECURITY=true            # Allow tokens with unknown security

# Holder requirements
REQUIRE_HOLDER_STATS_FOR_LARGE_CAP_ALERT=false
MAX_TOP10_CONCENTRATION=90             # Max % held by top 10 wallets
MAX_BUNDLERS_PERCENT=50                # Max % held by bundlers
MAX_INSIDERS_PERCENT=50                # Max % held by insiders
```

**⚠️ IMPORTANT:**
- `REQUIRE_MINT_REVOKED=false` - Setting to `true` blocks 99% of pump.fun tokens
- `REQUIRE_LP_LOCKED=false` - Setting to `true` blocks most new tokens
- These should ONLY be `true` if you specifically want ultra-conservative filtering

---

### Momentum & Timing
```bash
# Momentum gates
MOMENTUM_1H_STRONG=15                  # Strong momentum threshold (%)
MOMENTUM_1H_PUMPER=30                  # Pumper momentum threshold (%)
LARGE_CAP_MOMENTUM_GATE_1H=18          # Large cap momentum requirement
DRAW_24H_MAJOR=-30                     # Major drawdown threshold

# Multi-signal requirements
REQUIRE_MULTI_SIGNAL=true              # Require multiple signal confirmations
MULTI_SIGNAL_WINDOW_SEC=300            # Time window for multi-signal (5min)
MULTI_SIGNAL_MIN_COUNT=2               # Minimum signals required
MIN_TOKEN_AGE_MINUTES=0                # Minimum token age before alerting
```

---

## 🎛️ System Settings

### Performance & Monitoring
```bash
# Logging
CALLSBOT_LOG_STDOUT=true               # Log to stdout
CALLSBOT_METRICS_ENABLED=true          # Enable Prometheus metrics
CALLSBOT_METRICS_PORT=9108             # Metrics port

# Intervals
FETCH_INTERVAL=60                      # Seconds between feed checks
TRACK_INTERVAL_MIN=30                  # Seconds between price tracking
TELEGRAM_ALERT_MIN_INTERVAL=5          # Min seconds between alerts

# Budgets & Limits
CIELO_DAILY_BUDGET=1000                # Max Cielo API calls per day
CALLSBOT_FORCE_FALLBACK=false          # Force DexScreener fallback
```

---

### Database & Storage
```bash
# Database paths
ALERTED_TOKENS_DB=var/alerted_tokens.db
ADMIN_DB_PATH=var/admin.db
TRADING_DB_PATH=var/trading.db

# Cache settings
STATS_TTL_SEC=900                      # Stats cache TTL (15 minutes)
```

---

## 🎨 Gate Modes (Presets)

```bash
GATE_MODE=CUSTOM                       # Use custom settings below
```

**Available Modes:**
- `STRICT` - High confidence, conservative
- `MODERATE` - Balanced approach
- `RELAXED` - More signals, lower quality
- `CUSTOM` - Use individual settings

When `GATE_MODE=CUSTOM`, individual settings take precedence.

---

## 📊 Current Optimal Configuration (Oct 6, 2025)

Based on analysis of 2,189 signals:

```bash
# Gate Mode
GATE_MODE=CUSTOM

# Score Settings
HIGH_CONFIDENCE_SCORE=7
GENERAL_CYCLE_MIN_SCORE=7
SMART_MONEY_SCORE_BONUS=0

# Security (CRITICAL)
REQUIRE_MINT_REVOKED=false
REQUIRE_LP_LOCKED=false

# Liquidity & Volume
MIN_LIQUIDITY_USD=30000
VOL_TO_MCAP_RATIO_MIN=0.40
VOL_VERY_HIGH=60000
VOL_HIGH=30000
VOL_MED=5000

# Market Cap
MAX_MARKET_CAP_FOR_DEFAULT_ALERT=750000

# Smart Money
REQUIRE_SMART_MONEY_FOR_ALERT=false
```

**Performance Targets:**
- Win Rate: 15-20%
- Avg Multiplier: 2.5-3.5x
- Rug Rate: <10%

---

## 🔄 Changing Configuration

### Update .env
```bash
# Edit file
nano /opt/callsbotonchain/.env

# Restart worker to apply
docker compose restart worker
```

### Verify Changes
```bash
# Check loaded configuration
docker logs callsbot-worker | grep "gates"
```

---

## ⚠️ Common Mistakes

1. **Setting `REQUIRE_MINT_REVOKED=true`**
   - Blocks 99% of tokens
   - Only use if you want ultra-conservative filtering

2. **Setting `REQUIRE_LP_LOCKED=true`**
   - Blocks most new tokens
   - Only use for established tokens

3. **Score too high (>8)**
   - Analysis shows score 7 is optimal
   - Higher scores don't improve win rate

4. **Liquidity too low (<30k)**
   - Allows rugs through
   - Moonshots had $117k median liquidity

5. **Not restarting worker after changes**
   - Changes don't apply until restart
   - Always: `docker compose restart worker`

---

## 📚 Related Documentation

- [BOT_CONFIGURATION.md](./BOT_CONFIGURATION.md) - Detailed config guide
- [SERVER_RULES.md](./SERVER_RULES.md) - Deployment best practices
- [CURRENT_SETUP.md](../quickstart/CURRENT_SETUP.md) - Current state

---

**Last Updated:** October 6, 2025  
**Configuration Version:** v2.0 (Optimized)

