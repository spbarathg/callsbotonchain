#!/usr/bin/env python3
"""
Signal Performance Analyzer - Analyzes signal quality and outcomes
Tracks which alerts pumped/dumped and WHY the bot chose to alert on them
"""

import json
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict, Counter
import statistics

# Local and remote database paths
LOCAL_ANALYTICS_DIR = Path(__file__).parent.parent / "analytics"
LOCAL_DB_PATH = Path(__file__).parent.parent / "var" / "alerted_tokens.db"
SIGNAL_ANALYTICS_FILE = LOCAL_ANALYTICS_DIR / "signal_performance.jsonl"

# Outcome classification thresholds
PUMP_THRESHOLD = 1.5  # 50% gain = pump
BIG_PUMP_THRESHOLD = 3.0  # 3x = big win
DUMP_THRESHOLD = 0.7  # -30% = dump
RUG_THRESHOLD = 0.5  # -50% = likely rug


def get_db_connection(db_path: Path = LOCAL_DB_PATH) -> sqlite3.Connection:
    """Connect to the alerts database"""
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def classify_outcome(first_price: float, peak_price: float, last_price: float, 
                     outcome: Optional[str], peak_drawdown: Optional[float]) -> str:
    """Classify signal outcome based on price action"""
    
    # Check for rug first
    if outcome == 'rug' or (peak_drawdown and peak_drawdown >= 80):
        return 'rug'
    
    if not first_price or first_price <= 0:
        return 'unknown'
    
    # Calculate multiples
    peak_multiple = (peak_price / first_price) if peak_price and peak_price > 0 else 1.0
    current_multiple = (last_price / first_price) if last_price and last_price > 0 else 1.0
    
    # Classification logic
    if peak_multiple >= BIG_PUMP_THRESHOLD:
        if current_multiple >= PUMP_THRESHOLD:
            return 'big_win'  # Hit 3x and held gains
        else:
            return 'pumped_then_dumped'  # Hit 3x but gave it back
    elif peak_multiple >= PUMP_THRESHOLD:
        if current_multiple >= PUMP_THRESHOLD:
            return 'win'  # 50%+ gain and holding
        else:
            return 'pumped_then_faded'  # Pumped but faded
    elif current_multiple <= RUG_THRESHOLD:
        return 'loss'  # Down 50%+
    elif current_multiple <= DUMP_THRESHOLD:
        return 'small_loss'  # Down 30%+
    elif current_multiple >= 1.1:
        return 'small_win'  # Up 10%+
    else:
        return 'flat'  # Sideways


def analyze_signal_outcomes(db_path: Path = LOCAL_DB_PATH, days: float = 7) -> Dict[str, Any]:
    """Analyze outcomes of recent signals (days can be fractional for hours)"""
    
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Get recent alerts with full tracking data (supports fractional days for hours)
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    
    query = """
    SELECT 
        a.token_address,
        a.alerted_at,
        a.final_score,
        a.smart_money_detected,
        a.conviction_type,
        s.first_price_usd,
        s.peak_price_usd,
        s.last_price_usd,
        s.first_market_cap_usd,
        s.peak_market_cap_usd,
        s.last_market_cap_usd,
        s.peak_price_at,
        s.outcome,
        s.peak_drawdown_pct,
        s.last_checked_at
    FROM alerted_tokens a
    LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
    WHERE a.alerted_at >= ?
    ORDER BY a.alerted_at DESC
    """
    
    cursor.execute(query, (cutoff_date,))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return {"error": "No signals found in the specified period"}
    
    # Analyze each signal
    signals = []
    outcome_counts = Counter()
    score_by_outcome = defaultdict(list)
    conviction_by_outcome = defaultdict(list)
    smart_money_by_outcome = defaultdict(int)
    
    total_by_conviction = Counter()
    wins_by_conviction = Counter()
    
    for row in rows:
        # Parse row data
        token = row['token_address']
        alerted_at = row['alerted_at']
        score = row['final_score'] or 0
        smart_money = bool(row['smart_money_detected'])
        conviction = row['conviction_type'] or 'unknown'
        
        first_price = row['first_price_usd'] or 0
        peak_price = row['peak_price_usd'] or 0
        last_price = row['last_price_usd'] or 0
        first_mcap = row['first_market_cap_usd'] or 0
        peak_mcap = row['peak_market_cap_usd'] or 0
        last_mcap = row['last_market_cap_usd'] or 0
        peak_price_at = row['peak_price_at']
        outcome_flag = row['outcome']
        peak_drawdown = row['peak_drawdown_pct']
        last_checked = row['last_checked_at']
        
        # Calculate time to peak
        time_to_peak = None
        if alerted_at and peak_price_at:
            try:
                alert_dt = datetime.strptime(alerted_at, '%Y-%m-%d %H:%M:%S')
                peak_dt = datetime.strptime(peak_price_at, '%Y-%m-%d %H:%M:%S')
                time_to_peak = int((peak_dt - alert_dt).total_seconds() / 60)  # minutes
            except:
                pass
        
        # Calculate age
        age_hours = None
        if alerted_at:
            try:
                alert_dt = datetime.strptime(alerted_at, '%Y-%m-%d %H:%M:%S')
                age_hours = (datetime.now() - alert_dt).total_seconds() / 3600
            except:
                pass
        
        # Classify outcome
        outcome_class = classify_outcome(first_price, peak_price, last_price, outcome_flag, peak_drawdown)
        
        # Calculate gains
        peak_gain_pct = ((peak_price / first_price) - 1) * 100 if first_price and peak_price else 0
        current_gain_pct = ((last_price / first_price) - 1) * 100 if first_price and last_price else 0
        
        signal_data = {
            'token': token,
            'alerted_at': alerted_at,
            'age_hours': round(age_hours, 1) if age_hours else None,
            'score': score,
            'smart_money': smart_money,
            'conviction': conviction,
            'first_price': first_price,
            'peak_price': peak_price,
            'last_price': last_price,
            'first_mcap': first_mcap,
            'peak_mcap': peak_mcap,
            'last_mcap': last_mcap,
            'peak_gain_pct': round(peak_gain_pct, 1),
            'current_gain_pct': round(current_gain_pct, 1),
            'time_to_peak_min': time_to_peak,
            'outcome': outcome_class,
            'peak_drawdown': round(peak_drawdown, 1) if peak_drawdown else None
        }
        
        signals.append(signal_data)
        
        # Aggregate statistics
        outcome_counts[outcome_class] += 1
        score_by_outcome[outcome_class].append(score)
        conviction_by_outcome[outcome_class].append(conviction)
        if smart_money:
            smart_money_by_outcome[outcome_class] += 1
        
        # Conviction stats
        total_by_conviction[conviction] += 1
        if outcome_class in ('win', 'big_win', 'small_win'):
            wins_by_conviction[conviction] += 1
    
    # Calculate summary statistics
    total_signals = len(signals)
    
    wins = outcome_counts['win'] + outcome_counts['big_win'] + outcome_counts['small_win']
    losses = outcome_counts['loss'] + outcome_counts['small_loss'] + outcome_counts['rug']
    win_rate = (wins / total_signals * 100) if total_signals > 0 else 0
    
    # Average gains by outcome
    avg_gain_by_outcome = {}
    for outcome_class, count in outcome_counts.items():
        gains = [s['peak_gain_pct'] for s in signals if s['outcome'] == outcome_class and s['peak_gain_pct']]
        avg_gain_by_outcome[outcome_class] = round(statistics.mean(gains), 1) if gains else 0
    
    # Score analysis
    avg_score_by_outcome = {}
    for outcome_class, scores in score_by_outcome.items():
        avg_score_by_outcome[outcome_class] = round(statistics.mean(scores), 1) if scores else 0
    
    # Conviction analysis
    conviction_performance = {}
    for conviction in total_by_conviction:
        total = total_by_conviction[conviction]
        wins_count = wins_by_conviction.get(conviction, 0)
        conviction_performance[conviction] = {
            'total': total,
            'wins': wins_count,
            'win_rate': round(wins_count / total * 100, 1) if total > 0 else 0
        }
    
    # Time to peak analysis
    time_to_peak_data = [s['time_to_peak_min'] for s in signals if s['time_to_peak_min'] and s['outcome'] in ('win', 'big_win')]
    avg_time_to_peak = round(statistics.mean(time_to_peak_data), 0) if time_to_peak_data else None
    
    return {
        'period_days': days,
        'total_signals': total_signals,
        'win_rate': round(win_rate, 1),
        'wins': wins,
        'losses': losses,
        'outcome_distribution': dict(outcome_counts),
        'avg_gain_by_outcome': avg_gain_by_outcome,
        'avg_score_by_outcome': avg_score_by_outcome,
        'conviction_performance': conviction_performance,
        'avg_time_to_peak_minutes': avg_time_to_peak,
        'signals': signals[:50]  # Top 50 most recent
    }


def analyze_criteria_correlation(db_path: Path = LOCAL_DB_PATH, days: float = 7) -> Dict[str, Any]:
    """Analyze which criteria correlate with winning signals (days can be fractional)"""
    
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    
    # Get signals with outcomes
    query = """
    SELECT 
        a.final_score,
        a.smart_money_detected,
        a.conviction_type,
        s.first_price_usd,
        s.peak_price_usd,
        s.last_price_usd,
        s.first_market_cap_usd,
        s.outcome,
        s.peak_drawdown_pct
    FROM alerted_tokens a
    LEFT JOIN alerted_token_stats s ON a.token_address = s.token_address
    WHERE a.alerted_at >= ?
    AND s.first_price_usd > 0
    AND s.peak_price_usd > 0
    """
    
    cursor.execute(query, (cutoff_date,))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return {"error": "Insufficient data"}
    
    # Analyze correlations
    score_wins = []
    score_losses = []
    
    smart_money_wins = 0
    smart_money_losses = 0
    no_smart_money_wins = 0
    no_smart_money_losses = 0
    
    mcap_ranges = {
        'micro (<100k)': {'wins': 0, 'losses': 0},
        'small (100k-500k)': {'wins': 0, 'losses': 0},
        'mid (500k-2M)': {'wins': 0, 'losses': 0},
        'large (>2M)': {'wins': 0, 'losses': 0}
    }
    
    for row in rows:
        score = row['final_score'] or 0
        smart_money = bool(row['smart_money_detected'])
        first_price = row['first_price_usd'] or 0
        peak_price = row['peak_price_usd'] or 0
        last_price = row['last_price_usd'] or 0
        first_mcap = row['first_market_cap_usd'] or 0
        outcome_flag = row['outcome']
        peak_drawdown = row['peak_drawdown_pct']
        
        outcome_class = classify_outcome(first_price, peak_price, last_price, outcome_flag, peak_drawdown)
        is_win = outcome_class in ('win', 'big_win', 'small_win')
        is_loss = outcome_class in ('loss', 'small_loss', 'rug')
        
        # Score correlation
        if is_win:
            score_wins.append(score)
        elif is_loss:
            score_losses.append(score)
        
        # Smart money correlation
        if smart_money:
            if is_win:
                smart_money_wins += 1
            elif is_loss:
                smart_money_losses += 1
        else:
            if is_win:
                no_smart_money_wins += 1
            elif is_loss:
                no_smart_money_losses += 1
        
        # Market cap correlation
        if first_mcap > 0:
            if first_mcap < 100_000:
                mcap_key = 'micro (<100k)'
            elif first_mcap < 500_000:
                mcap_key = 'small (100k-500k)'
            elif first_mcap < 2_000_000:
                mcap_key = 'mid (500k-2M)'
            else:
                mcap_key = 'large (>2M)'
            
            if is_win:
                mcap_ranges[mcap_key]['wins'] += 1
            elif is_loss:
                mcap_ranges[mcap_key]['losses'] += 1
    
    # Calculate correlation metrics
    avg_score_wins = round(statistics.mean(score_wins), 1) if score_wins else 0
    avg_score_losses = round(statistics.mean(score_losses), 1) if score_losses else 0
    
    smart_money_win_rate = round(smart_money_wins / (smart_money_wins + smart_money_losses) * 100, 1) if (smart_money_wins + smart_money_losses) > 0 else 0
    no_smart_money_win_rate = round(no_smart_money_wins / (no_smart_money_wins + no_smart_money_losses) * 100, 1) if (no_smart_money_wins + no_smart_money_losses) > 0 else 0
    
    mcap_win_rates = {}
    for mcap_range, counts in mcap_ranges.items():
        total = counts['wins'] + counts['losses']
        mcap_win_rates[mcap_range] = {
            'win_rate': round(counts['wins'] / total * 100, 1) if total > 0 else 0,
            'sample_size': total
        }
    
    return {
        'score_analysis': {
            'avg_score_winners': avg_score_wins,
            'avg_score_losers': avg_score_losses,
            'score_difference': round(avg_score_wins - avg_score_losses, 1)
        },
        'smart_money_analysis': {
            'smart_money_win_rate': smart_money_win_rate,
            'no_smart_money_win_rate': no_smart_money_win_rate,
            'smart_money_advantage': round(smart_money_win_rate - no_smart_money_win_rate, 1)
        },
        'market_cap_analysis': mcap_win_rates
    }


def generate_tuning_recommendations(outcome_analysis: Dict[str, Any], 
                                   correlation_analysis: Dict[str, Any]) -> List[Dict[str, str]]:
    """Generate specific tuning recommendations based on performance data"""
    
    recommendations = []
    
    # Win rate analysis
    win_rate = outcome_analysis.get('win_rate', 0)
    if win_rate < 30:
        recommendations.append({
            'priority': 'HIGH',
            'category': 'Win Rate',
            'issue': f'Low win rate: {win_rate}%',
            'recommendation': 'Increase HIGH_CONFIDENCE_SCORE threshold to be more selective',
            'action': 'Consider raising HIGH_CONFIDENCE_SCORE from current to +1 or +2'
        })
    elif win_rate < 45:
        recommendations.append({
            'priority': 'MEDIUM',
            'category': 'Win Rate',
            'issue': f'Below-target win rate: {win_rate}%',
            'recommendation': 'Review and tighten gating criteria (liquidity, volume, score)',
            'action': 'Increase MIN_LIQUIDITY_USD or VOL_24H_MIN_FOR_ALERT by 20%'
        })
    
    # Score analysis
    score_analysis = correlation_analysis.get('score_analysis', {})
    score_diff = score_analysis.get('score_difference', 0)
    if score_diff < 0.5:
        recommendations.append({
            'priority': 'HIGH',
            'category': 'Scoring',
            'issue': f'Score barely differentiates winners from losers (diff: {score_diff})',
            'recommendation': 'Scoring logic needs improvement - weights are off',
            'action': 'Review score_token() function weights for momentum, volume, smart money'
        })
    
    # Smart money analysis
    sm_analysis = correlation_analysis.get('smart_money_analysis', {})
    sm_advantage = sm_analysis.get('smart_money_advantage', 0)
    if sm_advantage < 10:
        recommendations.append({
            'priority': 'MEDIUM',
            'category': 'Smart Money',
            'issue': f'Smart money signals not performing better (advantage: {sm_advantage}%)',
            'recommendation': 'Smart money detection may have false positives',
            'action': 'Review feed alternation logic or increase smart money bonus in scoring'
        })
    elif sm_advantage > 20:
        recommendations.append({
            'priority': 'LOW',
            'category': 'Smart Money',
            'issue': f'Smart money signals strong (advantage: {sm_advantage}%)',
            'recommendation': 'Consider requiring smart money for all alerts',
            'action': 'Set REQUIRE_SMART_MONEY_FOR_ALERT=true in config'
        })
    
    # Conviction type analysis
    conviction_perf = outcome_analysis.get('conviction_performance', {})
    for conviction, stats in conviction_perf.items():
        if stats['total'] >= 5:  # Only if enough samples
            if stats['win_rate'] < 35:
                recommendations.append({
                    'priority': 'MEDIUM',
                    'category': 'Conviction Type',
                    'issue': f'{conviction} conviction underperforming: {stats["win_rate"]}% win rate',
                    'recommendation': f'Disable or tighten criteria for {conviction} conviction alerts',
                    'action': f'Review why {conviction} signals are failing - may need higher thresholds'
                })
    
    # Market cap analysis
    mcap_analysis = correlation_analysis.get('market_cap_analysis', {})
    best_mcap_range = None
    best_win_rate = 0
    for mcap_range, data in mcap_analysis.items():
        if data['sample_size'] >= 3 and data['win_rate'] > best_win_rate:
            best_win_rate = data['win_rate']
            best_mcap_range = mcap_range
    
    if best_mcap_range and best_win_rate > win_rate + 15:
        recommendations.append({
            'priority': 'LOW',
            'category': 'Market Cap',
            'issue': f'{best_mcap_range} range performs best ({best_win_rate}% vs {win_rate}% overall)',
            'recommendation': f'Consider focusing more on {best_mcap_range} tokens',
            'action': 'Adjust MAX_MARKET_CAP_FOR_DEFAULT_ALERT to favor this range'
        })
    
    # Time to peak analysis
    avg_ttp = outcome_analysis.get('avg_time_to_peak_minutes')
    if avg_ttp and avg_ttp < 30:
        recommendations.append({
            'priority': 'LOW',
            'category': 'Timing',
            'issue': f'Winners pump quickly (avg {avg_ttp} min to peak)',
            'recommendation': 'Consider shorter tracking intervals to catch momentum early',
            'action': 'Reduce TRACK_INTERVAL_MIN to capture fast movers'
        })
    
    # Sort by priority
    priority_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
    recommendations.sort(key=lambda x: priority_order[x['priority']])
    
    return recommendations


def print_signal_analysis(days: int = 7, db_path: Path = LOCAL_DB_PATH):
    """Print comprehensive signal performance analysis"""
    
    print("=" * 80)
    print("SIGNAL PERFORMANCE ANALYZER")
    print("=" * 80)
    print(f"Analyzing signals from last {days} days\n")
    
    # Outcome analysis
    print("=" * 80)
    print("OUTCOME ANALYSIS")
    print("=" * 80)
    
    outcome_data = analyze_signal_outcomes(db_path, days)
    
    if 'error' in outcome_data:
        print(f"❌ {outcome_data['error']}")
        return
    
    print(f"\n📊 Overall Performance:")
    print(f"  Total Signals: {outcome_data['total_signals']}")
    print(f"  Win Rate: {outcome_data['win_rate']}%")
    print(f"  Wins: {outcome_data['wins']}")
    print(f"  Losses: {outcome_data['losses']}")
    
    print(f"\n📈 Outcome Distribution:")
    for outcome, count in sorted(outcome_data['outcome_distribution'].items(), key=lambda x: -x[1]):
        pct = round(count / outcome_data['total_signals'] * 100, 1)
        avg_gain = outcome_data['avg_gain_by_outcome'].get(outcome, 0)
        avg_score = outcome_data['avg_score_by_outcome'].get(outcome, 0)
        print(f"  {outcome:20} : {count:3} ({pct:5.1f}%) | Avg Gain: {avg_gain:+6.1f}% | Avg Score: {avg_score:.1f}")
    
    print(f"\n🎯 Conviction Performance:")
    for conviction, stats in sorted(outcome_data['conviction_performance'].items(), key=lambda x: -x[1]['win_rate']):
        print(f"  {conviction:20} : {stats['total']:3} signals | Win Rate: {stats['win_rate']:5.1f}%")
    
    if outcome_data.get('avg_time_to_peak_minutes'):
        print(f"\n⏱️  Average Time to Peak: {outcome_data['avg_time_to_peak_minutes']:.0f} minutes")
    
    # Correlation analysis
    print("\n" + "=" * 80)
    print("CORRELATION ANALYSIS")
    print("=" * 80)
    
    correlation_data = analyze_criteria_correlation(db_path, days)
    
    if 'error' not in correlation_data:
        print(f"\n📊 Score Analysis:")
        sa = correlation_data['score_analysis']
        print(f"  Winners Avg Score: {sa['avg_score_winners']}/10")
        print(f"  Losers Avg Score: {sa['avg_score_losers']}/10")
        print(f"  Difference: {sa['score_difference']:+.1f} {'✅' if sa['score_difference'] > 1.0 else '⚠️'}")
        
        print(f"\n💎 Smart Money Analysis:")
        sm = correlation_data['smart_money_analysis']
        print(f"  Smart Money Win Rate: {sm['smart_money_win_rate']}%")
        print(f"  No Smart Money Win Rate: {sm['no_smart_money_win_rate']}%")
        print(f"  Smart Money Advantage: {sm['smart_money_advantage']:+.1f}% {'✅' if sm['smart_money_advantage'] > 10 else '⚠️'}")
        
        print(f"\n💰 Market Cap Performance:")
        for mcap_range, data in sorted(correlation_data['market_cap_analysis'].items(), 
                                       key=lambda x: -x[1]['win_rate']):
            if data['sample_size'] > 0:
                print(f"  {mcap_range:20} : Win Rate {data['win_rate']:5.1f}% (n={data['sample_size']})")
    
    # Recommendations
    print("\n" + "=" * 80)
    print("TUNING RECOMMENDATIONS")
    print("=" * 80)
    
    recommendations = generate_tuning_recommendations(outcome_data, correlation_data)
    
    if recommendations:
        print()
        for i, rec in enumerate(recommendations, 1):
            print(f"[{rec['priority']:6}] {rec['category']}")
            print(f"  Issue: {rec['issue']}")
            print(f"  Recommendation: {rec['recommendation']}")
            print(f"  Action: {rec['action']}")
            print()
    else:
        print("\n✅ System is performing well - no critical tuning needed at this time")
    
    # Top recent signals
    print("=" * 80)
    print("RECENT SIGNALS (Top 10)")
    print("=" * 80)
    print()
    
    for signal in outcome_data['signals'][:10]:
        outcome_emoji = {
            'big_win': '🚀',
            'win': '✅',
            'small_win': '📈',
            'flat': '➡️',
            'small_loss': '📉',
            'loss': '❌',
            'rug': '💀',
            'pumped_then_dumped': '⚠️',
            'pumped_then_faded': '⚠️',
            'unknown': '❓'
        }.get(signal['outcome'], '❓')
        
        print(f"{outcome_emoji} {signal['token'][:10]}... | Score: {signal['score']}/10 | " +
              f"{signal['conviction']:15} | Peak: {signal['peak_gain_pct']:+6.1f}% | " +
              f"Current: {signal['current_gain_pct']:+6.1f}% | Age: {signal['age_hours']:.1f}h")
    
    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


def main():
    """Main entry point"""
    
    # Parse arguments
    days = 7
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except:
            print(f"Usage: {sys.argv[0]} [days]")
            sys.exit(1)
    
    # Check for local database
    if not LOCAL_DB_PATH.exists():
        print(f"❌ Local database not found: {LOCAL_DB_PATH}")
        print("\n💡 This tool analyzes your local database.")
        print("   To analyze the server database, first copy it locally:")
        print(f"   scp root@64.227.157.221:/opt/callsbotonchain/var/alerted_tokens.db {LOCAL_DB_PATH}")
        sys.exit(1)
    
    try:
        print_signal_analysis(days, LOCAL_DB_PATH)
    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

