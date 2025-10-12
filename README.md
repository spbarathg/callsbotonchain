# CallsBot - Solana Memecoin Signal & Trading System

**Production Status:** ✅ Live and Running  
**Server:** https://callsbotonchain.com  
**Last Updated:** October 12, 2025

---

## What This Is

CallsBot is a sophisticated signal detection and automated trading system for Solana memecoins. It continuously monitors the market (primarily Pump.fun tokens), scores every significant transaction using a multi-factor analysis system, and automatically executes trades on high-quality signals.

The goal is simple: **find and trade only the top 1-2% of tokens** that show genuine momentum, liquidity, and market structure—before they moon.

### The Problem We're Solving

The Solana memecoin market moves fast. By the time you see a token pumping on socials, you're already late. Most tokens are rugs or low-liquidity scams. Even "signal bots" often catch tokens after the pump, leaving you holding bags.

This system is different: it evaluates tokens at the transaction level, filtering through thousands of tokens daily to find the rare few worth trading.

---

## System Architecture

### 1. Signal Bot (Detection Engine)

The signal bot runs continuously, processing real-time transaction data from Cielo Finance's feed API:

**What it does:**
- Scans ~100-200 tokens per minute from Pump.fun and major DEXs
- Performs preliminary scoring on each token (0-10 scale)
- Deep analysis on promising candidates (scores 2+)
- Multi-gate filtering system (liquidity, momentum, holder distribution)
- Anti-FOMO filter to reject late entries (tokens already pumped >30%)

**Scoring System:**
- **0-1:** Instant rejection (low value transactions, obvious scams)
- **2-4:** Detailed analysis triggered, most still fail gates
- **5-7:** High-quality signals, automated trading considered
- **8-10:** Premium signals, highest confidence

**Key Filters:**
- Minimum liquidity: $20,000 (prevents rug pulls)
- Volume/MarketCap ratio: >2% (shows real activity)
- Anti-FOMO: Rejects tokens pumping >30% in 24h
- Holder distribution: Top 10 holders can't control >18%

### 2. Trading Bot (Execution Engine)

The trading bot receives signals from the detection engine and executes trades automatically:

**Features:**
- **Circle Strategy:** Dynamic portfolio rebalancing (max 5 positions)
- **Momentum Ranking:** Always holds the strongest tokens
- **Atomic Swaps:** Sells weak positions to buy stronger signals
- **Risk Management:** Stop-losses, trailing stops, position limits
- **Capital Efficiency:** ~85% utilization vs 60% with static holdings

**How Circle Strategy Works:**

Think of your capital as a fishing net catching fish from a pond:
- **The Pond:** All available tokens in the market
- **The Net:** Continuous signal scanning
- **The Circle:** Fixed portfolio size (5 positions)
- **The Rule:** When you catch a bigger fish, throw back the smallest

This means if you're holding 5 positions and a score-9 signal arrives, the bot will automatically sell your weakest position (e.g., down -5% with low momentum) and buy the new opportunity. Your capital is always allocated to the best opportunities available, not just the first ones you found.

### 3. Performance Tracking

Continuous monitoring system that tracks every alerted token:
- Price tracking every 30 seconds
- Max gain/loss recording
- Win rate analysis by score and strategy
- Performance metrics for system tuning

---

## Current Configuration

As of October 12, 2025, the bot is running with **very aggressive** settings designed to maximize signal flow:

```bash
# Signal Detection
HIGH_CONFIDENCE_SCORE=3          # Very low threshold (catching more signals)
GENERAL_CYCLE_MIN_SCORE=2        # Minimum score to alert
MIN_LIQUIDITY_USD=20000          # $20k minimum (protects from rugs)
VOL_TO_MCAP_RATIO_MIN=0.02       # 2% minimum volume ratio

# Safety Filters (Currently Disabled)
REQUIRE_MINT_REVOKED=false       # Would block 99% of Pump.fun tokens
REQUIRE_LP_LOCKED=false          # Would block most new tokens
REQUIRE_SMART_MONEY_FOR_ALERT=false

# Anti-FOMO Protection
MAX_24H_CHANGE_FOR_ALERT=30%     # Reject tokens already pumped
MAX_1H_CHANGE_FOR_ALERT=200%     # Reject extreme spikes

# Trading System
PORTFOLIO_REBALANCING_ENABLED=true
PORTFOLIO_MAX_POSITIONS=5
PORTFOLIO_MIN_MOMENTUM_ADVANTAGE=15.0
```

**Why these settings?**

Initial analysis of 2,189 signals showed that score-7 tokens had a 20% win rate. However, the market is currently challenging, so we've lowered thresholds to capture more opportunities while maintaining core safety filters (liquidity, anti-FOMO, holder distribution).

---

## Performance Expectations

### Historical Performance (2,189 Signals Analyzed)

From the initial deployment and analysis:
- **Overall Return:** 1.60x total (+60% across all signals)
- **Win Rate:** 11.3% (248 profitable / 2,189 total)
- **Moonshots:** 9 tokens hit 10x+ including 896x and 143x winners
- **Top 10 Signals:** Contributed 88% of all profits
- **Best Score Range:** Score 7 had 20% win rate (highest consistency)

### Current Goals (After System Improvements)

- **Target Win Rate:** 15-20% (up from 11.3%)
- **Average Return:** 2.5-3.5x per winning signal
- **Signal Volume:** 10-30 quality signals per day
- **Rug Protection:** <10% rug rate (via liquidity filter)

### Realistic Growth Path

Starting with $500 capital:
- **Conservative Path:** $500 → $3,000 in 4-7 cycles (3-6 weeks)
- **Aggressive Path:** $500 → $10,000 in 8-12 cycles (6-10 weeks)
- **Ultimate Goal:** $500 → $50,000+ in 10-15 cycles (2-4 months)

**Key assumption:** Not every signal wins, but the winners (especially 10x+ moonshots) far outweigh the losers.

---

## How to Use

### Quick Start (Read-Only Monitoring)

If you just want to see signals without auto-trading:

1. Join the Telegram group (configured in .env)
2. Signals are posted automatically with score, liquidity, and key metrics
3. Manually review and trade on exchanges like Jupiter, Raydium, or Pump.fun

### Full Auto-Trading

For autonomous trading:

1. Fund the treasury wallet (configured in deployment/.env)
2. Ensure `TS_TRADING_ENABLED=true` in .env
3. Set risk limits (`PORTFOLIO_MAX_POSITIONS`, `TS_MAX_POSITION_SIZE_USD`)
4. Monitor via web dashboard: https://callsbotonchain.com

---

## System Components

### Running Services

All services run in Docker containers on the production server:

- **worker:** Main signal detection bot (`scripts/bot.py`)
- **tracker:** Price tracking and performance analysis
- **paper_trader:** Simulated trading for testing strategies
- **web:** Dashboard and API server (port 8080)
- **caddy:** Reverse proxy with SSL (ports 80/443)
- **redis:** Signal distribution and caching

Check status: `docker compose ps` (on server)

### Databases

- **alerted_tokens.db:** Signal history, currently being rebuilt
- **trading.db:** Live trading positions and order history
- **treasury.json:** Capital allocation and risk tracking
- **admin.db:** System configuration and feature flags

### Key Files

- `scripts/bot.py` - Main signal detection loop
- `app/analyze_token.py` - Token scoring logic
- `tradingSystem/trader_optimized.py` - Trade execution
- `tradingSystem/portfolio_manager.py` - Circle Strategy implementation
- `tradingSystem/momentum_ranker.py` - Position ranking system
- `config/config.py` - System configuration

---

## Configuration Guide

### Environment Variables

All settings are in `deployment/.env` on the server:

**Critical Settings:**
```bash
# Cielo API (required for data feed)
CIELO_API_KEY=your_api_key_here

# Telegram Notifications
TELEGRAM_USER_API_ID=21297486
TELEGRAM_USER_API_HASH=your_hash
TELEGRAM_GROUP_CHAT_ID=-1003153567866
TELEGRAM_USER_SESSION_FILE=var/memecoin_session

# Trading Wallet
TREASURY_WALLET_ADDRESS=your_solana_wallet
TREASURY_PRIVATE_KEY=your_private_key
```

**Tuning Settings:**
```bash
# Lower = more signals (but potentially lower quality)
HIGH_CONFIDENCE_SCORE=3
GENERAL_CYCLE_MIN_SCORE=2

# Higher = fewer but safer signals
MIN_LIQUIDITY_USD=20000
VOL_TO_MCAP_RATIO_MIN=0.02

# Position limits
PORTFOLIO_MAX_POSITIONS=5
TS_MAX_POSITION_SIZE_USD=100
```

### Telegram Setup

The bot uses **Telethon** (user account, not bot API) to send messages:

1. Run `python scripts/setup_telethon_session.py`
2. Enter your phone number and verification code
3. Session file saved to `var/memecoin_session.session`
4. Upload to server and restart worker

This allows sending to private groups without bot limitations.

---

## Monitoring & Operations

### Health Check

```bash
# SSH to server
ssh root@64.227.157.221

# Check all services
cd /opt/callsbotonchain/deployment
docker compose ps

# View recent signals
docker logs callsbot-worker --tail 100 | grep "ALERTED"

# Check for rejections
docker logs callsbot-worker --tail 100 | grep "REJECTED"
```

### Key Metrics to Watch

- **Signal Volume:** Should see 10-30 signals per day (currently lower due to aggressive filters)
- **Win Rate:** Target 15-20% (track via `scripts/analyze_performance.py`)
- **System Health:** All containers should show "healthy" status
- **Disk Usage:** Keep under 80% (run `docker system prune` if needed)

### Common Issues

**No Signals Being Generated:**
- Check if filters are too strict (HIGH_CONFIDENCE_SCORE, MIN_LIQUIDITY_USD)
- Verify Cielo API key is valid
- Check worker logs for rejection reasons

**Telegram Not Delivering:**
- Verify Telethon session is authorized
- Check if phone number can access the group
- Restart worker container

**Trading Not Executing:**
- Check if `TS_TRADING_ENABLED=true`
- Verify treasury wallet has SOL balance
- Check for errors in worker logs

---

## Development

### Local Setup

```bash
# Clone repository
git clone <repo-url>
cd callsbotonchain

# Install dependencies
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Copy and configure .env
cp .env.example .env
# Edit .env with your API keys

# Run in dry-run mode (no real trades)
TS_DRY_RUN=true python scripts/bot.py
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test suites
pytest tests/test_analyze_token.py
pytest tests/test_portfolio_manager.py
pytest tests/test_circle_strategy_integration.py

# Run with coverage
pytest --cov=app --cov=tradingSystem
```

### Deployment

```bash
# On server
cd /opt/callsbotonchain/deployment

# Pull latest code
git pull origin main

# Rebuild and restart
docker compose build worker
docker compose up -d

# Verify
docker compose ps
docker logs -f callsbot-worker
```

---

## Documentation

Comprehensive documentation is in the `docs/` directory:

- **[Getting Started](docs/quickstart/GETTING_STARTED.md)** - Initial setup guide
- **[Circle Strategy](docs/trading/CIRCLE_STRATEGY.md)** - Portfolio rebalancing explained
- **[Configuration Guide](docs/configuration/BOT_CONFIGURATION.md)** - All settings explained
- **[Troubleshooting](docs/operations/TROUBLESHOOTING.md)** - Common issues and fixes
- **[Deployment Guide](docs/deployment/QUICK_REFERENCE.md)** - Server deployment
- **[Monitoring System](docs/monitoring/MONITORING_SYSTEM.md)** - Health checks and metrics

---

## Architecture Decisions

### Why Pump.fun Focus?

Pump.fun is where memecoins are born on Solana. By monitoring new token launches at the transaction level, we can catch momentum before it hits social media. Traditional signal bots rely on price action or social metrics—we start earlier.

### Why Multi-Gate Filtering?

Early analysis showed that single-factor scoring (price, volume, smart money) wasn't predictive. A multi-factor system with independent gates (liquidity, momentum, holder distribution, anti-FOMO) provides better risk/reward.

### Why Circle Strategy?

Static portfolio management means your capital gets stuck in stale positions. Circle Strategy ensures you're always holding your best 5 opportunities, maximizing capital efficiency and reducing opportunity cost.

### Why Not More Positions?

Testing showed 5 positions is optimal for a $500 starting bankroll:
- Too few (3): Misses diversification
- Too many (7+): Dilutes capital, reduces per-position size
- Just right (5): Balanced risk/reward, manageable monitoring

---

## Current Status

As of **October 12, 2025, 11:00 PM IST**:

- **System:** ✅ All services healthy and running
- **Worker:** Processing ~2,000 tokens/hour
- **Signals:** Currently very selective (aggressive filters active)
- **Trading:** Paper trading active, live trading ready
- **Database:** Being rebuilt after schema changes
- **Performance Data:** Collecting fresh data with current configuration

**Recent Changes:**
- Lowered HIGH_CONFIDENCE_SCORE from 7 to 3 (more signals)
- Lowered GENERAL_CYCLE_MIN_SCORE from 4 to 2
- Disabled REQUIRE_MINT_REVOKED and REQUIRE_LP_LOCKED
- Fixed Telethon session for Telegram delivery
- Deployed Circle Strategy with portfolio rebalancing

**Next Steps:**
- Monitor signal quality over 24-48 hours
- Analyze win rate and adjust thresholds if needed
- Tune momentum ranking parameters
- Consider raising liquidity threshold to $30k (historical optimal)

---

## Philosophy

This bot is designed around one core principle: **quality over quantity**.

Most signal bots spam 100+ tokens per day, hoping a few hit. That's noise, not signal. This system is intentionally selective—scoring every transaction but alerting only when multiple independent factors align.

The goal isn't to catch every pump. It's to catch the *right* pumps early enough to profit, with enough safety filters that rugs are rare.

Will every signal win? No. But historically, the winners (especially the 10x+ moonshots) generate enough profit to cover all losses and then some. That's the edge.

---

## License & Disclaimer

**Disclaimer:** This is experimental software for educational purposes. Cryptocurrency trading carries significant risk. Only use capital you can afford to lose. Past performance does not guarantee future results.

**Status:** Active development and production use.

**Contact:** [Your contact info or Telegram]

---

Built with Python, Solana, and an obsessive attention to signal quality.

