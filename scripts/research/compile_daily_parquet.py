import os
import json
import logging
import argparse
from datetime import datetime
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("CompileParquet")

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
FEATURES_DIR = os.path.join(BASE_DIR, 'unbiased_logger', 'logs', 'features_T30')
DEPTH_DIR = os.path.join(BASE_DIR, 'unbiased_logger', 'logs', 'depth_series')
GAPS_DIR = os.path.join(BASE_DIR, 'unbiased_logger', 'logs', 'system_events')
OUTPUT_DIR = os.path.join(BASE_DIR, 'unbiased_logger', 'logs', 'compiled_parquet')

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Simulation Assumptions
TRADE_SIZE_SOL = 0.5
DEX_FEE_PCT = 0.01
JITO_TIP_SOL = 0.001
PRIORITY_FEE_SOL = 0.0005
DEAD_POOL_EPSILON_SOL = 0.05 # Must be < TRADE_SIZE_SOL to avoid misclassifying "nothing happened" as a rug

def simulate_buy(vsol, vtoken, sol_amount):
    """Simulates buying tokens on a constant-product bonding curve."""
    k = vsol * vtoken
    sol_in_after_fee = sol_amount * (1 - DEX_FEE_PCT)
    new_vsol = vsol + sol_in_after_fee
    new_vtoken = k / new_vsol
    tokens_received = vtoken - new_vtoken
    return tokens_received

def simulate_sell(vsol, vtoken, token_amount):
    """Simulates selling tokens on a constant-product bonding curve."""
    k = vsol * vtoken
    new_vtoken = vtoken + token_amount
    new_vsol = k / new_vtoken
    sol_received_raw = vsol - new_vsol
    sol_received_after_fee = sol_received_raw * (1 - DEX_FEE_PCT)
    return sol_received_after_fee

def overlaps_gap(start_ts, end_ts, gaps):
    """Checks if a given time window overlaps with any recorded gap."""
    for gap in gaps:
        if start_ts <= gap['end_ts'] and end_ts >= gap['start_ts']:
            return True
    return False

def get_depth_at_horizon(valid_bars, target_ts, max_lookforward=300):
    """Finds the closest depth bar to a specific target timestamp."""
    for bar in valid_bars:
        if target_ts <= bar["ts"] <= target_ts + max_lookforward:
            return bar
    return None

def calculate_nrr_metrics(features, depth_bars, gaps):
    """Calculates Max and Fixed-Horizon Net-Realizable Returns."""
    mint = features["mint"]
    launch_time = features["launch_timestamp"]
    entry_time = launch_time + 30.0
    
    # 1. Feature Window Gap Check (Drop entirely if gap overlaps T+0 to T+30s)
    if overlaps_gap(launch_time, entry_time, gaps):
        return None # Return None to signal row drop
        
    valid_bars = [b for b in depth_bars if b["ts"] >= entry_time]
    
    if not valid_bars or not depth_bars:
        # If no depth bars, we assume 100% loss
        return {
            "nrr_fixed_1h": -TRADE_SIZE_SOL,
            "nrr_fixed_4h": -TRADE_SIZE_SOL,
            "max_nrr_4h": -TRADE_SIZE_SOL
        }
        
    # Derive curve floor from the absolute first recorded bar (T+0ish)
    # Pump.fun initializes exactly at 30.0 SOL. If our first observed bar is heavily inflated 
    # (> 31.0), it means the depth_tracker missed the TokenCreated event and we caught it late.
    # We fallback to 30.0 to prevent flagging minor drawdowns as 100% loss rugged pools.
    first_bar = sorted(depth_bars, key=lambda x: x["ts"])[0]
    floor_vsol = first_bar["vsol"]
    if floor_vsol > 31.0:
        floor_vsol = 30.0
        
    # Get entry depth (closest bar to T+30s)
    entry_bar = valid_bars[0]
    tokens_bought = simulate_buy(entry_bar["vsol"], entry_bar["vtoken"], TRADE_SIZE_SOL)
    
    if tokens_bought <= 0:
        return {
            "nrr_fixed_1h": -TRADE_SIZE_SOL,
            "nrr_fixed_4h": -TRADE_SIZE_SOL,
            "max_nrr_4h": -TRADE_SIZE_SOL
        }

    # Initialize results
    results = {}
    
    def is_dead_pool(current_vsol):
        return current_vsol <= (floor_vsol + DEAD_POOL_EPSILON_SOL)
    
    # 2. nrr_fixed_1h
    if overlaps_gap(entry_time, launch_time + 3600, gaps):
        results["nrr_fixed_1h"] = None
    else:
        bar_1h = get_depth_at_horizon(valid_bars, launch_time + 3600)
        if bar_1h and not is_dead_pool(bar_1h["vsol"]):
            sol_received = simulate_sell(bar_1h["vsol"], bar_1h["vtoken"], tokens_bought)
            results["nrr_fixed_1h"] = sol_received - TRADE_SIZE_SOL - JITO_TIP_SOL - PRIORITY_FEE_SOL
        else:
            results["nrr_fixed_1h"] = -TRADE_SIZE_SOL # Dead pool or no data -> total loss clamp

    # 3. nrr_fixed_4h
    if overlaps_gap(entry_time, launch_time + 14400, gaps):
        results["nrr_fixed_4h"] = None
        results["max_nrr_4h"] = None
    else:
        bar_4h = get_depth_at_horizon(valid_bars, launch_time + 14400)
        if bar_4h and not is_dead_pool(bar_4h["vsol"]):
            sol_received = simulate_sell(bar_4h["vsol"], bar_4h["vtoken"], tokens_bought)
            results["nrr_fixed_4h"] = sol_received - TRADE_SIZE_SOL - JITO_TIP_SOL - PRIORITY_FEE_SOL
        else:
            results["nrr_fixed_4h"] = -TRADE_SIZE_SOL

        # 4. max_nrr_4h (Volatility ceiling)
        max_nrr = -TRADE_SIZE_SOL
        for bar in valid_bars:
            if bar["ts"] > launch_time + 14400:
                break
            if is_dead_pool(bar["vsol"]):
                continue
            sol_rec = simulate_sell(bar["vsol"], bar["vtoken"], tokens_bought)
            nrr = sol_rec - TRADE_SIZE_SOL - JITO_TIP_SOL - PRIORITY_FEE_SOL
            if nrr > max_nrr:
                max_nrr = nrr
        results["max_nrr_4h"] = max_nrr

    return results

def compile_daily(date_str):
    features_file = os.path.join(FEATURES_DIR, f"{date_str}.jsonl")
    depth_file = os.path.join(DEPTH_DIR, f"{date_str}.jsonl")
    gaps_file = os.path.join(GAPS_DIR, f"{date_str}_gaps.jsonl")
    
    if not os.path.exists(features_file):
        logger.warning(f"No features file found for {date_str}")
        return

    # Load gaps
    gaps = []
    if os.path.exists(gaps_file):
        with open(gaps_file, 'r') as f:
            for line in f:
                try:
                    gaps.append(json.loads(line.strip()))
                except:
                    pass
        
    # Load features
    features_data = []
    with open(features_file, 'r') as f:
        for line in f:
            try:
                features_data.append(json.loads(line.strip()))
            except:
                pass
                
    # Load and group depth bars
    depth_data = {}
    if os.path.exists(depth_file):
        with open(depth_file, 'r') as f:
            for line in f:
                try:
                    bar = json.loads(line.strip())
                    mint = bar["mint"]
                    if mint not in depth_data:
                        depth_data[mint] = []
                    depth_data[mint].append(bar)
                except:
                    pass
                    
    # Calculate NRR metrics
    final_dataset = []
    for feat in features_data:
        mint = feat["mint"]
        bars = depth_data.get(mint, [])
        nrr_metrics = calculate_nrr_metrics(feat, bars, gaps)
        
        if nrr_metrics is None:
            # Row dropped due to T+30s gap overlap
            continue
            
        feat.update(nrr_metrics)
        
        # Binary target for XGBoost (e.g. > 10% ROI) based on 1h fixed horizon
        if feat.get("nrr_fixed_1h") is not None:
            roi = feat["nrr_fixed_1h"] / TRADE_SIZE_SOL
            feat["target_hit_10pct_1h"] = 1 if roi >= 0.10 else 0
        else:
            feat["target_hit_10pct_1h"] = None
            
        final_dataset.append(feat)
        
    # Convert to Parquet
    if final_dataset:
        df = pd.DataFrame(final_dataset)
        out_file = os.path.join(OUTPUT_DIR, f"features_{date_str}.parquet")
        df.to_parquet(out_file, engine='pyarrow')
        logger.info(f"Compiled {len(df)} valid records to {out_file}")
    else:
        logger.info(f"No valid records found for {date_str} after filtering.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Date format YYYY-MM-DD", required=True)
    args = parser.parse_args()
    compile_daily(args.date)
