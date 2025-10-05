#!/usr/bin/env python3
"""
Metrics Analyzer - Analyze collected monitoring data for trends and insights
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import statistics

ANALYTICS_DIR = Path(__file__).parent.parent / "analytics"

def load_metrics(date_str=None):
    """Load metrics from a specific date or today"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    metrics_file = ANALYTICS_DIR / f"metrics_{date_str}.jsonl"
    
    if not metrics_file.exists():
        print(f"❌ No metrics found for {date_str}")
        return []
    
    entries = []
    with open(metrics_file, 'r') as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except:
                pass
    
    return entries

def load_health_history():
    """Load health history"""
    health_file = ANALYTICS_DIR / "health_history.jsonl"
    
    if not health_file.exists():
        return []
    
    entries = []
    with open(health_file, 'r') as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except:
                pass
    
    return entries

def analyze_health_trends():
    """Analyze health score trends over time"""
    history = load_health_history()
    
    if not history:
        print("No health history available")
        return
    
    print("\n" + "=" * 60)
    print("HEALTH TRENDS")
    print("=" * 60)
    
    # Overall statistics
    scores = [e['score'] for e in history]
    statuses = [e['status'] for e in history]
    
    print(f"\nOverall Statistics ({len(history)} checks):")
    print(f"  Average Score: {statistics.mean(scores):.1f}/100")
    print(f"  Median Score: {statistics.median(scores):.1f}/100")
    print(f"  Min Score: {min(scores)}/100")
    print(f"  Max Score: {max(scores)}/100")
    print(f"  Std Dev: {statistics.stdev(scores):.1f}" if len(scores) > 1 else "  Std Dev: N/A")
    
    # Status distribution
    status_counts = Counter(statuses)
    print(f"\nStatus Distribution:")
    for status, count in status_counts.most_common():
        pct = 100 * count / len(statuses)
        print(f"  {status:10} : {count:4} ({pct:5.1f}%)")
    
    # Recent trend (last 50 checks)
    recent = history[-50:]
    recent_scores = [e['score'] for e in recent]
    
    if len(recent_scores) > 1:
        trend = "improving" if recent_scores[-1] > recent_scores[0] else "degrading" if recent_scores[-1] < recent_scores[0] else "stable"
        print(f"\nRecent Trend (last 50 checks): {trend}")
        print(f"  First: {recent_scores[0]}/100")
        print(f"  Last: {recent_scores[-1]}/100")
        print(f"  Change: {recent_scores[-1] - recent_scores[0]:+d}")
    
    # Issue frequency
    total_issues = sum(e.get('issues_count', 0) for e in history)
    total_warnings = sum(e.get('warnings_count', 0) for e in history)
    
    print(f"\nIssue Frequency:")
    print(f"  Total Issues: {total_issues}")
    print(f"  Total Warnings: {total_warnings}")
    print(f"  Avg Issues per Check: {total_issues/len(history):.2f}")
    print(f"  Avg Warnings per Check: {total_warnings/len(history):.2f}")

def analyze_signal_quality(entries):
    """Analyze signal quality metrics"""
    print("\n" + "=" * 60)
    print("SIGNAL QUALITY ANALYSIS")
    print("=" * 60)
    
    if not entries:
        print("No data available")
        return
    
    # Extract API stats over time
    total_alerts = []
    tracking_counts = []
    alerts_24h = []
    
    for entry in entries:
        if entry.get('api_stats'):
            stats = entry['api_stats']
            total_alerts.append(stats.get('total_alerts', 0))
            tracking_counts.append(stats.get('tracking_count', 0))
            alerts_24h.append(stats.get('alerts_24h', 0))
    
    if total_alerts:
        print(f"\nAlert Generation:")
        print(f"  Start: {total_alerts[0]} alerts")
        print(f"  End: {total_alerts[-1]} alerts")
        print(f"  New Alerts: {total_alerts[-1] - total_alerts[0]}")
        print(f"  Rate: {(total_alerts[-1] - total_alerts[0]) / len(entries):.2f} per check")
    
    # Database stats over time
    db_stats_list = [e.get('database_stats') for e in entries if e.get('database_stats')]
    
    if db_stats_list:
        latest = db_stats_list[-1]
        print(f"\nDatabase Statistics (latest):")
        print(f"  Total Alerts: {latest.get('total_alerts', 0)}")
        print(f"  Smart Money: {latest.get('smart_money', 0)} ({100*latest.get('smart_money', 0)/max(latest.get('total_alerts', 1), 1):.1f}%)")
        print(f"  Avg Score: {latest.get('avg_score', 0):.1f}/10")

def analyze_budget_efficiency(entries):
    """Analyze budget usage patterns"""
    print("\n" + "=" * 60)
    print("BUDGET EFFICIENCY ANALYSIS")
    print("=" * 60)
    
    if not entries:
        print("No data available")
        return
    
    budget_data = [e.get('budget_status') for e in entries if e.get('budget_status')]
    
    if not budget_data:
        print("No budget data available")
        return
    
    daily_used = [b.get('daily_used', 0) for b in budget_data]
    daily_pcts = [b.get('daily_percent', 0) for b in budget_data]
    
    print(f"\nBudget Usage Trend:")
    print(f"  Start: {daily_used[0]} calls ({daily_pcts[0]:.1f}%)")
    print(f"  End: {daily_used[-1]} calls ({daily_pcts[-1]:.1f}%)")
    print(f"  Rate: {(daily_used[-1] - daily_used[0]) / len(daily_used):.1f} calls per check")
    
    # Estimate time to exhaustion
    if len(daily_used) > 1:
        latest = budget_data[-1]
        rate_per_check = (daily_used[-1] - daily_used[0]) / len(daily_used)
        remaining = latest.get('daily_max', 10000) - daily_used[-1]
        
        if rate_per_check > 0:
            checks_until_exhaust = remaining / rate_per_check
            print(f"\nProjection:")
            print(f"  Remaining: {remaining} calls")
            print(f"  Checks until exhaustion: ~{checks_until_exhaust:.0f}")
        
        # Zero-miss mode status
        zero_miss = latest.get('zero_miss_mode', False)
        print(f"  Zero-Miss Mode: {'✅ ON' if zero_miss else '❌ OFF'}")

def analyze_system_resources(entries):
    """Analyze system resource usage"""
    print("\n" + "=" * 60)
    print("SYSTEM RESOURCES ANALYSIS")
    print("=" * 60)
    
    if not entries:
        print("No data available")
        return
    
    resource_data = [e.get('resource_usage') for e in entries if e.get('resource_usage')]
    
    if not resource_data:
        print("No resource data available")
        return
    
    disk_usage = [r.get('disk_usage_percent', 0) for r in resource_data]
    mem_usage = [r.get('memory_usage_percent', 0) for r in resource_data]
    
    print(f"\nDisk Usage:")
    print(f"  Average: {statistics.mean(disk_usage):.1f}%")
    print(f"  Min: {min(disk_usage)}%")
    print(f"  Max: {max(disk_usage)}%")
    print(f"  Trend: {disk_usage[-1] - disk_usage[0]:+d}% over period")
    
    print(f"\nMemory Usage:")
    print(f"  Average: {statistics.mean(mem_usage):.1f}%")
    print(f"  Min: {min(mem_usage):.1f}%")
    print(f"  Max: {max(mem_usage):.1f}%")

def analyze_feed_performance(entries):
    """Analyze feed health and performance"""
    print("\n" + "=" * 60)
    print("FEED PERFORMANCE ANALYSIS")
    print("=" * 60)
    
    if not entries:
        print("No data available")
        return
    
    feed_data = [e.get('feed_health') for e in entries if e.get('feed_health')]
    heartbeats = [e.get('last_heartbeat') for e in entries if e.get('last_heartbeat')]
    
    if feed_data:
        latest = feed_data[-1]
        print(f"\nFeed Health (latest):")
        print(f"  Status: {latest.get('status', 'unknown')}")
        print(f"  Current Cycle: {latest.get('current_cycle', 'unknown')}")
        print(f"  Feed Items: {latest.get('feed_items', 0)}")
        print(f"  Processing Rate: {latest.get('processing_rate', 0):.1f}%")
        print(f"  Error Rate: {latest.get('error_rate', 0):.1f}%")
    
    if heartbeats:
        # Analyze cycle distribution
        cycles = [hb.get('cycle') for hb in heartbeats if hb.get('cycle')]
        feed_items = [hb.get('feed_items', 0) for hb in heartbeats]
        processed_counts = [hb.get('processed_count', 0) for hb in heartbeats]
        
        cycle_counts = Counter(cycles)
        print(f"\nCycle Distribution:")
        for cycle, count in cycle_counts.items():
            pct = 100 * count / len(cycles) if cycles else 0
            print(f"  {cycle}: {count} ({pct:.1f}%)")
        
        if feed_items:
            print(f"\nFeed Items per Cycle:")
            print(f"  Average: {statistics.mean(feed_items):.1f}")
            print(f"  Min: {min(feed_items)}")
            print(f"  Max: {max(feed_items)}")
        
        if any(processed_counts):
            total_processed = sum(processed_counts)
            total_items = sum(feed_items)
            filter_rate = 100 * (1 - total_processed / max(total_items, 1))
            print(f"\nFiltering Efficiency:")
            print(f"  Total Items: {total_items}")
            print(f"  Total Processed: {total_processed}")
            print(f"  Filter Rate: {filter_rate:.1f}% (items rejected)")

def identify_anomalies(entries):
    """Identify anomalies and potential issues"""
    print("\n" + "=" * 60)
    print("ANOMALY DETECTION")
    print("=" * 60)
    
    if not entries:
        print("No data available")
        return
    
    anomalies = []
    
    # Check for score drops
    for i in range(1, len(entries)):
        prev_score = entries[i-1].get('health_analysis', {}).get('score', 0)
        curr_score = entries[i].get('health_analysis', {}).get('score', 0)
        
        if curr_score < prev_score - 30:
            anomalies.append({
                "type": "Score Drop",
                "time": entries[i]['timestamp'],
                "details": f"Score dropped from {prev_score} to {curr_score}"
            })
    
    # Check for restarts
    for entry in entries:
        restarts = entry.get('container_restarts', [])
        total_restarts = sum(r.get('restarts', 0) for r in restarts)
        if total_restarts > 0:
            anomalies.append({
                "type": "Container Restart",
                "time": entry['timestamp'],
                "details": f"{total_restarts} restart(s) detected"
            })
    
    # Check for critical errors
    for entry in entries:
        errors = entry.get('recent_errors', {})
        if errors.get('critical_error_count', 0) > 5:
            anomalies.append({
                "type": "High Error Count",
                "time": entry['timestamp'],
                "details": f"{errors['critical_error_count']} critical errors"
            })
    
    if anomalies:
        print(f"\nFound {len(anomalies)} anomalies:")
        for i, anomaly in enumerate(anomalies[:10], 1):
            print(f"\n{i}. {anomaly['type']}")
            print(f"   Time: {anomaly['time']}")
            print(f"   Details: {anomaly['details']}")
        
        if len(anomalies) > 10:
            print(f"\n... and {len(anomalies) - 10} more")
    else:
        print("\n✅ No anomalies detected")

def generate_recommendations(entries):
    """Generate optimization recommendations"""
    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)
    
    if not entries:
        print("Insufficient data for recommendations")
        return
    
    recommendations = []
    
    latest = entries[-1]
    
    # Budget recommendations
    budget = latest.get('budget_status', {})
    if budget:
        daily_pct = budget.get('daily_percent', 0)
        if daily_pct < 50:
            recommendations.append({
                "priority": "LOW",
                "category": "Budget",
                "recommendation": "Budget underutilized - consider increasing tracking frequency",
                "action": "Decrease TRACK_INTERVAL_MIN or increase TRACK_BATCH_SIZE"
            })
        elif daily_pct > 85:
            recommendations.append({
                "priority": "HIGH",
                "category": "Budget",
                "recommendation": "Budget usage critical - increase limit or reduce tracking",
                "action": "Increase BUDGET_PER_DAY_MAX or increase TRACK_INTERVAL_MIN"
            })
    
    # Resource recommendations
    resources = latest.get('resource_usage', {})
    if resources:
        disk_pct = resources.get('disk_usage_percent', 0)
        if disk_pct > 80:
            recommendations.append({
                "priority": "HIGH",
                "category": "Disk",
                "recommendation": "Disk space running low",
                "action": "Run: docker system prune -af && docker image prune -af"
            })
    
    # Health recommendations
    health = latest.get('health_analysis', {})
    if health.get('score', 100) < 75:
        recommendations.append({
            "priority": "MEDIUM",
            "category": "Health",
            "recommendation": "Health score below optimal",
            "action": "Review issues and warnings, check ops/TROUBLESHOOTING.md"
        })
    
    # Signal quality recommendations
    db_stats = latest.get('database_stats', {})
    if db_stats:
        smart_pct = 100 * db_stats.get('smart_money', 0) / max(db_stats.get('total_alerts', 1), 1)
        if smart_pct < 40:
            recommendations.append({
                "priority": "MEDIUM",
                "category": "Signal Quality",
                "recommendation": "Smart money detection rate low",
                "action": "Verify smart money detection logic, check feed alternation"
            })
    
    if recommendations:
        print()
        for rec in sorted(recommendations, key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[x["priority"]]):
            print(f"[{rec['priority']:6}] {rec['category']}")
            print(f"  {rec['recommendation']}")
            print(f"  Action: {rec['action']}")
            print()
    else:
        print("\n✅ System is running optimally - no recommendations at this time")

def main():
    """Main analysis function"""
    if not ANALYTICS_DIR.exists():
        print(f"❌ Analytics directory not found: {ANALYTICS_DIR}")
        sys.exit(1)
    
    # Get date from argument or use today
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    
    print("=" * 60)
    print("CALLSBOT METRICS ANALYZER")
    print("=" * 60)
    print(f"Date: {date_str}")
    print()
    
    # Load data
    entries = load_metrics(date_str)
    
    if not entries:
        print(f"No metrics found for {date_str}")
        print("\nAvailable dates:")
        for file in sorted(ANALYTICS_DIR.glob("metrics_*.jsonl")):
            print(f"  - {file.stem.replace('metrics_', '')}")
        sys.exit(1)
    
    print(f"Loaded {len(entries)} metric entries")
    
    # Run analyses
    analyze_health_trends()
    analyze_signal_quality(entries)
    analyze_budget_efficiency(entries)
    analyze_system_resources(entries)
    analyze_feed_performance(entries)
    identify_anomalies(entries)
    generate_recommendations(entries)
    
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()

