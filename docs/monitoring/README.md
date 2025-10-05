# Monitoring System Overview

## What This System Does

### 1. Operational Monitoring (`monitor_bot.py`)
Monitors your bot's **health and operational metrics** every 5 minutes:
- Container status, restarts, uptime
- Budget usage and efficiency  
- Feed health and cycle performance
- System resources (disk, memory, CPU)
- API statistics
- Error detection

**Run with:**
```bash
python monitoring/monitor_bot.py
```

**Analyze with:**
```bash
python monitoring/analyze_metrics.py
```

---

### 2. Signal Performance Analysis (`analyze_signals.py`) ⭐ NEW

Monitors your bot's **signal quality and profitability**:
- Which tokens pumped or dumped after alerts
- Win rate and outcome distribution
- Score correlation with outcomes
- Smart money detection effectiveness
- Market cap sweet spots
- Specific tuning recommendations

**Run with:**
```bash
# Copy database from server first
scp root@64.227.157.221:/opt/callsbotonchain/var/alerted_tokens.db var/

# Analyze signal performance
python monitoring/analyze_signals.py 7  # Last 7 days
```

---

## Why You Need Both

| Operational Monitoring | Signal Performance |
|------------------------|-------------------|
| "Is the bot running?" | "Is the bot profitable?" |
| Health score, uptime | Win rate, outcomes |
| Budget usage | Signal quality |
| Feed cycling | Tuning recommendations |
| System resources | Criteria correlation |

**Both are critical:**
- Operational monitoring ensures the bot stays alive
- Signal analysis ensures it's making good decisions

---

## Quick Start

### For Signal Performance Analysis (Most Important)

```powershell
# 1. Copy database
scp root@64.227.157.221:/opt/callsbotonchain/var/alerted_tokens.db var/

# 2. Run analysis
python monitoring/analyze_signals.py

# 3. Review win rate and recommendations
# 4. Tune config based on results
```

See **[QUICK_START.md](QUICK_START.md)** for details.

### For Operational Monitoring

```powershell
# Start monitoring (runs continuously)
python monitoring/monitor_bot.py

# In another terminal, analyze collected data
python monitoring/analyze_metrics.py
```

See **[MONITORING_SYSTEM.md](MONITORING_SYSTEM.md)** for details.

---

## Files in This Directory

| File | Purpose |
|------|---------|
| **monitor_bot.py** | Continuous operational health monitoring |
| **analyze_metrics.py** | Analyzes operational metrics and trends |
| **analyze_signals.py** | Analyzes signal performance and profitability ⭐ |
| **MONITORING_SYSTEM.md** | Full operational monitoring documentation |
| **SIGNAL_ANALYSIS.md** | Full signal performance documentation ⭐ |
| **QUICK_START.md** | Quick start guide for signal analysis ⭐ |
| **README.md** | This file |

⭐ = NEW for signal performance analysis

---

## Recommended Workflow

### Daily (1 minute)
```bash
# Check latest operational snapshot
cat analytics/latest_snapshot.json | python -m json.tool
```

### Weekly (5 minutes)
```powershell
# Analyze signal performance
scp root@64.227.157.221:/opt/callsbotonchain/var/alerted_tokens.db var/
python monitoring/analyze_signals.py 7
```

### Monthly (30 minutes)
```powershell
# Deep dive on both operational and signal performance
python monitoring/analyze_metrics.py
python monitoring/analyze_signals.py 30

# Implement top recommendations
# Document changes in tuning log
```

---

## What Gets Monitored Locally

### Operational Metrics (Every 5 minutes)
- ✅ Container health (4 containers)
- ✅ Restart counts
- ✅ Heartbeat freshness (<2 min = healthy)
- ✅ Budget usage (calls/day limit)
- ✅ Feed alternation (smart/regular cycles)
- ✅ Disk/memory/CPU usage
- ✅ Error counts in logs
- ✅ Database statistics

Stored in: `analytics/metrics_YYYY-MM-DD.jsonl`

### Signal Performance (On-demand)
- ✅ Token outcomes (pump/dump/rug)
- ✅ Win rate by conviction type
- ✅ Score correlation with outcomes
- ✅ Smart money advantage
- ✅ Market cap performance
- ✅ Time to peak for winners
- ✅ Tuning recommendations

Analyzed from: `var/alerted_tokens.db`

---

## Key Questions Answered

### Operational Monitoring
- Is the bot still running?
- Is the budget running out?
- Are there errors in the logs?
- Is the feed cycling properly?
- Is disk space low?

### Signal Performance Analysis
- What's my win rate?
- Which signals are profitable?
- Is smart money detection working?
- Which market cap range performs best?
- What should I tune to improve?

---

## Getting Started

1. **Set up operational monitoring** (optional, for continuous health checks)
   ```bash
   python monitoring/monitor_bot.py
   ```

2. **Run your first signal analysis** (essential, for tuning)
   ```powershell
   scp root@64.227.157.221:/opt/callsbotonchain/var/alerted_tokens.db var/
   python monitoring/analyze_signals.py
   ```

3. **Read the results**
   - Check win rate (target >40%)
   - Review recommendations
   - Tune config based on data

4. **Iterate weekly**
   - Re-analyze after changes
   - Track improvements over time
   - Continue tuning

---

## Documentation

| Topic | Document |
|-------|----------|
| Quick start for signal analysis | [QUICK_START.md](QUICK_START.md) |
| Full signal analysis guide | [SIGNAL_ANALYSIS.md](SIGNAL_ANALYSIS.md) |
| Operational monitoring setup | [MONITORING_SYSTEM.md](MONITORING_SYSTEM.md) |
| Manual SQL analysis queries | [../ops/ANALYSIS_GUIDE.md](../ops/ANALYSIS_GUIDE.md) |
| Trading system monitoring | [../docs/TRADING_MONITORING.md](../docs/TRADING_MONITORING.md) |

---

## Support

For issues with:
- **Signal analysis** - Check SIGNAL_ANALYSIS.md troubleshooting section
- **Operational monitoring** - Check MONITORING_SYSTEM.md troubleshooting section
- **Bot itself** - Check ../ops/TROUBLESHOOTING.md

---

**System Status**: Production Ready  
**Last Updated**: October 4, 2025  
**Version**: 1.1 (Added Signal Performance Analysis)

