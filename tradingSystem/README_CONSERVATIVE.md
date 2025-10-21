# Conservative Paper Trading System

## Overview

This trading system implements the **CAPITAL_MANAGEMENT_STRATEGY.md** principles with:

- ✅ **Risk-Tier Based Position Sizing** (5-12% per trade)
- ✅ **50% Cash Reserve Enforcement** (never deploy more than 50%)
- ✅ **Daily/Weekly Loss Limits** (-10% daily, -20% weekly with auto-stop)
- ✅ **Recovery Mode** (reduce positions by 50% after 3 consecutive losses)
- ✅ **Realistic Simulation** (slippage, fees, latency)

---

## Quick Start

### 1. Run the CLI

```bash
cd tradingSystem
python cli_conservative.py
```

### 2. View Configuration

```
> config
```

Shows:
- Position sizing for each tier
- Stop loss and trailing stop percentages
- Circuit breaker limits
- Current bankroll

### 3. View Portfolio Status

```
> status
```

Shows:
- Capital overview (current, deployed, reserve)
- Performance (trades, win rate, P&L)
- Risk management (circuit breaker status, recovery mode)
- Open positions with unrealized P&L

---

## How It Works

### Risk Tier Classification

Every signal is automatically classified into one of 3 risk tiers based on:
- Market cap
- Liquidity (optional)
- Score
- Volume
- Conviction type

**Tier 1: MOONSHOT** ($10k-$50k MCap)
- Position Size: 5-8% (default 7%)
- Stop Loss: -70%
- Trailing Stop: -50%
- Target: 5x-100x+
- Strategy: Small bet, BIG potential

**Tier 2: AGGRESSIVE** ($50k-$150k MCap)
- Position Size: 8-12% (default 10%)
- Stop Loss: -50%
- Trailing Stop: -35%
- Target: 2x-20x
- Strategy: Bread and butter

**Tier 3: CALCULATED** ($150k-$500k MCap)
- Position Size: 5-8% (default 6%)
- Stop Loss: -40%
- Trailing Stop: -25%
- Target: 2x-5x
- Strategy: Quick flips

### Position Sizing Example

Starting capital: $1,000

**Tier 1 (Moonshot):**
- Position: $70 (7%)
- Max loss if stopped: -$49 (4.9% of capital)
- Potential gain at 50x: +$3,430 (343% of capital)

**Tier 2 (Aggressive):**
- Position: $100 (10%)
- Max loss if stopped: -$50 (5% of capital)
- Potential gain at 10x: +$900 (90% of capital)

**Tier 3 (Calculated):**
- Position: $60 (6%)
- Max loss if stopped: -$24 (2.4% of capital)
- Potential gain at 3x: +$120 (12% of capital)

### Capital Preservation

**Maximum Deployment: 50%**
- At $1,000: Max $500 deployed, $500 cash reserve
- System enforces this STRICTLY

**Example Portfolio:**
```
Cash Reserve:   $550 (55%)  ✅
Position 1:     $70  (Tier 1)
Position 2:     $100 (Tier 2)
Position 3:     $100 (Tier 2)
Position 4:     $60  (Tier 3)
Position 5:     $60  (Tier 3)
──────────────────────────
Total Deployed: $390 (39%)  ✅ Under 50% limit
```

### Circuit Breakers

**Daily Loss Limit: -10%**
- At $1,000 capital: -$100 max loss per day
- Breaker trips → STOP trading for the day
- Resets at midnight

**Weekly Loss Limit: -20%**
- At $1,000 capital: -$200 max loss per week
- Breaker trips → STOP trading for the week
- Resets on Monday

**Consecutive Losses: 3**
- After 3 losses in a row → Enter recovery mode
- Recovery mode: Reduce position sizes by 50%
- Exit recovery mode on next win

### Example Circuit Breaker Flow

```
Day 1:
- Trade 1: -$50 (5% loss)
- Trade 2: -$40 (4% loss)
- Daily P&L: -$90 (still under -$100 limit)
- Status: ⚠️ Warning (near limit)

Trade 3: -$20 (2% loss)
- Daily P&L: -$110
- Status: 🚨 CIRCUIT BREAKER TRIPPED!
- Action: NO MORE TRADES TODAY

Day 2:
- Daily counter resets
- Can trade again (but recovery mode active)
- Position sizes reduced by 50%
```

---

## Integration with Bot

The paper trading system can integrate with your live bot's signals:

### Manual Mode (Current)

```python
from tradingSystem.paper_trader_conservative import ConservativePaperTrader

trader = ConservativePaperTrader(starting_capital=1000)

# When your bot generates a signal
signal_data = {
    'token_address': 'ABC123...',
    'price': 0.00001,
    'first_market_cap_usd': 75000,
    'liquidity_usd': 35000,
    'volume_24h_usd': 50000,
    'final_score': 8,
    'conviction_type': 'High Confidence'
}

# Open position
pos_id = trader.open_position('ABC123...', signal_data)

# Later, update price
trader.update_and_check_exits('ABC123...', 0.00002)  # 2x gain

# Get stats
stats = trader.get_stats()
print(f"Win Rate: {stats['win_rate']:.1f}%")
print(f"Total P&L: ${stats['total_pnl']:,.2f}")
```

### Automatic Mode (Future)

Connect to your bot's signal feed and automatically paper trade every signal:

```python
# In your bot's signal_processor.py
from tradingSystem.paper_trader_conservative import ConservativePaperTrader

paper_trader = ConservativePaperTrader(starting_capital=1000)

# After sending Telegram alert
if telegram_ok:
    # Paper trade the signal
    signal_data = {
        'token_address': token_address,
        'price': current_price,
        'first_market_cap_usd': mcap,
        'liquidity_usd': liquidity,
        'volume_24h_usd': volume_24h,
        'final_score': final_score,
        'conviction_type': conviction_type
    }
    paper_trader.open_position(token_address, signal_data)
```

---

## Files

- **`config_conservative.py`**: Configuration with conservative parameters
- **`paper_trader_conservative.py`**: Core trading engine
- **`cli_conservative.py`**: Interactive CLI for testing
- **Database**: `var/paper_trading_conservative.db`
- **Logs**: `data/logs/paper_trading_conservative.jsonl`

---

## Expected Performance

Based on CAPITAL_MANAGEMENT_STRATEGY.md projections:

### Month 1 ($1,000 starting)

**Conservative (25% WR):**
- Expected: $3,500-$4,500 (250-350% gain)
- Probability: HIGH

**Target (30% WR):**
- Expected: $7,000-$10,000 (600-900% gain)
- Probability: ACHIEVABLE

**Best Case (35% WR + moonshots):**
- Expected: $18,000-$30,000 (1,700-2,900% gain)
- Probability: POSSIBLE

### Why This Works

**The Math:**
```
33 trades, $70 avg position, 25% win rate:

Losses:  25 × $70 × -45% avg = -$788
Winners:  6 × $70 × 5x        = +$2,100
Moonshots: 2 × $70 × 30x      = +$4,200
────────────────────────────────────
Net Profit: $5,512 (551% ROI!)
```

**Key Insight:**
- ONE moonshot at 50x ($70 → $3,500) covers 22 full stop losses
- You only need 1-2 moonshots per month to be massively profitable
- Small positions = capital preservation + moonshot capture

---

## Safety Features

1. **Never Exceeds 50% Deployment**
   - System enforces maximum 50% capital deployed
   - Always keeps 50% cash reserve

2. **Daily/Weekly Loss Limits**
   - Auto-stops trading at -10% daily
   - Auto-stops trading at -20% weekly
   - Prevents catastrophic drawdowns

3. **Recovery Mode**
   - Activates after 3 consecutive losses
   - Reduces position sizes by 50%
   - Exits on next win

4. **Position Size Caps**
   - Absolute maximum: 12% per trade
   - Tier-specific limits enforced
   - Prevents overexposure

5. **Realistic Simulation**
   - Includes swap fees (0.25%)
   - Simulates slippage (0.5-4% based on liquidity)
   - Simulates execution latency (1-3 seconds)

---

## Monitoring

### View Statistics

```bash
cd tradingSystem
python cli_conservative.py
> status
```

### Query Database

```bash
sqlite3 var/paper_trading_conservative.db

-- View all closed trades
SELECT * FROM paper_positions WHERE status='closed';

-- Calculate win rate
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as wins,
    ROUND(SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as win_rate
FROM paper_positions 
WHERE status='closed';

-- View portfolio snapshots
SELECT * FROM portfolio_snapshots ORDER BY timestamp DESC LIMIT 10;
```

### View Logs

```bash
tail -f data/logs/paper_trading_conservative.jsonl | jq
```

---

## Next Steps

1. **Test the CLI**: Run `python cli_conservative.py` and familiarize yourself with the interface
2. **Review Config**: Run `config` command to see all parameters
3. **Simulate Trades**: Use the `open` command to test position sizing
4. **Integrate with Bot**: Connect to your live signal feed for automatic paper trading
5. **Monitor Performance**: Track win rate, P&L, and circuit breaker status
6. **Adjust if Needed**: Tune position sizes and limits based on results

---

## Questions?

See:
- `CAPITAL_MANAGEMENT_STRATEGY.md` - Full trading strategy
- `TRADING_QUICK_REFERENCE.txt` - Quick reference card
- `STATUS.md` - Current bot status and verification

**The system is READY to use and implements ALL the conservative capital management principles!** 🛡️🚀










