# Bot Performance Analysis Guide

## Overview
This guide provides comprehensive methods to analyze the bot's performance, identify optimization opportunities, and validate signal quality.

---

## 1. Signal Quality Analysis

### A. Score Distribution
```bash
# Analyze score distribution
sqlite3 /opt/callsbotonchain/var/alerted_tokens.db << 'SQL'
SELECT 
  CASE 
    WHEN final_score >= 9 THEN 'Perfect (9-10)'
    WHEN final_score >= 8 THEN 'Excellent (8)'
    WHEN final_score >= 6 THEN 'Good (6-7)'
    WHEN final_score >= 4 THEN 'Marginal (4-5)'
    ELSE 'Low (<4)'
  END as category,
  COUNT(*) as count,
  ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM alerted_tokens), 1) as percentage
FROM alerted_tokens
GROUP BY category
ORDER BY MIN(final_score) DESC;
SQL
```

**What to look for:**
- ✅ **Good**: Perfect+Excellent > 30%, Low < 20%
- ⚠️ **Warning**: Good signals < 50%
- ❌ **Bad**: Low signals > 30% (gates too loose)

### B. Conviction Type Analysis
```bash
# Breakdown by conviction type
sqlite3 /opt/callsbotonchain/var/alerted_tokens.db << 'SQL'
SELECT 
  conviction_type,
  COUNT(*) as count,
  ROUND(AVG(final_score), 1) as avg_score,
  ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM alerted_tokens), 1) as percentage
FROM alerted_tokens
WHERE conviction_type IS NOT NULL
GROUP BY conviction_type
ORDER BY count DESC;
SQL
```

**What to look for:**
- ✅ **Good**: Smart Money > 50%, Avg scores > 6.0
- ⚠️ **Warning**: Nuanced > 30% (may be taking too many risks)
- ❌ **Bad**: Smart Money < 30% (detection issue)

### C. Hourly Signal Distribution
```bash
# Check signal distribution by hour
sqlite3 /opt/callsbotonchain/var/alerted_tokens.db << 'SQL'
SELECT 
  SUBSTR(alerted_at, 12, 2) as hour,
  COUNT(*) as alerts,
  SUM(CASE WHEN smart_money_detected = 1 THEN 1 ELSE 0 END) as smart_alerts
FROM alerted_tokens
WHERE DATE(alerted_at) = DATE('now')
GROUP BY hour
ORDER BY hour;
SQL
```

**What to look for:**
- Identify peak activity hours
- Correlate with market conditions
- Adjust monitoring during high-activity periods

---

## 2. Tracking Performance Analysis

### A. Peak Multiple Distribution
```bash
# Analyze how well tokens perform after alert
curl -s 'http://127.0.0.1/api/tracked?limit=1000' | python3 << 'EOF'
import json, sys
data = json.load(sys.stdin)
rows = data.get('rows', [])

multiples = [r.get('peak_multiple', 0) for r in rows if r.get('peak_multiple')]
if multiples:
    multiples.sort(reverse=True)
    
    print(f"Total tracked: {len(rows)}")
    print(f"With peak data: {len(multiples)}")
    print("")
    print(f"Top 10 performers: {', '.join([f'{m:.2f}x' for m in multiples[:10]])}")
    print("")
    
    # Categories
    moon = sum(1 for m in multiples if m >= 10.0)
    big = sum(1 for m in multiples if 5.0 <= m < 10.0)
    good = sum(1 for m in multiples if 2.0 <= m < 5.0)
    small = sum(1 for m in multiples if 1.5 <= m < 2.0)
    flat = sum(1 for m in multiples if m < 1.5)
    
    print(f"🚀 Moon (≥10x): {moon} ({100*moon/len(multiples):.1f}%)")
    print(f"💎 Big (5-10x): {big} ({100*big/len(multiples):.1f}%)")
    print(f"✅ Good (2-5x): {good} ({100*good/len(multiples):.1f}%)")
    print(f"📊 Small (1.5-2x): {small} ({100*small/len(multiples):.1f}%)")
    print(f"📉 Flat (<1.5x): {flat} ({100*flat/len(multiples):.1f}%)")
    print("")
    
    avg = sum(multiples) / len(multiples)
    median = multiples[len(multiples)//2]
    print(f"Average peak: {avg:.2f}x")
    print(f"Median peak: {median:.2f}x")
EOF
```

**What to look for:**
- ✅ **Excellent**: Moon+Big > 10%, Avg > 2.0x
- ✅ **Good**: Good+Small > 50%, Avg > 1.5x
- ⚠️ **Warning**: Flat > 50% (signals too early or low quality)

### B. Smart Money vs Non-Smart Performance
```bash
# Compare smart money vs regular signal performance
curl -s 'http://127.0.0.1/api/tracked?limit=1000' | python3 << 'EOF'
import json, sys
data = json.load(sys.stdin)
rows = data.get('rows', [])

smart = [r.get('peak_multiple', 0) for r in rows 
         if 'Smart Money' in r.get('conviction', '') and r.get('peak_multiple')]
regular = [r.get('peak_multiple', 0) for r in rows 
           if 'Smart Money' not in r.get('conviction', '') and r.get('peak_multiple')]

if smart:
    smart_avg = sum(smart) / len(smart)
    smart_2x = sum(1 for m in smart if m >= 2.0)
    print(f"Smart Money Signals: {len(smart)}")
    print(f"  Avg peak: {smart_avg:.2f}x")
    print(f"  ≥2x: {smart_2x} ({100*smart_2x/len(smart):.1f}%)")

if regular:
    reg_avg = sum(regular) / len(regular)
    reg_2x = sum(1 for m in regular if m >= 2.0)
    print(f"\nRegular Signals: {len(regular)}")
    print(f"  Avg peak: {reg_avg:.2f}x")
    print(f"  ≥2x: {reg_2x} ({100*reg_2x/len(regular):.1f}%)")

if smart and regular:
    print(f"\nSmart Money Advantage: {smart_avg/reg_avg:.2f}x better")
EOF
```

**What to look for:**
- ✅ **Excellent**: Smart money 2x+ better than regular
- ✅ **Good**: Smart money 1.5x+ better
- ⚠️ **Warning**: No significant difference (detection may not be adding value)

### C. Time to Peak Analysis
```bash
# Analyze how quickly tokens reach peak
sqlite3 /opt/callsbotonchain/var/alerted_tokens.db << 'SQL'
SELECT 
  'Avg time to peak: ' || ROUND(AVG(
    (JULIANDAY(ats.peak_price_at) - JULIANDAY(at.alerted_at)) * 24 * 60
  ), 0) || ' minutes'
FROM alerted_tokens at
JOIN alerted_token_stats ats ON at.token_address = ats.token_address
WHERE ats.peak_price_at IS NOT NULL 
  AND ats.peak_price_at != ats.first_alert_at;
SQL
```

**What to look for:**
- ✅ **Fast**: < 30 minutes (catching early momentum)
- ✅ **Normal**: 30-120 minutes
- ⚠️ **Slow**: > 120 minutes (may be too conservative)

---

## 3. Budget Efficiency Analysis

### A. Daily Budget Trend
```bash
# Track budget usage over time (requires historical data)
curl -s http://127.0.0.1/api/v2/budget-status | python3 << 'EOF'
import json, sys
data = json.load(sys.stdin)

daily_used = data.get('daily_used', 0)
daily_max = data.get('daily_max', 1)
daily_pct = data.get('daily_percent', 0)
reset_hours = data.get('reset_hours', 0)

hours_elapsed = 24 - reset_hours
if hours_elapsed > 0:
    hourly_rate = daily_used / hours_elapsed
    projected = hourly_rate * 24
    
    print(f"Current usage: {daily_used}/{daily_max} ({daily_pct:.1f}%)")
    print(f"Hourly rate: {hourly_rate:.1f} calls/hour")
    print(f"Projected 24h: {projected:.0f} calls")
    print(f"Efficiency: {100*projected/daily_max:.1f}% of budget")
    print("")
    
    if projected < daily_max * 0.6:
        print("✅ Underutilized - can increase tracking frequency")
    elif projected < daily_max * 0.8:
        print("✅ Optimal usage")
    elif projected < daily_max:
        print("⚠️  High usage - monitor closely")
    else:
        print("❌ May exceed budget - reduce tracking or increase limit")
EOF
```

### B. API Call Efficiency
```bash
# Check how many API calls are saved by filtering
docker logs callsbot-worker --tail 2000 2>&1 | \
  grep '"type": "heartbeat"' | tail -20 | python3 << 'EOF'
import json, sys
total_items = 0
total_saved = 0
for line in sys.stdin:
    try:
        d = json.loads(line.strip())
        total_items += d.get('feed_items', 0)
        total_saved += d.get('api_calls_saved', 0)
    except:
        pass

if total_items > 0:
    efficiency = (total_saved / total_items) * 100
    print(f"Last 20 cycles:")
    print(f"  Feed items: {total_items}")
    print(f"  API calls saved: {total_saved}")
    print(f"  Efficiency: {efficiency:.1f}% (calls saved per item)")
    print("")
    
    if efficiency > 95:
        print("✅ Excellent filtering (>95% junk removed)")
    elif efficiency > 85:
        print("✅ Good filtering (85-95%)")
    else:
        print("⚠️  Low filtering (<85%) - may need stricter gates")
EOF
```

---

## 4. Feed Quality Analysis

### A. Feed Source Distribution
```bash
# Check where data is coming from
tail -100 /opt/callsbotonchain/data/logs/alerts.jsonl | python3 << 'EOF'
import json, sys
from collections import Counter

sources = []
for line in sys.stdin:
    try:
        alert = json.loads(line.strip())
        source = alert.get('data_source', 'unknown')
        sources.append(source)
    except:
        pass

if sources:
    counter = Counter(sources)
    print("Data sources (last 100 alerts):")
    for source, count in counter.most_common():
        pct = 100 * count / len(sources)
        print(f"  {source}: {count} ({pct:.1f}%)")
EOF
```

**What to look for:**
- ✅ **Good**: cielo+ds or pure cielo for majority
- ⚠️ **Warning**: High fallback usage (dexscreener/geckoterminal)
- ❌ **Bad**: synthetic > 20% (feed issues)

### B. Feed Cycle Performance
```bash
# Compare alert quality between general and smart cycles
tail -200 /opt/callsbotonchain/data/logs/alerts.jsonl | python3 << 'EOF'
import json, sys

general_scores = []
smart_scores = []

for line in sys.stdin:
    try:
        alert = json.loads(line.strip())
        score = alert.get('final_score', 0)
        smart_cycle = alert.get('smart_cycle', False)
        
        if smart_cycle:
            smart_scores.append(score)
        else:
            general_scores.append(score)
    except:
        pass

if general_scores:
    print(f"General cycle: {len(general_scores)} alerts, avg score {sum(general_scores)/len(general_scores):.1f}")
if smart_scores:
    print(f"Smart cycle: {len(smart_scores)} alerts, avg score {sum(smart_scores)/len(smart_scores):.1f}")

if general_scores and smart_scores:
    smart_avg = sum(smart_scores) / len(smart_scores)
    gen_avg = sum(general_scores) / len(general_scores)
    advantage = smart_avg - gen_avg
    print(f"\nSmart cycle advantage: +{advantage:.1f} score points")
EOF
```

---

## 5. Best Token Analysis

### A. Top Performers
```bash
# Find best performing tokens
curl -s 'http://127.0.0.1/api/tracked?limit=1000' | python3 << 'EOF'
import json, sys
data = json.load(sys.stdin)
rows = data.get('rows', [])

# Sort by peak multiple
sorted_rows = sorted(rows, key=lambda r: r.get('peak_multiple', 0), reverse=True)

print("🏆 TOP 20 PERFORMERS:\n")
for i, r in enumerate(sorted_rows[:20], 1):
    token = r.get('token', 'N/A')[:25]
    peak = r.get('peak_multiple', 0)
    score = r.get('final_score', 0)
    conviction = r.get('conviction', 'N/A')[:30]
    mcap = r.get('first_mcap', 0)
    
    emoji = "🚀" if peak >= 10 else "💎" if peak >= 5 else "✅" if peak >= 2 else "📊"
    print(f"{i:2}. {emoji} {token:25} | {peak:6.2f}x | Score: {score}/10 | ${mcap:,.0f}")
    print(f"     {conviction}")
EOF
```

### B. Pattern Analysis
```bash
# Identify common patterns in top performers
curl -s 'http://127.0.0.1/api/tracked?limit=1000' | python3 << 'EOF'
import json, sys
data = json.load(sys.stdin)
rows = data.get('rows', [])

# Get top 20% by peak multiple
sorted_rows = sorted(rows, key=lambda r: r.get('peak_multiple', 0), reverse=True)
top_20_pct = sorted_rows[:len(sorted_rows)//5]

if top_20_pct:
    # Analyze patterns
    smart_count = sum(1 for r in top_20_pct if 'Smart Money' in r.get('conviction', ''))
    avg_score = sum(r.get('final_score', 0) for r in top_20_pct) / len(top_20_pct)
    avg_mcap = sum(r.get('first_mcap', 0) for r in top_20_pct) / len(top_20_pct)
    
    print(f"Top 20% performers ({len(top_20_pct)} tokens):")
    print(f"  Smart Money: {smart_count} ({100*smart_count/len(top_20_pct):.1f}%)")
    print(f"  Avg Score: {avg_score:.1f}/10")
    print(f"  Avg Initial MCap: ${avg_mcap:,.0f}")
    
    if smart_count / len(top_20_pct) > 0.7:
        print("\n✅ Smart money signals are key winners")
    if avg_score > 7.5:
        print("✅ High scores correlate with performance")
    if avg_mcap < 100000:
        print("✅ Early entries (low mcap) perform best")
EOF
```

---

## 6. Failure Analysis

### A. Tokens That Didn't Pump
```bash
# Analyze tokens with low peak multiples
curl -s 'http://127.0.0.1/api/tracked?limit=1000' | python3 << 'EOF'
import json, sys
data = json.load(sys.stdin)
rows = data.get('rows', [])

# Get tokens with peak < 1.2x (didn't pump)
flat_tokens = [r for r in rows if r.get('peak_multiple', 0) < 1.2 and r.get('peak_multiple', 0) > 0]

if flat_tokens:
    print(f"📉 FLAT TOKENS ({len(flat_tokens)}):\n")
    
    # Analyze common patterns
    smart_count = sum(1 for r in flat_tokens if 'Smart Money' in r.get('conviction', ''))
    nuanced_count = sum(1 for r in flat_tokens if 'Nuanced' in r.get('conviction', ''))
    avg_score = sum(r.get('final_score', 0) for r in flat_tokens) / len(flat_tokens)
    
    print(f"Common patterns:")
    print(f"  Smart Money: {smart_count} ({100*smart_count/len(flat_tokens):.1f}%)")
    print(f"  Nuanced: {nuanced_count} ({100*nuanced_count/len(flat_tokens):.1f}%)")
    print(f"  Avg Score: {avg_score:.1f}/10")
    
    if nuanced_count / len(flat_tokens) > 0.4:
        print("\n⚠️  Many nuanced signals fail - consider stricter gates")
    if avg_score < 6.0:
        print("⚠️  Low scores correlate with failure - increase score threshold")
EOF
```

---

## 7. Generate Performance Report

Save as `/opt/callsbotonchain/ops/generate_report.sh`:

```bash
#!/bin/bash
echo "========================================="
echo "CALLSBOT PERFORMANCE REPORT"
echo "Generated: $(date)"
echo "========================================="
echo ""

# 1. Signal Quality
echo "1. SIGNAL QUALITY"
echo "-----------------"
sqlite3 /opt/callsbotonchain/var/alerted_tokens.db << 'SQL'
SELECT 
  'Total Alerts: ' || COUNT(*) ||
  ' | Smart: ' || SUM(CASE WHEN smart_money_detected = 1 THEN 1 ELSE 0 END) ||
  ' (' || ROUND(100.0 * SUM(CASE WHEN smart_money_detected = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) || '%)' ||
  ' | Avg Score: ' || ROUND(AVG(final_score), 1)
FROM alerted_tokens;
SQL
echo ""

# 2. Top Performers
echo "2. TOP 5 PERFORMERS"
echo "-------------------"
curl -s 'http://127.0.0.1/api/tracked?limit=100' | python3 -c "
import json, sys
rows = json.load(sys.stdin).get('rows', [])
top5 = sorted(rows, key=lambda r: r.get('peak_multiple', 0), reverse=True)[:5]
for r in top5:
    print(f\"{r.get('token', 'N/A')[:20]:20} | {r.get('peak_multiple', 0):6.2f}x\")
"
echo ""

# 3. Budget
echo "3. BUDGET STATUS"
echo "----------------"
curl -s http://127.0.0.1/api/v2/budget-status | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f\"Daily: {d['daily_used']}/{d['daily_max']} ({d['daily_percent']:.1f}%)\")
print(f\"Status: {d['status']} | Zero-Miss: {'ON' if d['zero_miss_mode'] else 'OFF'}\")
"
echo ""

echo "========================================="
echo "Report complete. Check dashboard for details:"
echo "http://64.227.157.221/"
echo "========================================="
```

Run daily:
```bash
chmod +x /opt/callsbotonchain/ops/generate_report.sh
/opt/callsbotonchain/ops/generate_report.sh > /opt/callsbotonchain/reports/$(date +%Y%m%d).txt
```

---

## 8. Key Performance Indicators (KPIs)

Track these metrics daily:

### Signal Quality KPIs:
- **Smart Money %**: Target > 50%
- **Avg Score**: Target > 6.0
- **High Score %**: Target > 30% (score ≥ 8)

### Performance KPIs:
- **Avg Peak Multiple**: Target > 2.0x
- **≥5x Rate**: Target > 10%
- **≥2x Rate**: Target > 40%
- **Flat Rate (<1.5x)**: Target < 40%

### Operational KPIs:
- **Budget Usage**: Target 50-80% (not too low, not maxed)
- **API Efficiency**: Target > 90% filtering
- **Container Uptime**: Target 100% (0 restarts)
- **Heartbeat Freshness**: Target < 2 minutes

### Trading KPIs (when enabled):
- **Win Rate**: Target > 60%
- **Avg Profit per Trade**: Target > 20%
- **Max Drawdown**: Target < 30%
- **Sharpe Ratio**: Target > 1.5

