"""
Feature Engineering for Adaptive Signal Detection
Extracts training data from historical signal performance
"""
import sqlite3
import pandas as pd
import numpy as np
import os
from typing import Dict, List, Tuple


def extract_features(db_path='var/alerted_tokens.db') -> pd.DataFrame:
    """Extract training data from database with engineered features"""
    
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")
    
    con = sqlite3.connect(db_path)
    
    # Main query to get all signal data with outcomes
    # FIXED: Use actual column names from alerted_token_stats schema
    query = """
    SELECT 
        -- Token identifier
        s.token_address,
        s.first_alert_at as alerted_at,
        
        -- Signal quality features
        a.final_score,
        s.preliminary_score as prelim_score,
        s.conviction_type,
        COALESCE(s.smart_money_involved, a.smart_money_detected) as smart_money_detected,
        
        -- Market metrics at entry (FIXED: use first_* columns)
        s.first_price_usd as entry_price,
        s.first_market_cap_usd as entry_market_cap,
        s.first_liquidity_usd as entry_liquidity,
        s.last_volume_24h_usd as entry_volume_24h,  -- Approximate (DB doesn't track entry volume)
        
        -- Outcome metrics (targets)
        COALESCE(s.max_gain_percent, 0) as max_gain_percent,
        COALESCE((s.peak_price_at - s.first_alert_at) / 60.0, 0) as time_to_peak_minutes,
        COALESCE(s.is_rug, 0) as is_rug,
        s.peak_price_usd,
        s.last_price_usd
        
    FROM alerted_token_stats s
    LEFT JOIN alerted_tokens a ON s.token_address = a.token_address
    WHERE s.max_gain_percent IS NOT NULL  -- Only tokens with outcome data
    """
    
    df = pd.read_sql_query(query, con)
    con.close()
    
    print(f"📊 Loaded {len(df)} historical signals with outcomes")
    
    if len(df) == 0:
        print("⚠️  No training data available yet. Wait for more signals to accumulate.")
        print("   The tracking system needs to update max_gain_percent for signals.")
        print("   This happens when the tracking script runs (every 30 seconds).")
        return df
    
    # Engineer derived features
    df = engineer_derived_features(df)
    df = engineer_categorical_features(df)
    df = engineer_target_variables(df)
    
    return df


def engineer_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create derived numerical features"""
    
    # Ratio features (key predictors based on analysis)
    df['vol_to_mcap_ratio'] = df['entry_volume_24h'] / df['entry_market_cap'].replace(0, np.nan)
    df['vol_to_liq_ratio'] = df['entry_volume_24h'] / df['entry_liquidity'].replace(0, np.nan)
    df['liq_to_mcap_ratio'] = df['entry_liquidity'] / df['entry_market_cap'].replace(0, np.nan)
    
    # Log-transform skewed features (reduces impact of outliers)
    df['log_liquidity'] = np.log1p(df['entry_liquidity'].fillna(0))
    df['log_volume'] = np.log1p(df['entry_volume_24h'].fillna(0))
    df['log_mcap'] = np.log1p(df['entry_market_cap'].fillna(0))
    
    # Score gap (indicates overscoring or underscoring)
    df['score_gap'] = df['final_score'] - df['prelim_score']
    
    # Market cap category (micro/small/mid)
    df['is_microcap'] = (df['entry_market_cap'] < 100_000).astype(int)
    df['is_smallcap'] = ((df['entry_market_cap'] >= 100_000) & 
                         (df['entry_market_cap'] < 1_000_000)).astype(int)
    
    # Liquidity quality tiers (based on analysis)
    df['is_excellent_liq'] = (df['entry_liquidity'] >= 50_000).astype(int)
    df['is_good_liq'] = ((df['entry_liquidity'] >= 15_000) & 
                         (df['entry_liquidity'] < 50_000)).astype(int)
    df['is_poor_liq'] = (df['entry_liquidity'] < 15_000).astype(int)
    
    return df


def engineer_categorical_features(df: pd.DataFrame) -> pd.DataFrame:
    """One-hot encode categorical features"""
    
    # Conviction type encoding
    df['conviction_Smart_Money'] = df['conviction_type'].str.contains(
        'Smart Money', case=False, na=False).astype(int)
    df['conviction_Strict'] = df['conviction_type'].str.contains(
        'Strict', case=False, na=False).astype(int)
    df['conviction_Nuanced'] = df['conviction_type'].str.contains(
        'Nuanced', case=False, na=False).astype(int)
    df['conviction_High_Confidence'] = df['conviction_type'].str.contains(
        'High Confidence', case=False, na=False).astype(int)
    
    return df


def engineer_target_variables(df: pd.DataFrame) -> pd.DataFrame:
    """Create target variables for different prediction tasks"""
    
    # Primary regression target: max_gain_percent (continuous)
    df['target_gain'] = df['max_gain_percent']
    
    # Classification targets (binary)
    df['is_winner_1.5x'] = (df['max_gain_percent'] >= 50).astype(int)  # 1.5x
    df['is_winner_2x'] = (df['max_gain_percent'] >= 100).astype(int)    # 2x
    df['is_winner_5x'] = (df['max_gain_percent'] >= 400).astype(int)    # 5x
    df['is_winner_10x'] = (df['max_gain_percent'] >= 900).astype(int)   # 10x
    
    # Multi-class target (quality tiers)
    df['performance_tier'] = pd.cut(
        df['max_gain_percent'],
        bins=[-np.inf, 0, 50, 100, 400, np.inf],
        labels=['Loser', 'Small', 'Good', 'Great', 'Moon']
    )
    
    return df


def get_feature_list() -> List[str]:
    """Return list of feature columns for model training"""
    return [
        # Core score features
        'final_score',
        'prelim_score',
        'score_gap',
        'smart_money_detected',
        
        # Market metrics (log-transformed)
        'log_liquidity',
        'log_volume',
        'log_mcap',
        
        # Ratio features (key predictors)
        'vol_to_mcap_ratio',
        'vol_to_liq_ratio',
        'liq_to_mcap_ratio',
        
        # Categorical flags
        'conviction_Smart_Money',
        'conviction_Strict',
        'conviction_Nuanced',
        'conviction_High_Confidence',
        
        # Market cap tiers
        'is_microcap',
        'is_smallcap',
        
        # Liquidity quality
        'is_excellent_liq',
        'is_good_liq',
        'is_poor_liq',
    ]


def summarize_dataset(df: pd.DataFrame) -> Dict:
    """Print dataset summary statistics"""
    summary = {
        'total_signals': len(df),
        'avg_gain': df['max_gain_percent'].mean(),
        'median_gain': df['max_gain_percent'].median(),
        'win_rate_1.5x': df['is_winner_1.5x'].mean() * 100,
        'win_rate_2x': df['is_winner_2x'].mean() * 100,
        'win_rate_5x': df['is_winner_5x'].mean() * 100,
        'win_rate_10x': df['is_winner_10x'].mean() * 100,
        'rug_rate': df['is_rug'].mean() * 100,
    }
    
    print("\n" + "="*60)
    print("📈 DATASET SUMMARY")
    print("="*60)
    print(f"Total Signals: {summary['total_signals']}")
    print(f"Avg Gain: {summary['avg_gain']:.1f}%")
    print(f"Median Gain: {summary['median_gain']:.1f}%")
    print(f"\nWin Rates:")
    print(f"  1.5x+: {summary['win_rate_1.5x']:.1f}%")
    print(f"  2x+:   {summary['win_rate_2x']:.1f}%")
    print(f"  5x+:   {summary['win_rate_5x']:.1f}%")
    print(f"  10x+:  {summary['win_rate_10x']:.1f}%")
    print(f"\nRug Rate: {summary['rug_rate']:.1f}%")
    print("="*60 + "\n")
    
    return summary


if __name__ == '__main__':
    # Test feature engineering
    df = extract_features()
    
    if len(df) > 0:
        summary = summarize_dataset(df)
        
        print("✅ Feature engineering complete!")
        print(f"📊 Generated {len(get_feature_list())} features")
        print(f"🎯 Ready for model training")
        
        # Show sample
        print("\nSample Features (first 3 rows):")
        print(df[get_feature_list()].head(3))
    else:
        print("⚠️  Not enough data yet. Need at least 50 signals with outcomes.")

