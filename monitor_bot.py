#!/usr/bin/env python3
"""
Local Bot Monitor - Periodically checks server health and stores analytics
Runs from your local machine, connects to server via SSH
"""

import subprocess
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import time

# Configuration
SERVER = "root@64.227.157.221"
SERVER_PATH = "/opt/callsbotonchain"
LOCAL_ANALYTICS_DIR = Path("analytics")
CHECK_INTERVAL_SECONDS = 300  # 5 minutes

# Ensure analytics directory exists
LOCAL_ANALYTICS_DIR.mkdir(exist_ok=True)

def run_ssh_command(command):
    """Execute SSH command and return output"""
    try:
        result = subprocess.run(
            ["ssh", SERVER, command],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return None, "Command timed out", 1
    except Exception as e:
        return None, str(e), 1

def get_container_status():
    """Check Docker container status"""
    cmd = """docker ps --format '{"name":"{{.Names}}","status":"{{.Status}}","uptime":"{{.RunningFor}}"}' | grep callsbot"""
    stdout, stderr, code = run_ssh_command(cmd)
    
    containers = []
    if code == 0 and stdout:
        for line in stdout.strip().split('\n'):
            try:
                containers.append(json.loads(line))
            except:
                pass
    
    return {
        "success": code == 0,
        "containers": containers,
        "count": len(containers)
    }

def get_container_restarts():
    """Check container restart counts"""
    cmd = """docker inspect callsbot-worker callsbot-web callsbot-trader --format='{"name":"{{.Name}}","restarts":{{.RestartCount}},"started":"{{.State.StartedAt}}"}' 2>/dev/null"""
    stdout, stderr, code = run_ssh_command(cmd)
    
    restarts = []
    if code == 0 and stdout:
        for line in stdout.strip().split('\n'):
            try:
                restarts.append(json.loads(line))
            except:
                pass
    
    return restarts

def get_api_stats():
    """Get bot statistics from API"""
    cmd = """curl -s http://127.0.0.1/api/v2/quick-stats"""
    stdout, stderr, code = run_ssh_command(cmd)
    
    if code == 0 and stdout:
        try:
            return json.loads(stdout)
        except:
            pass
    return None

def get_budget_status():
    """Get budget status"""
    cmd = """curl -s http://127.0.0.1/api/v2/budget-status"""
    stdout, stderr, code = run_ssh_command(cmd)
    
    if code == 0 and stdout:
        try:
            return json.loads(stdout)
        except:
            pass
    return None

def get_feed_health():
    """Get feed health status"""
    cmd = """curl -s http://127.0.0.1/api/v2/feed-health"""
    stdout, stderr, code = run_ssh_command(cmd)
    
    if code == 0 and stdout:
        try:
            return json.loads(stdout)
        except:
            pass
    return None

def get_last_heartbeat():
    """Get last worker heartbeat"""
    cmd = """docker logs callsbot-worker --tail 2000 2>&1 | grep '"type": "heartbeat"' | tail -1"""
    stdout, stderr, code = run_ssh_command(cmd)
    
    if code == 0 and stdout:
        try:
            return json.loads(stdout.strip())
        except:
            pass
    return None

def get_database_stats():
    """Get database statistics"""
    cmd = f"""sqlite3 {SERVER_PATH}/var/alerted_tokens.db << 'SQL'
SELECT json_object(
    'total_alerts', COUNT(*),
    'smart_money', SUM(CASE WHEN smart_money_detected = 1 THEN 1 ELSE 0 END),
    'avg_score', ROUND(AVG(final_score), 2)
) FROM alerted_tokens;
SQL"""
    stdout, stderr, code = run_ssh_command(cmd)
    
    if code == 0 and stdout:
        try:
            return json.loads(stdout.strip())
        except:
            pass
    return None

def get_resource_usage():
    """Get system resource usage"""
    # Disk usage
    disk_cmd = """df -h / | tail -1 | awk '{print $5}' | sed 's/%//'"""
    disk_stdout, _, _ = run_ssh_command(disk_cmd)
    disk_usage = int(disk_stdout.strip()) if disk_stdout else 0
    
    # Memory usage
    mem_cmd = """free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}'"""
    mem_stdout, _, _ = run_ssh_command(mem_cmd)
    mem_usage = float(mem_stdout.strip()) if mem_stdout else 0
    
    # Container memory
    container_mem_cmd = """docker stats --no-stream --format '{"name":"{{.Name}}","memory":"{{.MemUsage}}","cpu":"{{.CPUPerc}}"}' | grep callsbot"""
    container_stdout, _, _ = run_ssh_command(container_mem_cmd)
    
    containers = []
    if container_stdout:
        for line in container_stdout.strip().split('\n'):
            try:
                containers.append(json.loads(line))
            except:
                pass
    
    return {
        "disk_usage_percent": disk_usage,
        "memory_usage_percent": mem_usage,
        "containers": containers
    }

def get_recent_errors():
    """Check for recent errors in logs"""
    cmd = """docker logs callsbot-worker --tail 1000 2>&1 | grep -iE 'exception|traceback|fatal|critical' | grep -v 'JSONDecodeError' | grep -v 'Telegram' | wc -l"""
    stdout, stderr, code = run_ssh_command(cmd)
    
    error_count = int(stdout.strip()) if stdout and stdout.strip().isdigit() else -1
    
    return {
        "critical_error_count": error_count,
        "has_errors": error_count > 0
    }

def get_tracking_sample():
    """Get sample of tracked tokens"""
    cmd = """curl -s 'http://127.0.0.1/api/tracked?limit=5'"""
    stdout, stderr, code = run_ssh_command(cmd)
    
    if code == 0 and stdout:
        try:
            data = json.loads(stdout)
            rows = data.get('rows', [])
            return {
                "count": len(rows),
                "sample": rows[:3] if rows else []
            }
        except:
            pass
    return None

def analyze_health(data):
    """Analyze collected data and determine health status"""
    issues = []
    warnings = []
    score = 100  # Start with perfect score
    
    # Check containers
    if data.get('containers', {}).get('count', 0) != 4:
        issues.append("Not all containers running")
        score -= 30
    
    # Check restarts
    restarts = data.get('container_restarts', [])
    total_restarts = sum(r.get('restarts', 0) for r in restarts)
    if total_restarts > 0:
        warnings.append(f"Containers have restarted {total_restarts} times")
        score -= 10
    
    # Check heartbeat
    heartbeat = data.get('last_heartbeat')
    if heartbeat:
        hb_time = heartbeat.get('ts', '')
        if hb_time:
            try:
                hb_dt = datetime.fromisoformat(hb_time.replace('Z', '+00:00'))
                age_seconds = (datetime.now(timezone.utc) - hb_dt).total_seconds()
                if age_seconds > 300:
                    issues.append(f"Heartbeat is {age_seconds:.0f}s old (stale)")
                    score -= 25
                elif age_seconds > 120:
                    warnings.append(f"Heartbeat is {age_seconds:.0f}s old")
                    score -= 10
            except:
                pass
    else:
        issues.append("No heartbeat found")
        score -= 30
    
    # Check budget
    budget = data.get('budget_status', {})
    if budget:
        daily_pct = budget.get('daily_percent', 0)
        if daily_pct > 90:
            issues.append(f"Budget usage high: {daily_pct:.1f}%")
            score -= 20
        elif daily_pct > 80:
            warnings.append(f"Budget usage elevated: {daily_pct:.1f}%")
            score -= 5
    
    # Check resources
    resources = data.get('resource_usage', {})
    disk_usage = resources.get('disk_usage_percent', 0)
    mem_usage = resources.get('memory_usage_percent', 0)
    
    if disk_usage > 90:
        issues.append(f"Disk usage critical: {disk_usage}%")
        score -= 20
    elif disk_usage > 80:
        warnings.append(f"Disk usage high: {disk_usage}%")
        score -= 5
    
    if mem_usage > 90:
        issues.append(f"Memory usage critical: {mem_usage:.1f}%")
        score -= 15
    elif mem_usage > 80:
        warnings.append(f"Memory usage high: {mem_usage:.1f}%")
        score -= 5
    
    # Check errors
    errors = data.get('recent_errors', {})
    if errors.get('critical_error_count', 0) > 5:
        warnings.append(f"Multiple critical errors detected: {errors['critical_error_count']}")
        score -= 10
    
    # Check API stats
    stats = data.get('api_stats', {})
    if stats:
        if not stats.get('signals_enabled', False):
            warnings.append("Signals are disabled")
            score -= 5
    
    # Determine overall status
    if score >= 90:
        status = "EXCELLENT"
    elif score >= 75:
        status = "GOOD"
    elif score >= 60:
        status = "WARNING"
    elif score >= 40:
        status = "DEGRADED"
    else:
        status = "CRITICAL"
    
    return {
        "status": status,
        "score": max(0, score),
        "issues": issues,
        "warnings": warnings
    }

def collect_metrics():
    """Collect all metrics from server"""
    timestamp = datetime.now(timezone.utc).isoformat()
    
    print(f"[{timestamp}] Collecting metrics from {SERVER}...")
    
    data = {
        "timestamp": timestamp,
        "server": SERVER,
        "containers": get_container_status(),
        "container_restarts": get_container_restarts(),
        "api_stats": get_api_stats(),
        "budget_status": get_budget_status(),
        "feed_health": get_feed_health(),
        "last_heartbeat": get_last_heartbeat(),
        "database_stats": get_database_stats(),
        "resource_usage": get_resource_usage(),
        "recent_errors": get_recent_errors(),
        "tracking_sample": get_tracking_sample()
    }
    
    # Analyze health
    health_analysis = analyze_health(data)
    data['health_analysis'] = health_analysis
    
    # Print summary
    print(f"  Status: {health_analysis['status']} (Score: {health_analysis['score']}/100)")
    if health_analysis['issues']:
        print(f"  ❌ Issues: {len(health_analysis['issues'])}")
        for issue in health_analysis['issues']:
            print(f"     - {issue}")
    if health_analysis['warnings']:
        print(f"  ⚠️  Warnings: {len(health_analysis['warnings'])}")
        for warning in health_analysis['warnings']:
            print(f"     - {warning}")
    
    # Show key metrics
    if data['api_stats']:
        stats = data['api_stats']
        print(f"  📊 Alerts: {stats.get('total_alerts', 0)} | Tracking: {stats.get('tracking_count', 0)}")
    
    if data['budget_status']:
        budget = data['budget_status']
        print(f"  💰 Budget: {budget.get('daily_used', 0)}/{budget.get('daily_max', 0)} ({budget.get('daily_percent', 0):.1f}%)")
    
    return data

def save_metrics(data):
    """Save metrics to analytics folder"""
    # Daily file
    date_str = datetime.now().strftime("%Y-%m-%d")
    daily_file = LOCAL_ANALYTICS_DIR / f"metrics_{date_str}.jsonl"
    
    with open(daily_file, 'a') as f:
        f.write(json.dumps(data) + '\n')
    
    # Latest snapshot
    latest_file = LOCAL_ANALYTICS_DIR / "latest_snapshot.json"
    with open(latest_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    # Health history (rolling, keep last 1000)
    health_file = LOCAL_ANALYTICS_DIR / "health_history.jsonl"
    
    # Append new entry
    with open(health_file, 'a') as f:
        health_entry = {
            "timestamp": data['timestamp'],
            "status": data['health_analysis']['status'],
            "score": data['health_analysis']['score'],
            "issues_count": len(data['health_analysis']['issues']),
            "warnings_count": len(data['health_analysis']['warnings'])
        }
        f.write(json.dumps(health_entry) + '\n')
    
    # Trim to last 1000 entries
    try:
        with open(health_file, 'r') as f:
            lines = f.readlines()
        if len(lines) > 1000:
            with open(health_file, 'w') as f:
                f.writelines(lines[-1000:])
    except:
        pass
    
    print(f"  💾 Saved to {daily_file}")

def generate_summary():
    """Generate daily summary report"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    daily_file = LOCAL_ANALYTICS_DIR / f"metrics_{date_str}.jsonl"
    
    if not daily_file.exists():
        return
    
    # Read all entries from today
    entries = []
    with open(daily_file, 'r') as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except:
                pass
    
    if not entries:
        return
    
    # Calculate statistics
    scores = [e['health_analysis']['score'] for e in entries if 'health_analysis' in e]
    statuses = [e['health_analysis']['status'] for e in entries if 'health_analysis' in e]
    
    summary = {
        "date": date_str,
        "checks_performed": len(entries),
        "avg_health_score": sum(scores) / len(scores) if scores else 0,
        "min_health_score": min(scores) if scores else 0,
        "max_health_score": max(scores) if scores else 0,
        "status_distribution": {status: statuses.count(status) for status in set(statuses)},
        "total_issues": sum(len(e['health_analysis']['issues']) for e in entries if 'health_analysis' in e),
        "total_warnings": sum(len(e['health_analysis']['warnings']) for e in entries if 'health_analysis' in e)
    }
    
    # Save summary
    summary_file = LOCAL_ANALYTICS_DIR / f"summary_{date_str}.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    return summary

def main():
    """Main monitoring loop"""
    print("=" * 60)
    print("CALLSBOT LOCAL MONITOR")
    print("=" * 60)
    print(f"Server: {SERVER}")
    print(f"Analytics: {LOCAL_ANALYTICS_DIR.absolute()}")
    print(f"Check Interval: {CHECK_INTERVAL_SECONDS}s ({CHECK_INTERVAL_SECONDS//60} minutes)")
    print("=" * 60)
    print()
    
    check_count = 0
    
    try:
        while True:
            check_count += 1
            print(f"\n[Check #{check_count}]")
            
            # Collect metrics
            try:
                data = collect_metrics()
                save_metrics(data)
                
                # Generate summary every 10 checks (or at start of day)
                if check_count % 10 == 0 or datetime.now().hour == 0:
                    summary = generate_summary()
                    if summary:
                        print(f"\n📊 Daily Summary: Avg Score {summary['avg_health_score']:.1f}/100")
                
            except Exception as e:
                print(f"  ❌ Error collecting metrics: {e}")
            
            # Wait for next check
            print(f"\n⏳ Waiting {CHECK_INTERVAL_SECONDS}s until next check...")
            time.sleep(CHECK_INTERVAL_SECONDS)
            
    except KeyboardInterrupt:
        print("\n\n⛔ Monitoring stopped by user")
        print(f"Total checks performed: {check_count}")
        
        # Generate final summary
        summary = generate_summary()
        if summary:
            print(f"\n📊 Final Summary:")
            print(f"  Checks: {summary['checks_performed']}")
            print(f"  Avg Score: {summary['avg_health_score']:.1f}/100")
            print(f"  Issues: {summary['total_issues']}")
            print(f"  Warnings: {summary['total_warnings']}")

if __name__ == "__main__":
    main()

