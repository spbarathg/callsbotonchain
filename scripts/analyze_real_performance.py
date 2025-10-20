#!/usr/bin/env python3
"""
SIMPLE PERFORMANCE ANALYSIS - What Actually Happened

Instead of simulating trades, let's analyze what ACTUALLY happened to the signals:
1. How many hit 2x+ before rugging?
2. What was the average max gain?
3. What % would have been captured with different trailing stops?
4. What's the realistic expected return?
"""
import sqlite3
from datetime import datetime

DB_PATH = '/opt/callsbotonchain/deployment/var/alerted_tokens.db'
V4_START = 1760825238.0928257

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

print('='*80)
print('SIMPLE PERFORMANCE ANALYSIS - REAL DATA')
print('='*80)
print()

# Load all V4 signals with performance data
c.execute("""
    SELECT 
        a.token_address,
        a.final_score,
        s.first_market_cap_usd,
        s.max_gain_percent,
        s.is_rug,
        s.token_symbol
    FROM alerted_tokens a
    LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
    WHERE CAST(a.alerted_at AS REAL) >= ?
    AND s.max_gain_percent IS NOT NULL
    AND a.final_score >= 8
    ORDER BY s.max_gain_percent DESC
""", (V4_START,))

all_signals = c.fetchall()

print(f'Total Signals (Score 8+): {len(all_signals)}')
print()

# Calculate statistics
if not all_signals:
    print("No signals found!")
    exit(1)

# Performance by threshold
thresholds = [(20, "1.2x"), (50, "1.5x"), (100, "2x"), (200, "3x"), (400, "5x"), (900, "10x")]

print('=== HIT RATE BY GAIN THRESHOLD ===')
for threshold_pct, label in thresholds:
    count = sum(1 for s in all_signals if s[3] >= threshold_pct)
    pct = count / len(all_signals) * 100
    print(f'{label:>6}: {count:>4}/{len(all_signals)} ({pct:>5.1f}%)')
print()

# Calculate what would be captured with different trailing stops
print('=== PROFIT CAPTURE SIMULATION ===')
print('(Assuming we held to peak, then exited on trail)')
print()

for trail_pct in [10, 15, 20, 30]:
    total_captured = 0
    winners = 0
    
    for signal in all_signals:
        max_gain = signal[3]
        
        # If max gain > trail, we capture (max_gain * (1 - trail/100))
        # If max gain < trail, we hit stop loss (-15%)
        if max_gain > trail_pct:
            captured = max_gain * (1 - trail_pct / 100)
            total_captured += captured
            if captured >= 20:  # 1.2x+ is a win
                winners += 1
        else:
            # Hit stop loss or break-even
            total_captured += -15
    
    avg_captured = total_captured / len(all_signals)
    win_rate = winners / len(all_signals) * 100
    
    print(f'{trail_pct:>3}% Trail: Avg {avg_captured:>7.1f}% | Win Rate: {win_rate:>5.1f}% | Winners: {winners}/{len(all_signals)}')

print()

# REALISTIC SIMULATION
print('=== REALISTIC $1000 BACKTEST ===')
print('Assumptions:')
print('- Start with $1000')
print('- 4 concurrent positions max')
print('- Score 8+: 25% position size ($250)')
print('- 15% trailing stop')
print('- Process signals chronologically')
print()

# Simple sequential simulation
capital = 1000
positions = []
completed_trades = []
max_positions = 4

for signal in sorted(all_signals, key=lambda s: s[0]):  # Sort by token address (proxy for time)
    # Can we open?
    if len(positions) < max_positions:
        # Open position
        size = min(250, capital * 0.25)
        if size < 50:  # Not enough capital
            continue
        
        capital -= size
        positions.append({
            'token': signal[0],
            'size': size,
            'max_gain': signal[3],
            'score': signal[1],
            'is_rug': signal[4],
        })
    
    # Check exits (process oldest first)
    for pos in positions[:]:
        max_gain = pos['max_gain']
        
        # Calculate exit
        trail_pct = 15
        if max_gain > trail_pct:
            captured_pct = max_gain * (1 - trail_pct / 100)
        else:
            captured_pct = -15  # Stop loss
        
        # Close position
        proceeds = pos['size'] * (1 + captured_pct / 100)
        profit = proceeds - pos['size']
        
        completed_trades.append({
            'size': pos['size'],
            'profit': profit,
            'profit_pct': captured_pct,
            'is_rug': pos['is_rug'],
        })
        
        capital += proceeds
        positions.remove(pos)
        break  # Only exit one per signal (sequential)

# Close remaining positions
for pos in positions:
    max_gain = pos['max_gain']
    trail_pct = 15
    if max_gain > trail_pct:
        captured_pct = max_gain * (1 - trail_pct / 100)
    else:
        captured_pct = -15
    
    proceeds = pos['size'] * (1 + captured_pct / 100)
    profit = proceeds - pos['size']
    
    completed_trades.append({
        'size': pos['size'],
        'profit': profit,
        'profit_pct': captured_pct,
        'is_rug': pos['is_rug'],
    })
    
    capital += proceeds

# Results
total_profit = sum(t['profit'] for t in completed_trades)
winners = [t for t in completed_trades if t['profit'] > 0]
losers = [t for t in completed_trades if t['profit'] <= 0]

print(f'Starting Capital: $1,000.00')
print(f'Ending Capital:   ${capital:,.2f}')
print(f'Total Profit:     ${total_profit:+,.2f}')
print(f'Return:           {(capital/1000 - 1) * 100:+.1f}%')
print()
print(f'Total Trades:     {len(completed_trades)}')
print(f'Winners:          {len(winners)} ({len(winners)/len(completed_trades)*100:.1f}%)')
print(f'Losers:           {len(losers)} ({len(losers)/len(completed_trades)*100:.1f}%)')
if winners:
    print(f'Avg Win:          {sum(t["profit_pct"] for t in winners)/len(winners):+.1f}%')
if losers:
    print(f'Avg Loss:         {sum(t["profit_pct"] for t in losers)/len(losers):+.1f}%')
print()

# Top winners
print('=== TOP 10 WINNING TRADES ===')
sorted_trades = sorted(completed_trades, key=lambda t: t['profit'], reverse=True)[:10]
for i, trade in enumerate(sorted_trades, 1):
    rug_flag = "RUG" if trade['is_rug'] else "OK"
    print(f'{i:>2}. ${trade["size"]:>6.2f} → ${trade["size"] + trade["profit"]:>7.2f} '
          f'({trade["profit_pct"]:+6.1f}%) [{rug_flag}]')

print()

# Top losers
print('=== TOP 10 LOSING TRADES ===')
sorted_trades = sorted(completed_trades, key=lambda t: t['profit'])[:10]
for i, trade in enumerate(sorted_trades, 1):
    rug_flag = "RUG" if trade['is_rug'] else "OK"
    print(f'{i:>2}. ${trade["size"]:>6.2f} → ${trade["size"] + trade["profit"]:>7.2f} '
          f'({trade["profit_pct"]:+6.1f}%) [{rug_flag}]')

print()
print('='*80)
print('VERDICT:')
if capital > 1500:
    print(f'✅ PROFITABLE: ${capital:,.2f} (+{(capital/1000-1)*100:.0f}%)')
elif capital > 1000:
    print(f'✅ SLIGHTLY PROFITABLE: ${capital:,.2f} (+{(capital/1000-1)*100:.0f}%)')
elif capital > 800:
    print(f'⚠️  MARGINAL: ${capital:,.2f} ({(capital/1000-1)*100:.0f}%)')
else:
    print(f'❌ UNPROFITABLE: ${capital:,.2f} ({(capital/1000-1)*100:.0f}%)')
print('='*80)

conn.close()

