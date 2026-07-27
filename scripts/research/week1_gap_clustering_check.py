"""week1_gap_clustering_check.py — does gap frequency correlate with launch volume?"""
import json
import glob
import os
import pandas as pd
import numpy as np
from scipy import stats

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
GAPS_GLOB = os.path.join(BASE_DIR, "unbiased_logger", "logs", "system_events", "*_gaps.jsonl")
PARQUET_GLOB = os.path.join(BASE_DIR, "unbiased_logger", "logs", "compiled_parquet", "*.parquet")
FEATURES_GLOB = os.path.join(BASE_DIR, "unbiased_logger", "logs", "features_T30", "*.jsonl")

def load_gaps() -> pd.DataFrame:
    rows = []
    for p in glob.glob(GAPS_GLOB):
        with open(p, 'r') as f:
            for l in f:
                if l.strip():
                    rows.append(json.loads(l.strip()))
    return pd.DataFrame(rows)

def load_volume_proxy() -> pd.DataFrame:
    # Since tokens that overlap a gap in T+0..T+30s are dropped from the Parquet file,
    # we should load the raw features_T30 JSONL to see the dropped tokens, OR
    # measure market-wide volume (e.g. trades per 5 minute window).
    #
    # However, to use the user's exact proxy logic (volume of the token vs gap overlap):
    rows = []
    for p in glob.glob(FEATURES_GLOB):
        with open(p, 'r') as f:
            for l in f:
                if l.strip():
                    rows.append(json.loads(l.strip()))
                    
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    
    return df[["mint", "launch_timestamp", "t30_trade_count"]].drop_duplicates("mint")

def main():
    gaps = load_gaps()
    volume = load_volume_proxy()
    
    if gaps.empty or volume.empty:
        print("Not enough data to run clustering check.")
        return

    # Define the 3 gap types based on time horizons
    def get_gap_types(row):
        ts = row["launch_timestamp"]
        t30_gap = 1 if overlaps_gap(ts, ts + 30.0, gaps) else 0
        h1_gap = 1 if overlaps_gap(ts + 30.0, ts + 3600.0, gaps) else 0
        h4_gap = 1 if overlaps_gap(ts + 30.0, ts + 14400.0, gaps) else 0
        return pd.Series([t30_gap, h1_gap, h4_gap])
        
    def overlaps_gap(start_ts, end_ts, gaps_df):
        for _, gap in gaps_df.iterrows():
            if gap['start_ts'] <= end_ts and gap['end_ts'] >= start_ts:
                return True
        return False
        
    volume[["gap_t30", "gap_1h", "gap_4h"]] = volume.apply(get_gap_types, axis=1)
    volume["log_volume"] = np.log1p(volume["t30_trade_count"])
    
    # Bin into quartiles once
    volume["volume_quartile"] = pd.qcut(volume["log_volume"], 4, labels=["Q1_low", "Q2", "Q3", "Q4_high"], duplicates='drop')
    
    for gap_col, desc in [("gap_t30", "T+30s Row Drop"), ("gap_1h", "1h Label Nulled"), ("gap_4h", "4h Label Nulled")]:
        print(f"\n{'='*40}")
        print(f"ANALYSIS FOR: {desc}")
        print(f"{'='*40}")
        
        corr, p = stats.pointbiserialr(volume[gap_col], volume["log_volume"])
        print(f"Point-biserial r={corr:.4f}, p={p:.4g}")

        table = pd.crosstab(volume["volume_quartile"], volume[gap_col])
        if table.shape[1] > 1:
            chi2, chi_p, dof, _ = stats.chi2_contingency(table)
            print("\nGap rate by volume quartile:")
            print((table[1] / table.sum(axis=1)).round(4))
            print(f"\nChi2={chi2:.4f}, p={chi_p:.4g}, dof={dof}")

            if p < 0.05 or chi_p < 0.05:
                print(f"\n⚠ {desc} correlates with launch volume — MNAR bias likely.")
        else:
            print("\nNo gaps found of this type to perform Chi2 test.")

if __name__ == "__main__":
    main()
