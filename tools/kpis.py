import argparse
import os
import pandas as pd


def compute_kpis(csv_path: str, group_by_gate_mode: bool = False):
    df = pd.read_csv(csv_path)
    # Guard against degenerate zero/negative baselines
    for base_col in ['first_price_usd', 'first_market_cap_usd']:
        if base_col in df.columns:
            df.loc[df[base_col] <= 0, base_col] = pd.NA
    # Normalize booleans/ints
    for col in [
        'label_ge_2x_price', 'final_score', 'smart_money_detected'
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    def summarize(frame: pd.DataFrame) -> dict:
        total = len(frame)
        if total == 0:
            return {
                'rows': 0,
                'two_x_rate': 0.0,
                'rug_rate': float('nan'),
                'median_time_to_peak_price_s': float('nan'),
            }
        # Prefer recomputation if label column missing
        if 'label_ge_2x_price' in frame.columns:
            two_x_rate = frame['label_ge_2x_price'].mean()
        elif {'peak_price_usd','first_price_usd'}.issubset(frame.columns):
            valid = frame['first_price_usd'].gt(0)
            two_x_rate = ((frame['peak_price_usd'] / frame['first_price_usd'])
                          .where(valid)
                          .ge(2.0)
                          .mean())
        else:
            two_x_rate = float('nan')
        rug_rate = (frame['outcome'].eq('rug').mean() if 'outcome' in frame.columns else float('nan'))
        med_ttp = frame['time_to_peak_price_s'].where(frame['time_to_peak_price_s'].ge(0) if 'time_to_peak_price_s' in frame.columns else False).median() \
                  if 'time_to_peak_price_s' in frame.columns else float('nan')
        return {
            'rows': int(total),
            'two_x_rate': float(two_x_rate) if pd.notna(two_x_rate) else float('nan'),
            'rug_rate': float(rug_rate) if pd.notna(rug_rate) else float('nan'),
            'median_time_to_peak_price_s': float(med_ttp) if pd.notna(med_ttp) else float('nan'),
        }

    results = []

    if group_by_gate_mode and 'gates' in df.columns:
        # If a JSON structure exists, attempt to extract gate mode
        # Otherwise, look for a sibling meta file
        try:
            # Some exports may include a separate meta file produced by export_stats
            meta_path = os.path.splitext(csv_path)[0] + '_meta.json'
            if os.path.exists(meta_path):
                import json
                with open(meta_path, 'r', encoding='utf-8') as mf:
                    meta = json.load(mf)
                gate_mode = (meta.get('current_gates') or {}).get('GATE_MODE')
                if gate_mode:
                    s = summarize(df)
                    s['gate_mode'] = gate_mode
                    results.append(s)
                    return pd.DataFrame(results)
        except Exception:
            pass

    # Overall summary
    results.append(summarize(df))
    return pd.DataFrame(results)


def main():
    ap = argparse.ArgumentParser(description='Compute daily KPIs from alerts CSV')
    ap.add_argument('--csv', required=True, help='Path to alerts_training_*.csv')
    ap.add_argument('--group', choices=['overall', 'gatemode'], default='overall')
    args = ap.parse_args()

    df = compute_kpis(args.csv, group_by_gate_mode=(args.group == 'gatemode'))
    pd.set_option('display.max_columns', None)
    print(df)


if __name__ == '__main__':
    main()


