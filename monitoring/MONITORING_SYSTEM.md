# Local Monitoring System

## Overview

This system provides automated, continuous monitoring of your callsbotonchain bot running on the server. It collects metrics every 5 minutes, stores them locally in the `analytics/` folder, and provides comprehensive analysis tools.

---

## Features

### ✅ Automated Monitoring
- **Periodic Checks**: Runs every 5 minutes (configurable)
- **Health Scoring**: 0-100 score based on multiple factors
- **Issue Detection**: Automatically identifies problems
- **Historical Data**: All metrics stored for trend analysis

### 📊 Metrics Collected
- Container status and restart counts
- API statistics (alerts, tracking, signals)
- Budget usage and efficiency
- Feed health and cycle performance
- Database statistics
- System resources (disk, memory, CPU)
- Error counts and types
- Tracking sample data

### 🔍 Analysis Capabilities
- Health trend analysis
- Signal quality metrics
- Budget efficiency tracking
- Resource usage patterns
- Feed performance analysis
- Anomaly detection
- Automated recommendations

---

## Installation

### 1. Prerequisites
- Python 3.7+ installed locally
- SSH access to server configured
- `ssh root@64.227.157.221` should work without password (using SSH keys)

### 2. Test SSH Connection
```bash
ssh root@64.227.157.221 "echo 'Connection OK'"
```

If this doesn't work, set up SSH keys first:
```bash
ssh-copy-id root@64.227.157.221
```

---

## Usage

### Start Monitoring

**Run in foreground** (recommended for testing):
```bash
python monitoring/monitor_bot.py
```

**Run in background** (for continuous monitoring):

**Windows (PowerShell):**
```powershell
Start-Process python -ArgumentList "monitoring/monitor_bot.py" -NoNewWindow -RedirectStandardOutput "monitor.log"
```

**Linux/Mac:**
```bash
nohup python3 monitoring/monitor_bot.py > monitor.log 2>&1 &
```

### Stop Monitoring
Press `Ctrl+C` in the terminal, or:

**Windows:**
```powershell
Stop-Process -Name python
```

**Linux/Mac:**
```bash
pkill -f monitor_bot.py
```

---

## Analyzing Data

### View Latest Status
```bash
# View latest snapshot
cat analytics/latest_snapshot.json | python -m json.tool

# View today's summary
cat analytics/summary_$(date +%Y-%m-%d).json | python -m json.tool
```

### Run Comprehensive Analysis
```bash
# Analyze today's data
python monitoring/analyze_metrics.py

# Analyze specific date
python monitoring/analyze_metrics.py 2025-10-04
```

### View Available Data
```bash
# List all collected metrics
ls -lh analytics/

# View health history
cat analytics/health_history.jsonl | tail -20
```

---

## Output Files

### `analytics/` Directory Structure

```
analytics/
├── metrics_2025-10-04.jsonl       # Raw metrics for each day
├── summary_2025-10-04.json        # Daily summary statistics
├── health_history.jsonl           # Rolling health scores (last 1000)
└── latest_snapshot.json           # Most recent check results
```

### File Descriptions

**`metrics_YYYY-MM-DD.jsonl`**
- One JSON line per check
- Contains all collected metrics
- Used for detailed analysis
- New file created each day

**`summary_YYYY-MM-DD.json`**
- Generated every 10 checks
- Contains aggregated statistics
- Shows trends for the day

**`health_history.jsonl`**
- Lightweight health scores only
- Rolling file (keeps last 1000)
- Used for long-term trend analysis

**`latest_snapshot.json`**
- Most recent check results
- Overwritten each check
- Quick way to see current status

---

## Health Scoring

### Score Breakdown (0-100)

**Perfect (100)**: All systems green
- All containers running
- No restarts
- Fresh heartbeat (< 2 min)
- Budget usage normal
- No errors
- Resources healthy

**Deductions:**
- -30: Containers not running
- -30: No heartbeat found
- -25: Stale heartbeat (>5 min)
- -20: Budget >90% or Disk >90%
- -20: Containers restarted
- -15: Memory >90%
- -10: Multiple warnings
- -10: Heartbeat 2-5 min old
- -5: Budget 80-90%
- -5: Disk/Memory 80-90%
- -5: Signals disabled

### Status Categories

| Score   | Status      | Meaning                           |
|---------|-------------|-----------------------------------|
| 90-100  | EXCELLENT   | Perfect operation                 |
| 75-89   | GOOD        | Minor warnings only               |
| 60-74   | WARNING     | Some issues need attention        |
| 40-59   | DEGRADED    | Multiple issues, needs fixing     |
| 0-39    | CRITICAL    | Serious problems, immediate action|

---

## Example Workflows

### Daily Routine

**Morning Check:**
```bash
# Check overnight status
python analyze_metrics.py

# Look for issues
cat analytics/latest_snapshot.json | grep -A 3 "health_analysis"
```

**Evening Review:**
```bash
# Generate report
python analyze_metrics.py > daily_report_$(date +%Y%m%d).txt

# Review recommendations
cat daily_report_*.txt | grep -A 5 "RECOMMENDATIONS"
```

### Troubleshooting

**If monitoring shows issues:**
```bash
# 1. Check latest snapshot
cat analytics/latest_snapshot.json | python -m json.tool

# 2. Review issues and warnings
python analyze_metrics.py | grep -A 20 "RECOMMENDATIONS"

# 3. SSH to server and investigate
ssh root@64.227.157.221
cd /opt/callsbotonchain
docker logs callsbot-worker --tail 50
```

### Trend Analysis

**Weekly Performance:**
```bash
# Analyze each day of the week
for date in 2025-10-01 2025-10-02 2025-10-03; do
    echo "=== $date ==="
    python analyze_metrics.py $date | grep "Average Score"
done
```

**Health History:**
```bash
# View last 20 health scores
tail -20 analytics/health_history.jsonl | python -c "
import json, sys
for line in sys.stdin:
    d = json.loads(line)
    print(f\"{d['timestamp'][:19]} | {d['status']:10} | Score: {d['score']:3}/100\")
"
```

---

## Configuration

### Adjust Check Interval

Edit `monitor_bot.py`:
```python
CHECK_INTERVAL_SECONDS = 300  # 5 minutes (default)
# Change to 600 for 10 minutes
# Change to 180 for 3 minutes
```

### Change Server

Edit `monitor_bot.py`:
```python
SERVER = "root@64.227.157.221"  # Change to your server
SERVER_PATH = "/opt/callsbotonchain"  # Change if different
```

### Customize Analytics Location

Edit both `monitor_bot.py` and `analyze_metrics.py`:
```python
LOCAL_ANALYTICS_DIR = Path("analytics")  # Change to your preferred location
```

---

## Automation

### Run on Startup (Windows)

1. Create `start_monitor.bat`:
```batch
@echo off
cd /d C:\Users\barat\yesv2\callsbotonchain
python monitor_bot.py > monitor.log 2>&1
```

2. Add to Windows Task Scheduler:
   - Open Task Scheduler
   - Create Basic Task
   - Name: "CallsBot Monitor"
   - Trigger: "When I log on"
   - Action: Start program
   - Program: `C:\Users\barat\yesv2\callsbotonchain\start_monitor.bat`

### Run on Startup (Linux/Mac)

Add to crontab:
```bash
crontab -e
# Add line:
@reboot cd /path/to/callsbotonchain && nohup python3 monitor_bot.py > monitor.log 2>&1 &
```

### Daily Analysis Report

Add to crontab:
```bash
0 23 * * * cd /path/to/callsbotonchain && python3 analyze_metrics.py > reports/report_$(date +\%Y\%m\%d).txt
```

---

## Monitoring Best Practices

### 1. Regular Reviews
- Check `latest_snapshot.json` daily
- Run analysis weekly
- Review trends monthly

### 2. Alert Thresholds
Set up alerts (manually or automated) for:
- Health score < 60
- Budget usage > 85%
- Disk usage > 85%
- No heartbeat for 10+ minutes
- Container restarts detected

### 3. Data Retention
- Keep daily metrics for 30 days
- Keep weekly summaries for 1 year
- Archive old data to external storage

### 4. Backup Analytics
```bash
# Backup analytics folder
tar -czf analytics_backup_$(date +%Y%m%d).tar.gz analytics/

# Copy to safe location
cp analytics_backup_*.tar.gz ~/backups/
```

---

## Troubleshooting

### Monitor Not Starting

**Error: SSH connection failed**
```bash
# Test SSH
ssh root@64.227.157.221 "echo OK"

# Set up SSH keys if needed
ssh-copy-id root@64.227.157.221
```

**Error: Python module not found**
```bash
# Verify Python version
python --version  # Should be 3.7+

# No additional dependencies needed (uses stdlib only)
```

### No Metrics Being Collected

**Check SSH connection:**
```bash
python -c "import subprocess; print(subprocess.run(['ssh', 'root@64.227.157.221', 'echo OK'], capture_output=True, text=True).stdout)"
```

**Check server paths:**
```bash
ssh root@64.227.157.221 "ls -la /opt/callsbotonchain"
```

### Analysis Shows "No data available"

**Check files exist:**
```bash
ls -lh analytics/metrics_*.jsonl
```

**Check file format:**
```bash
# View first line
head -1 analytics/metrics_$(date +%Y-%m-%d).jsonl | python -m json.tool
```

---

## Advanced Usage

### Custom Metrics

Add custom metrics to `monitor_bot.py`:

```python
def get_custom_metric():
    """Your custom metric collection"""
    cmd = """your custom SSH command"""
    stdout, stderr, code = run_ssh_command(cmd)
    # Process and return data
    return {"your": "data"}

# In collect_metrics(), add:
data['custom_metric'] = get_custom_metric()
```

### Export to External Systems

```python
# Add to save_metrics() function:
def send_to_external_system(data):
    """Send metrics to external monitoring"""
    import requests
    requests.post('https://your-monitoring-system.com/api/metrics', json=data)

# Call in save_metrics()
send_to_external_system(data)
```

### Alerting Integration

```python
# Add to analyze_health() function:
def send_alert(message):
    """Send alert when issues detected"""
    if health_analysis['status'] in ['CRITICAL', 'DEGRADED']:
        # Send email, SMS, Slack, etc.
        pass
```

---

## FAQ

**Q: How much disk space does monitoring use?**
A: Approximately 50-100KB per day (15-30MB per month)

**Q: Will this slow down the bot?**
A: No, monitoring reads data and doesn't interfere with bot operation

**Q: Can I run multiple monitors?**
A: Yes, but they'll create separate analytics files. Use different ANALYTICS_DIR for each.

**Q: What if my internet goes down?**
A: Monitor will pause, resume when connection restored. No data loss on server.

**Q: How do I reset analytics?**
A: Delete or rename the `analytics/` folder. Fresh start on next check.

**Q: Can I monitor multiple bots?**
A: Yes, create separate monitor scripts with different SERVER and ANALYTICS_DIR settings.

---

## Support

For issues with the monitoring system:
1. Check this README
2. Review `monitor.log` for errors
3. Test SSH connection manually
4. Verify server paths and permissions

For issues with the bot itself:
1. Check `ops/TROUBLESHOOTING.md`
2. Review server logs directly
3. Use monitoring data to identify trends

---

## Future Enhancements

Potential features to add:
- [ ] Web dashboard for viewing analytics
- [ ] Real-time alerting (email/Slack/Discord)
- [ ] Predictive analysis (ML-based)
- [ ] Comparison across multiple bots
- [ ] Export to time-series databases (InfluxDB, Prometheus)
- [ ] Mobile app integration
- [ ] Automated issue resolution

---

**Last Updated**: October 4, 2025  
**Version**: 1.0  
**Status**: Production Ready

