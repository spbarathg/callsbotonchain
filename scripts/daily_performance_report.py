#!/usr/bin/env python3
"""
Daily Performance Report for CallsBotOnChain
Analyzes bot health, signal quality, and trading profitability potential
"""
import sys
import os
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_db_connection(db_path: str = "var/alerted_tokens.db"):
    """Connect to the alerts database"""
    return sqlite3.connect(db_path)

def check_bot_health() -> Dict[str, Any]:
    """Check overall bot system health"""
    import subprocess
    
    health = {
        "containers": {},
        "overall_status": "HEALTHY"
    }
    
    try:
        # Check Docker containers
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=callsbot", "--format", "{{.Names}}:{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if ':' in line:
                    name, status = line.split(':', 1)
                    is_healthy = "Up" in status and "unhealthy" not in status.lower()
                    health["containers"][name] = {
                        "status": status,
                        "healthy": is_healthy
                    }
                    if not is_healthy:
                        health["overall_status"] = "DEGRADED"
        else:
            health["overall_status"] = "ERROR"
            health["error"] = "Cannot check containers"
            
    except Exception as e:
        health["overall_status"] = "ERROR"
        health["error"] = str(e)
    
    return health

def analyze_signal_performance(conn: sqlite3.Connection, hours: int = 24) -> Dict[str, Any]:
    """Analyze signal performance over the last N hours"""
    cutoff = datetime.now() - timedelta(hours=hours)
    cutoff_unix = int(cutoff.timestamp())
    
    # Overall stats
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            COUNT(*) as total_signals,
            COUNT(CASE WHEN s.token_address IS NOT NULL THEN 1 END) as tracked,
            COALESCE(AVG(s.max_gain_percent), 0) as avg_gain,
            COALESCE(MAX(s.max_gain_percent), 0) as max_gain,
            COUNT(CASE WHEN s.max_gain_percent > 0 THEN 1 END) as profitable,
            COUNT(CASE WHEN s.max_gain_percent >= 100 THEN 1 END) as x2_plus,
            COUNT(CASE WHEN s.max_gain_percent >= 400 THEN 1 END) as x5_plus,
            COUNT(CASE WHEN s.max_gain_percent >= 900 THEN 1 END) as x10_plus,
            COUNT(CASE WHEN s.is_rug = 1 THEN 1 END) as rugs
        FROM alerted_tokens a
        LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
        WHERE a.alerted_at >= ?
    """, (cutoff_unix,))
    
    row = cursor.fetchone()
    
    total = row[0] if row[0] else 0
    tracked = row[1] if row[1] else 0
    
    stats = {
        "total_signals": total,
        "tracked_signals": tracked,
        "tracking_rate": round(tracked / total * 100, 1) if total > 0 else 0,
        "avg_gain_pct": round(row[2], 2) if row[2] else 0,
        "max_gain_pct": round(row[3], 2) if row[3] else 0,
        "profitable_count": row[4] if row[4] else 0,
        "win_rate_pct": round(row[4] / tracked * 100, 2) if tracked > 0 else 0,
        "x2_plus": row[5] if row[5] else 0,
        "x5_plus": row[6] if row[6] else 0,
        "x10_plus": row[7] if row[7] else 0,
        "rugs": row[8] if row[8] else 0,
        "rug_rate_pct": round(row[8] / tracked * 100, 2) if tracked > 0 else 0
    }
    
    # Performance by score
    cursor.execute("""
        SELECT 
            a.final_score,
            COUNT(*) as count,
            COALESCE(AVG(s.max_gain_percent), 0) as avg_gain,
            COUNT(CASE WHEN s.max_gain_percent > 0 THEN 1 END) as profitable,
            COUNT(CASE WHEN s.max_gain_percent >= 100 THEN 1 END) as x2_plus
        FROM alerted_tokens a
        LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
        WHERE a.alerted_at >= ?
        GROUP BY a.final_score
        ORDER BY a.final_score DESC
    """, (cutoff_unix,))
    
    by_score = {}
    for row in cursor.fetchall():
        score = row[0]
        count = row[1]
        by_score[score] = {
            "count": count,
            "avg_gain_pct": round(row[2], 2),
            "win_rate_pct": round(row[3] / count * 100, 2) if count > 0 else 0,
            "x2_plus": row[4]
        }
    
    stats["by_score"] = by_score
    
    # Top performers
    cursor.execute("""
        SELECT 
            a.token_address,
            a.final_score,
            a.smart_money_detected,
            s.max_gain_percent,
            ROUND((s.max_gain_percent / 100.0) + 1, 2) as multiplier
        FROM alerted_tokens a
        JOIN alerted_token_stats s ON a.token_address = s.token_address
        WHERE a.alerted_at >= ?
        ORDER BY s.max_gain_percent DESC
        LIMIT 10
    """, (cutoff_unix,))
    
    stats["top_performers"] = []
    for row in cursor.fetchall():
        stats["top_performers"].append({
            "token": row[0][:12] + "...",
            "score": row[1],
            "smart_money": bool(row[2]),
            "gain_pct": round(row[3], 2),
            "multiplier": row[4]
        })
    
    return stats

def calculate_trading_profitability(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate potential trading profitability based on signal performance"""
    
    # Trading scenarios
    scenarios = {}
    
    # Scenario 1: Trade ALL signals
    if stats["tracked_signals"] > 0:
        avg_return = (stats["avg_gain_pct"] / 100) + 1  # Convert to multiplier
        scenarios["trade_all"] = {
            "strategy": "Trade every signal with equal size",
            "signals_per_day": stats["total_signals"],
            "win_rate": stats["win_rate_pct"],
            "avg_multiplier": round(avg_return, 3),
            "expected_roi_per_trade": round((avg_return - 1) * 100, 2),
            "risk_level": "HIGH" if stats["rug_rate_pct"] > 10 else "MEDIUM"
        }
    
    # Scenario 2: Trade only score 7+
    score_7_plus = {k: v for k, v in stats.get("by_score", {}).items() if k >= 7}
    if score_7_plus:
        total_7_plus = sum(s["count"] for s in score_7_plus.values())
        weighted_avg_gain = sum(s["avg_gain_pct"] * s["count"] for s in score_7_plus.values()) / total_7_plus if total_7_plus > 0 else 0
        weighted_win_rate = sum(s["win_rate_pct"] * s["count"] for s in score_7_plus.values()) / total_7_plus if total_7_plus > 0 else 0
        
        avg_return = (weighted_avg_gain / 100) + 1
        scenarios["trade_score_7_plus"] = {
            "strategy": "Trade only signals with score 7+",
            "signals_per_day": total_7_plus,
            "win_rate": round(weighted_win_rate, 2),
            "avg_multiplier": round(avg_return, 3),
            "expected_roi_per_trade": round((avg_return - 1) * 100, 2),
            "risk_level": "MEDIUM"
        }
    
    # Scenario 3: Trade only score 9-10
    score_9_plus = {k: v for k, v in stats.get("by_score", {}).items() if k >= 9}
    if score_9_plus:
        total_9_plus = sum(s["count"] for s in score_9_plus.values())
        weighted_avg_gain = sum(s["avg_gain_pct"] * s["count"] for s in score_9_plus.values()) / total_9_plus if total_9_plus > 0 else 0
        weighted_win_rate = sum(s["win_rate_pct"] * s["count"] for s in score_9_plus.values()) / total_9_plus if total_9_plus > 0 else 0
        
        avg_return = (weighted_avg_gain / 100) + 1
        scenarios["trade_score_9_plus"] = {
            "strategy": "Trade only signals with score 9-10 (highest confidence)",
            "signals_per_day": total_9_plus,
            "win_rate": round(weighted_win_rate, 2),
            "avg_multiplier": round(avg_return, 3),
            "expected_roi_per_trade": round((avg_return - 1) * 100, 2),
            "risk_level": "LOW"
        }
    
    # Calculate projected returns
    for scenario_name, scenario in scenarios.items():
        # Simple projection: $100 per trade
        if scenario["signals_per_day"] > 0:
            daily_investment = scenario["signals_per_day"] * 100
            daily_return = daily_investment * scenario["avg_multiplier"]
            daily_profit = daily_return - daily_investment
            
            scenario["projection_100_per_trade"] = {
                "daily_investment": daily_investment,
                "daily_return": round(daily_return, 2),
                "daily_profit": round(daily_profit, 2),
                "weekly_profit": round(daily_profit * 7, 2),
                "monthly_profit": round(daily_profit * 30, 2)
            }
    
    return scenarios

def generate_recommendations(stats: Dict[str, Any], scenarios: Dict[str, Any], health: Dict[str, Any]) -> List[str]:
    """Generate actionable recommendations"""
    recommendations = []
    
    # Bot health recommendations
    if health["overall_status"] != "HEALTHY":
        recommendations.append("🔴 CRITICAL: Bot health is degraded. Check container logs immediately.")
    
    # Data collection recommendations
    if stats["total_signals"] == 0:
        recommendations.append("⚠️ WARNING: No signals in last 24 hours. Check if bot is processing feed.")
    elif stats["tracking_rate"] < 50:
        recommendations.append(f"⚠️ WARNING: Only {stats['tracking_rate']}% of signals have tracking data. Tracker may have issues.")
    
    # Performance recommendations
    if stats["tracked_signals"] >= 10:  # Enough data to analyze
        if stats["win_rate_pct"] < 10:
            recommendations.append(f"🔴 CRITICAL: Win rate is {stats['win_rate_pct']}% (target: 15-20%). Consider raising score threshold or adjusting filters.")
        elif stats["win_rate_pct"] < 15:
            recommendations.append(f"⚠️ WARNING: Win rate is {stats['win_rate_pct']}% (target: 15-20%). Monitor for another 24-48 hours.")
        elif stats["win_rate_pct"] >= 15:
            recommendations.append(f"✅ GOOD: Win rate is {stats['win_rate_pct']}% (within target range 15-20%).")
        
        if stats["rug_rate_pct"] > 15:
            recommendations.append(f"🔴 CRITICAL: Rug rate is {stats['rug_rate_pct']}% (target: <10%). Consider raising MIN_LIQUIDITY_USD.")
        elif stats["rug_rate_pct"] > 10:
            recommendations.append(f"⚠️ WARNING: Rug rate is {stats['rug_rate_pct']}% (target: <10%). Monitor liquidity filters.")
        
        # Average gain recommendations
        avg_multiplier = (stats["avg_gain_pct"] / 100) + 1
        if avg_multiplier < 1.5:
            recommendations.append(f"⚠️ WARNING: Average multiplier is {avg_multiplier:.2f}x (target: 2.5-3.5x). Signals may not be catching early pumps.")
        elif avg_multiplier >= 2.5:
            recommendations.append(f"✅ EXCELLENT: Average multiplier is {avg_multiplier:.2f}x (meets target 2.5-3.5x).")
    else:
        recommendations.append(f"ℹ️ INFO: Only {stats['tracked_signals']} tracked signals. Need 24-48 hours for meaningful analysis.")
    
    # Trading strategy recommendations
    if scenarios:
        best_scenario = max(scenarios.items(), key=lambda x: x[1].get("expected_roi_per_trade", 0))
        if best_scenario[1]["expected_roi_per_trade"] > 50:
            recommendations.append(f"🚀 OPPORTUNITY: '{best_scenario[1]['strategy']}' shows {best_scenario[1]['expected_roi_per_trade']}% avg ROI per trade.")
        elif best_scenario[1]["expected_roi_per_trade"] > 0:
            recommendations.append(f"📊 MODERATE: Best strategy '{best_scenario[1]['strategy']}' shows {best_scenario[1]['expected_roi_per_trade']}% avg ROI per trade.")
        else:
            recommendations.append("🔴 CRITICAL: No profitable trading strategy identified. Do NOT trade until performance improves.")
    
    # Score distribution recommendations
    by_score = stats.get("by_score", {})
    if by_score:
        best_score = max(by_score.items(), key=lambda x: x[1]["win_rate_pct"] if x[1]["count"] >= 3 else 0)
        if best_score[1]["count"] >= 3:
            recommendations.append(f"💡 INSIGHT: Score {best_score[0]} has best win rate ({best_score[1]['win_rate_pct']}%). Focus trading on this tier.")
    
    return recommendations

def print_report(health: Dict[str, Any], stats: Dict[str, Any], scenarios: Dict[str, Any], recommendations: List[str]):
    """Print formatted report to console"""
    
    print("\n" + "="*80)
    print("📊 CALLSBOTONCHAIN - DAILY PERFORMANCE REPORT")
    print("="*80)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Period: Last 24 hours")
    print("="*80)
    
    # Bot Health
    print("\n🏥 BOT HEALTH")
    print("-" * 80)
    print(f"Overall Status: {health['overall_status']}")
    for container, info in health.get("containers", {}).items():
        status_emoji = "✅" if info["healthy"] else "🔴"
        print(f"  {status_emoji} {container}: {info['status']}")
    
    # Signal Performance
    print("\n📈 SIGNAL PERFORMANCE")
    print("-" * 80)
    print(f"Total Signals: {stats['total_signals']}")
    print(f"Tracked Signals: {stats['tracked_signals']} ({stats['tracking_rate']}%)")
    
    if stats['tracked_signals'] > 0:
        print(f"\n📊 Overall Metrics:")
        print(f"  Win Rate: {stats['win_rate_pct']}% ({stats['profitable_count']}/{stats['tracked_signals']})")
        print(f"  Avg Gain: {stats['avg_gain_pct']}% (Multiplier: {(stats['avg_gain_pct']/100)+1:.2f}x)")
        print(f"  Max Gain: {stats['max_gain_pct']}% (Multiplier: {(stats['max_gain_pct']/100)+1:.2f}x)")
        print(f"  Rug Rate: {stats['rug_rate_pct']}% ({stats['rugs']}/{stats['tracked_signals']})")
        print(f"\n🎯 Success Tiers:")
        print(f"  2x+ Gains: {stats['x2_plus']}")
        print(f"  5x+ Gains: {stats['x5_plus']}")
        print(f"  10x+ Gains: {stats['x10_plus']}")
        
        # Performance by score
        if stats.get("by_score"):
            print(f"\n📊 Performance by Score:")
            print(f"  {'Score':<8} {'Count':<8} {'Win Rate':<12} {'Avg Gain':<12} {'2x+':<8}")
            print(f"  {'-'*7} {'-'*7} {'-'*11} {'-'*11} {'-'*7}")
            for score in sorted(stats["by_score"].keys(), reverse=True):
                s = stats["by_score"][score]
                print(f"  {score:<8} {s['count']:<8} {s['win_rate_pct']:<11.1f}% {s['avg_gain_pct']:<11.1f}% {s['x2_plus']:<8}")
        
        # Top performers
        if stats.get("top_performers"):
            print(f"\n🏆 Top Performers:")
            for i, perf in enumerate(stats["top_performers"][:5], 1):
                sm_tag = " [SM]" if perf["smart_money"] else ""
                print(f"  {i}. {perf['token']}: {perf['multiplier']:.2f}x (Score {perf['score']}{sm_tag})")
    
    # Trading Profitability
    if scenarios:
        print("\n💰 TRADING PROFITABILITY ANALYSIS")
        print("-" * 80)
        
        for scenario_name, scenario in scenarios.items():
            print(f"\n📋 {scenario['strategy']}")
            print(f"  Signals/Day: {scenario['signals_per_day']}")
            print(f"  Win Rate: {scenario['win_rate']}%")
            print(f"  Avg Multiplier: {scenario['avg_multiplier']}x")
            print(f"  Expected ROI: {scenario['expected_roi_per_trade']}% per trade")
            print(f"  Risk Level: {scenario['risk_level']}")
            
            if "projection_100_per_trade" in scenario:
                proj = scenario["projection_100_per_trade"]
                print(f"\n  💵 Projection ($100 per trade):")
                print(f"    Daily Investment: ${proj['daily_investment']}")
                print(f"    Daily Return: ${proj['daily_return']}")
                print(f"    Daily Profit: ${proj['daily_profit']}")
                print(f"    Weekly Profit: ${proj['weekly_profit']}")
                print(f"    Monthly Profit: ${proj['monthly_profit']}")
    
    # Recommendations
    print("\n💡 RECOMMENDATIONS")
    print("-" * 80)
    for i, rec in enumerate(recommendations, 1):
        print(f"{i}. {rec}")
    
    print("\n" + "="*80)
    print("Report Complete")
    print("="*80 + "\n")

def save_report_json(health: Dict[str, Any], stats: Dict[str, Any], scenarios: Dict[str, Any], recommendations: List[str], output_dir: str = "analytics"):
    """Save report as JSON for historical tracking"""
    os.makedirs(output_dir, exist_ok=True)
    
    report = {
        "generated_at": datetime.now().isoformat(),
        "period_hours": 24,
        "health": health,
        "signal_performance": stats,
        "trading_scenarios": scenarios,
        "recommendations": recommendations
    }
    
    # Save with timestamp
    filename = f"{output_dir}/daily_report_{datetime.now().strftime('%Y-%m-%d')}.json"
    with open(filename, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"✅ Report saved to: {filename}")
    
    # Also save as latest
    latest_filename = f"{output_dir}/latest_daily_report.json"
    with open(latest_filename, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"✅ Latest report saved to: {latest_filename}")
    
    return filename

def main():
    """Main execution"""
    print("\n🔍 Generating Daily Performance Report...")
    
    # Check bot health
    print("  ✓ Checking bot health...")
    health = check_bot_health()
    
    # Analyze signal performance
    print("  ✓ Analyzing signal performance...")
    db_path = os.getenv("ALERTED_TOKENS_DB", "var/alerted_tokens.db")
    
    try:
        conn = get_db_connection(db_path)
        stats = analyze_signal_performance(conn, hours=24)
        conn.close()
    except Exception as e:
        print(f"  ✗ Error accessing database: {e}")
        stats = {
            "total_signals": 0,
            "tracked_signals": 0,
            "tracking_rate": 0,
            "error": str(e)
        }
    
    # Calculate trading profitability
    print("  ✓ Calculating trading scenarios...")
    scenarios = calculate_trading_profitability(stats)
    
    # Generate recommendations
    print("  ✓ Generating recommendations...")
    recommendations = generate_recommendations(stats, scenarios, health)
    
    # Print report
    print_report(health, stats, scenarios, recommendations)
    
    # Save report
    print("\n💾 Saving report...")
    save_report_json(health, stats, scenarios, recommendations)
    
    print("\n✅ Daily Performance Report Complete!")

if __name__ == "__main__":
    main()

