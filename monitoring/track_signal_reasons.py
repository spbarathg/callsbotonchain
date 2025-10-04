#!/usr/bin/env python3
"""
Signal Reason Tracker - Records WHY each signal was sent
Stores detailed criteria breakdown for correlation analysis
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Database path
LOCAL_ANALYTICS_DIR = Path(__file__).parent.parent / "analytics"
REASONS_DB_PATH = LOCAL_ANALYTICS_DIR / "signal_reasons.db"


def init_reasons_db():
    """Initialize signal reasons database"""
    LOCAL_ANALYTICS_DIR.mkdir(exist_ok=True)
    
    conn = sqlite3.connect(str(REASONS_DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_reasons (
            token_address TEXT PRIMARY KEY,
            alerted_at TIMESTAMP,
            final_score INTEGER,
            preliminary_score INTEGER,
            smart_money_detected BOOLEAN,
            conviction_type TEXT,
            
            -- Price/Market metrics at alert time
            price_usd REAL,
            market_cap_usd REAL,
            liquidity_usd REAL,
            volume_24h_usd REAL,
            
            -- Momentum metrics
            change_1h REAL,
            change_24h REAL,
            
            -- Community metrics
            unique_buyers_24h INTEGER,
            unique_sellers_24h INTEGER,
            
            -- Security/Risk metrics
            is_mint_revoked BOOLEAN,
            is_lp_locked BOOLEAN,
            lock_hours REAL,
            top10_concentration REAL,
            bundlers_percent REAL,
            insiders_percent REAL,
            
            -- Transaction context
            usd_value REAL,
            tx_type TEXT,
            dex TEXT,
            
            -- Gating results
            passed_senior_strict BOOLEAN,
            passed_senior_nuanced BOOLEAN,
            passed_junior_strict BOOLEAN,
            passed_junior_nuanced BOOLEAN,
            
            -- Scoring breakdown (JSON)
            scoring_details TEXT,
            
            -- Data source
            data_source TEXT,
            
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()


def record_signal_reason(
    token_address: str,
    alerted_at: str,
    final_score: int,
    preliminary_score: int,
    smart_money_detected: bool,
    conviction_type: str,
    stats: Dict[str, Any],
    tx_data: Dict[str, Any],
    scoring_details: list,
    gating_results: Dict[str, bool]
) -> None:
    """Record the detailed reason why a signal was sent"""
    
    init_reasons_db()
    
    conn = sqlite3.connect(str(REASONS_DB_PATH))
    cursor = conn.cursor()
    
    # Extract metrics from stats
    price_usd = stats.get('price_usd', 0)
    market_cap_usd = stats.get('market_cap_usd', 0)
    liquidity_usd = stats.get('liquidity_usd', 0)
    volume_24h_usd = (stats.get('volume', {}).get('24h', {}).get('volume_usd', 0) or 0)
    
    change_1h = stats.get('change', {}).get('1h', 0)
    change_24h = stats.get('change', {}).get('24h', 0)
    
    volume_data = stats.get('volume', {}).get('24h', {})
    unique_buyers = volume_data.get('unique_buyers', 0)
    unique_sellers = volume_data.get('unique_sellers', 0)
    
    security = stats.get('security', {})
    is_mint_revoked = security.get('is_mint_revoked')
    
    liquidity_obj = stats.get('liquidity', {})
    is_lp_locked = (
        liquidity_obj.get('is_lp_locked') or
        liquidity_obj.get('lock_status') in ('locked', 'burned') or
        liquidity_obj.get('is_lp_burned')
    )
    lock_hours = liquidity_obj.get('lock_hours') or liquidity_obj.get('lock_duration_hours')
    
    holders = stats.get('holders', {})
    top10_concentration = holders.get('top_10_concentration_percent') or holders.get('top10_percent')
    bundlers_percent = holders.get('bundlers_percent') or holders.get('bundlers')
    insiders_percent = holders.get('insiders_percent') or holders.get('insiders')
    
    # Transaction context
    usd_value = tx_data.get('usd_value', 0)
    tx_type = tx_data.get('tx_type', '')
    dex = tx_data.get('dex', '')
    
    # Data source
    data_source = stats.get('_source', 'unknown')
    
    # Store gating results
    passed_senior_strict = gating_results.get('senior_strict', False)
    passed_senior_nuanced = gating_results.get('senior_nuanced', False)
    passed_junior_strict = gating_results.get('junior_strict', False)
    passed_junior_nuanced = gating_results.get('junior_nuanced', False)
    
    # Serialize scoring details
    scoring_details_json = json.dumps(scoring_details)
    
    cursor.execute("""
        INSERT OR REPLACE INTO signal_reasons (
            token_address, alerted_at, final_score, preliminary_score,
            smart_money_detected, conviction_type,
            price_usd, market_cap_usd, liquidity_usd, volume_24h_usd,
            change_1h, change_24h,
            unique_buyers_24h, unique_sellers_24h,
            is_mint_revoked, is_lp_locked, lock_hours,
            top10_concentration, bundlers_percent, insiders_percent,
            usd_value, tx_type, dex,
            passed_senior_strict, passed_senior_nuanced,
            passed_junior_strict, passed_junior_nuanced,
            scoring_details, data_source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        token_address, alerted_at, final_score, preliminary_score,
        smart_money_detected, conviction_type,
        price_usd, market_cap_usd, liquidity_usd, volume_24h_usd,
        change_1h, change_24h,
        unique_buyers, unique_sellers,
        is_mint_revoked, is_lp_locked, lock_hours,
        top10_concentration, bundlers_percent, insiders_percent,
        usd_value, tx_type, dex,
        passed_senior_strict, passed_senior_nuanced,
        passed_junior_strict, passed_junior_nuanced,
        scoring_details_json, data_source
    ))
    
    conn.commit()
    conn.close()


def get_signal_reason(token_address: str) -> Optional[Dict[str, Any]]:
    """Retrieve the reason why a signal was sent"""
    
    if not REASONS_DB_PATH.exists():
        return None
    
    conn = sqlite3.connect(str(REASONS_DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM signal_reasons
        WHERE token_address = ?
    """, (token_address,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return dict(row)


def analyze_reason_patterns(db_path: Path = REASONS_DB_PATH, alerts_db: Path = None) -> Dict[str, Any]:
    """Analyze patterns in signal reasons vs outcomes"""
    
    if not db_path.exists():
        return {"error": "No signal reasons database found"}
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # If alerts database provided, join with outcomes
    if alerts_db and alerts_db.exists():
        # Attach alerts database
        cursor.execute(f"ATTACH DATABASE '{alerts_db}' AS alerts")
        
        query = """
        SELECT 
            r.*,
            s.peak_price_usd,
            s.first_price_usd,
            s.last_price_usd,
            s.outcome
        FROM signal_reasons r
        LEFT JOIN alerts.alerted_token_stats s ON r.token_address = s.token_address
        """
    else:
        query = "SELECT * FROM signal_reasons"
    
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return {"error": "No signal reasons found"}
    
    # Analyze patterns
    analysis = {
        'total_signals': len(rows),
        'by_conviction': {},
        'by_gating_path': {},
        'by_data_source': {},
        'mint_revoked_stats': {'yes': 0, 'no': 0, 'unknown': 0},
        'lp_locked_stats': {'yes': 0, 'no': 0, 'unknown': 0},
        'avg_metrics': {}
    }
    
    # Collect metrics
    market_caps = []
    volumes = []
    liquidities = []
    change_1h_vals = []
    top10_vals = []
    
    for row in rows:
        # Conviction
        conviction = row['conviction_type'] or 'unknown'
        analysis['by_conviction'][conviction] = analysis['by_conviction'].get(conviction, 0) + 1
        
        # Gating path
        if row['passed_senior_strict']:
            path = 'senior_strict'
        elif row['passed_senior_nuanced']:
            path = 'senior_nuanced'
        elif row['passed_junior_strict']:
            path = 'junior_strict'
        elif row['passed_junior_nuanced']:
            path = 'junior_nuanced'
        else:
            path = 'unknown'
        analysis['by_gating_path'][path] = analysis['by_gating_path'].get(path, 0) + 1
        
        # Data source
        source = row['data_source'] or 'unknown'
        analysis['by_data_source'][source] = analysis['by_data_source'].get(source, 0) + 1
        
        # Security metrics
        if row['is_mint_revoked'] is True:
            analysis['mint_revoked_stats']['yes'] += 1
        elif row['is_mint_revoked'] is False:
            analysis['mint_revoked_stats']['no'] += 1
        else:
            analysis['mint_revoked_stats']['unknown'] += 1
        
        if row['is_lp_locked'] is True:
            analysis['lp_locked_stats']['yes'] += 1
        elif row['is_lp_locked'] is False:
            analysis['lp_locked_stats']['no'] += 1
        else:
            analysis['lp_locked_stats']['unknown'] += 1
        
        # Collect numeric metrics
        if row['market_cap_usd']:
            market_caps.append(row['market_cap_usd'])
        if row['volume_24h_usd']:
            volumes.append(row['volume_24h_usd'])
        if row['liquidity_usd']:
            liquidities.append(row['liquidity_usd'])
        if row['change_1h']:
            change_1h_vals.append(row['change_1h'])
        if row['top10_concentration']:
            top10_vals.append(row['top10_concentration'])
    
    # Calculate averages
    import statistics
    if market_caps:
        analysis['avg_metrics']['market_cap_usd'] = round(statistics.mean(market_caps), 2)
        analysis['avg_metrics']['median_market_cap_usd'] = round(statistics.median(market_caps), 2)
    if volumes:
        analysis['avg_metrics']['volume_24h_usd'] = round(statistics.mean(volumes), 2)
    if liquidities:
        analysis['avg_metrics']['liquidity_usd'] = round(statistics.mean(liquidities), 2)
    if change_1h_vals:
        analysis['avg_metrics']['change_1h'] = round(statistics.mean(change_1h_vals), 2)
    if top10_vals:
        analysis['avg_metrics']['top10_concentration'] = round(statistics.mean(top10_vals), 2)
    
    return analysis


if __name__ == "__main__":
    # Test initialization
    init_reasons_db()
    print(f"✅ Signal reasons database initialized at: {REASONS_DB_PATH}")
    
    # Show analysis if data exists
    if REASONS_DB_PATH.exists():
        analysis = analyze_reason_patterns()
        if 'error' not in analysis:
            print(f"\n📊 Analysis of {analysis['total_signals']} signals:")
            print(f"\nBy Conviction: {analysis['by_conviction']}")
            print(f"\nBy Gating Path: {analysis['by_gating_path']}")
            print(f"\nBy Data Source: {analysis['by_data_source']}")
            print(f"\nAvg Metrics: {analysis['avg_metrics']}")

