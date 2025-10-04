#!/usr/bin/env python3
"""
Unified Monitor - Runs both operational and signal performance monitoring
Single command for complete bot monitoring
"""

import subprocess
import sys
import time
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

# Import existing monitoring modules
sys.path.insert(0, str(Path(__file__).parent))
from monitor_bot import collect_metrics, save_metrics, generate_summary, SERVER, CHECK_INTERVAL_SECONDS, LOCAL_ANALYTICS_DIR
from analyze_signals import analyze_signal_outcomes, analyze_criteria_correlation, generate_tuning_recommendations

# Configuration
SIGNAL_ANALYSIS_INTERVAL_CHECKS = 1  # Run signal analysis every check (5 minutes)
SIGNAL_ANALYSIS_HOURS = 24  # Analyze last 24 hours (tokens need 60min before tracking)
LOCAL_DB_PATH = Path(__file__).parent.parent / "var" / "alerted_tokens.db"
SERVER_DB_PATH = "/opt/callsbotonchain/var/alerted_tokens.db"


def sync_database_from_server():
    """Download latest database from server for signal analysis"""
    print(f"\n  📥 Syncing database from server...")
    
    try:
        # Ensure var directory exists
        LOCAL_DB_PATH.parent.mkdir(exist_ok=True, parents=True)
        
        # Close any existing database file handles
        if LOCAL_DB_PATH.exists():
            try:
                LOCAL_DB_PATH.unlink()
            except Exception as e:
                print(f"  ⚠️  Could not remove old database: {e}")
        
        # Create a SQLite checkpoint on server first to ensure consistency
        print(f"  ⏳ Creating WAL checkpoint on server...")
        checkpoint_cmd = f"ssh {SERVER} 'cd /opt/callsbotonchain && sqlite3 {SERVER_DB_PATH} \"PRAGMA wal_checkpoint(FULL);\"'"
        subprocess.run(checkpoint_cmd, shell=True, capture_output=True, timeout=10)
        
        # Method 1: Try using ssh with cat (more reliable on Windows)
        print(f"  ⏳ Downloading database via SSH stream...")
        ssh_cmd = f'ssh {SERVER} "cat {SERVER_DB_PATH}"'
        
        result = subprocess.run(
            ssh_cmd,
            shell=True,
            capture_output=True,
            timeout=60
        )
        
        if result.returncode == 0 and result.stdout:
            # Write the binary data to file
            with open(LOCAL_DB_PATH, 'wb') as f:
                f.write(result.stdout)
            
            if LOCAL_DB_PATH.exists() and LOCAL_DB_PATH.stat().st_size > 0:
                file_size = LOCAL_DB_PATH.stat().st_size / 1024  # KB
                print(f"  ✅ Database synced successfully ({file_size:.1f} KB)")
                return True
            else:
                print(f"  ⚠️  Database file is empty or missing after download")
                return False
        else:
            error_msg = result.stderr.decode('utf-8', errors='ignore').strip() if result.stderr else "Unknown error"
            print(f"  ⚠️  Database sync failed: {error_msg}")
            
            # Fallback: Try scp with quoted path
            print(f"  ⏳ Trying alternative method (scp)...")
            local_path_unix = str(LOCAL_DB_PATH).replace('\\', '/')
            scp_cmd = f'scp -C {SERVER}:{SERVER_DB_PATH} "{local_path_unix}"'
            
            result = subprocess.run(
                scp_cmd,
                shell=True,
                capture_output=True,
                timeout=60
            )
            
            if result.returncode == 0 and LOCAL_DB_PATH.exists():
                file_size = LOCAL_DB_PATH.stat().st_size / 1024  # KB
                print(f"  ✅ Database synced successfully via scp ({file_size:.1f} KB)")
                return True
            else:
                print(f"  ❌ Both sync methods failed")
                return False
                
    except subprocess.TimeoutExpired:
        print(f"  ⚠️  Database sync timed out (network issue?)")
        return False
    except Exception as e:
        print(f"  ⚠️  Database sync error: {e}")
        return False


def run_signal_analysis(hours: int = 6):
    """Run signal performance analysis for recent alerts"""
    print(f"\n{'=' * 80}")
    print("SIGNAL PERFORMANCE ANALYSIS (RECENT ALERTS)")
    print(f"{'=' * 80}\n")
    
    if not LOCAL_DB_PATH.exists():
        print("❌ Local database not found. Attempting to sync from server...\n")
        if not sync_database_from_server():
            print("⚠️  Cannot run signal analysis without database")
            return
    
    try:
        # Convert hours to days for the analyzer (it expects days)
        days_equivalent = hours / 24.0
        
        # Run outcome analysis
        outcome_data = analyze_signal_outcomes(LOCAL_DB_PATH, days_equivalent)
        
        if 'error' in outcome_data:
            print(f"⚠️  {outcome_data['error']}")
            return
        
        # Print compact summary
        print(f"📊 Performance Summary (Last {hours} hours):")
        print(f"  Total Signals: {outcome_data['total_signals']}")
        
        if outcome_data['total_signals'] == 0:
            print(f"  ⚠️  No signals in last {hours} hours")
            return
            
        print(f"  Win Rate: {outcome_data['win_rate']}%")
        print(f"  Wins: {outcome_data['wins']} | Losses: {outcome_data['losses']}")
        
        print(f"\n🎯 Top Outcomes:")
        sorted_outcomes = sorted(outcome_data['outcome_distribution'].items(), key=lambda x: -x[1])
        for outcome, count in sorted_outcomes[:5]:
            pct = round(count / outcome_data['total_signals'] * 100, 1)
            avg_gain = outcome_data['avg_gain_by_outcome'].get(outcome, 0)
            print(f"  {outcome:20} : {count:3} ({pct:5.1f}%) | Avg Gain: {avg_gain:+6.1f}%")
        
        # Conviction performance
        print(f"\n🎯 Conviction Performance:")
        for conviction, stats in sorted(outcome_data['conviction_performance'].items(), 
                                       key=lambda x: -x[1]['win_rate'])[:3]:
            print(f"  {conviction:20} : Win Rate {stats['win_rate']:5.1f}%")
        
        # Correlation analysis (only if enough data)
        if outcome_data['total_signals'] >= 10:
            correlation_data = analyze_criteria_correlation(LOCAL_DB_PATH, days_equivalent)
        else:
            correlation_data = {'error': 'Not enough signals for correlation'}
        
        if 'error' not in correlation_data:
            print(f"\n💎 Smart Money:")
            sm = correlation_data['smart_money_analysis']
            advantage = sm['smart_money_advantage']
            emoji = '✅' if advantage > 15 else '⚠️' if advantage > 5 else '❌'
            print(f"  Advantage: {advantage:+.1f}% {emoji}")
        
        # Tuning recommendations
        recommendations = generate_tuning_recommendations(outcome_data, correlation_data)
        
        if recommendations:
            print(f"\n🔧 Top Tuning Recommendations:")
            for rec in recommendations[:3]:  # Show top 3
                print(f"  [{rec['priority']:6}] {rec['category']}: {rec['recommendation']}")
        else:
            print(f"\n✅ No tuning needed - system performing well")
        
        print(f"\n{'=' * 80}")
        
    except Exception as e:
        print(f"❌ Error during signal analysis: {e}")


def print_header():
    """Print unified monitor header"""
    print("=" * 80)
    print("UNIFIED BOT MONITOR - REAL-TIME ANALYSIS")
    print("=" * 80)
    print(f"Server: {SERVER}")
    print(f"Analytics: {LOCAL_ANALYTICS_DIR.absolute()}")
    print(f"Operational Check: Every {CHECK_INTERVAL_SECONDS}s ({CHECK_INTERVAL_SECONDS//60} min)")
    print(f"Signal Analysis: Every {SIGNAL_ANALYSIS_INTERVAL_CHECKS} check(s) - Last {SIGNAL_ANALYSIS_HOURS}h")
    print("=" * 80)
    print("\nMonitoring:")
    print("  ✅ Container health and restarts")
    print("  ✅ Budget usage and efficiency")
    print("  ✅ Feed health and cycling")
    print("  ✅ System resources (disk, memory, CPU)")
    print("  ✅ Recent signal outcomes (pumps/rugs)")
    print("  ✅ Real-time win rate tracking")
    print("  ✅ Tuning recommendations")
    print("\nPress Ctrl+C to stop\n")
    print("=" * 80)


def main():
    """Main unified monitoring loop"""
    print_header()
    
    check_count = 0
    last_signal_analysis = 0
    
    try:
        while True:
            check_count += 1
            print(f"\n[Check #{check_count}] {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            # Run operational metrics collection
            try:
                print("\n📊 OPERATIONAL METRICS")
                print("-" * 40)
                data = collect_metrics()
                save_metrics(data)
                
                # Generate summary every 10 checks
                if check_count % 10 == 0:
                    summary = generate_summary()
                    if summary:
                        print(f"\n📈 Daily Summary: Avg Health Score {summary['avg_health_score']:.1f}/100")
                
            except Exception as e:
                print(f"  ❌ Error collecting operational metrics: {e}")
            
            # Run signal analysis every check (real-time monitoring)
            if check_count % SIGNAL_ANALYSIS_INTERVAL_CHECKS == 0:
                try:
                    # Sync database first
                    if sync_database_from_server():
                        run_signal_analysis(hours=SIGNAL_ANALYSIS_HOURS)
                        last_signal_analysis = check_count
                except Exception as e:
                    print(f"  ❌ Error in signal analysis: {e}")
            
            # Wait for next check
            print(f"\n⏳ Waiting {CHECK_INTERVAL_SECONDS}s until next check...")
            print("=" * 80)
            time.sleep(CHECK_INTERVAL_SECONDS)
            
    except KeyboardInterrupt:
        print("\n\n⛔ Monitoring stopped by user")
        print(f"\nFinal Statistics:")
        print(f"  Total checks performed: {check_count}")
        print(f"  Signal analyses run: {(check_count // SIGNAL_ANALYSIS_INTERVAL_CHECKS) + 1}")
        
        # Generate final summaries
        try:
            summary = generate_summary()
            if summary:
                print(f"\n📊 Operational Summary:")
                print(f"  Health Score: {summary['avg_health_score']:.1f}/100")
                print(f"  Issues: {summary['total_issues']}")
                print(f"  Warnings: {summary['total_warnings']}")
        except:
            pass
        
        print(f"\n💾 Data saved to: {LOCAL_ANALYTICS_DIR}")
        if LOCAL_DB_PATH.exists():
            print(f"📊 Signal database: {LOCAL_DB_PATH}")


if __name__ == "__main__":
    main()

