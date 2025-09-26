import argparse
import math
import pandas as pd
from dataclasses import dataclass


@dataclass
class Config:
    initial_equity: float = 1000.0
    per_trade_usd: float = 120.0
    max_concurrent: int = 4
    max_trades_per_day: int = 5
    stop_loss_pct: float = 0.20
    tp1_mult: float = 1.5
    tp1_pct: float = 0.50
    tp2_mult: float = 2.5
    tp2_pct: float = 0.25
    trail_from_peak_pct: float = 0.30
    time_stop_min: int = 90
    entry_slippage_pct: float = 0.01
    exit_slippage_pct: float = 0.01


def simulate(csv_path: str, cfg: Config) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # Require first_price_usd and peak_price_usd to approximate path
    if 'first_price_usd' not in df.columns or 'peak_price_usd' not in df.columns:
        raise SystemExit("CSV must include first_price_usd and peak_price_usd columns.")

    # Basic heuristic: assume linear path to peak within time_to_peak_price_s, then drift
    # For paper mode, we only need to check if TP levels hit before SL/time stop using peak.
    trades = []
    equity = cfg.initial_equity
    open_slots = cfg.max_concurrent
    daily_trades = 0

    for _, r in df.iterrows():
        if daily_trades >= cfg.max_trades_per_day:
            break
        if open_slots <= 0:
            break

        entry = float(r.get('first_price_usd') or 0)
        peak = float(r.get('peak_price_usd') or 0)
        if entry <= 0:
            continue
        # Apply entry slippage
        entry_eff = entry * (1 + cfg.entry_slippage_pct)
        tp1 = entry_eff * cfg.tp1_mult
        tp2 = entry_eff * cfg.tp2_mult
        sl = entry_eff * (1 - cfg.stop_loss_pct)

        size = min(cfg.per_trade_usd, max(0.0, equity * 0.15))
        if size <= 0:
            continue

        qty = size / entry_eff
        pnl = 0.0
        filled_tp1 = False
        filled_tp2 = False
        # If peak never reached entry_eff, assume stop hit
        if peak <= sl:
            exit_price = sl * (1 - cfg.exit_slippage_pct)
            pnl = (exit_price - entry_eff) * qty
            stop_reason = 'SL'
        else:
            # Peak above entry; check ladder
            if peak >= tp1:
                # TP1: sell tp1_pct
                sell_qty = qty * cfg.tp1_pct
                exit_price = tp1 * (1 - cfg.exit_slippage_pct)
                pnl += (exit_price - entry_eff) * sell_qty
                qty -= sell_qty
                filled_tp1 = True
            if peak >= tp2 and qty > 0:
                sell_qty = qty * cfg.tp2_pct
                exit_price = tp2 * (1 - cfg.exit_slippage_pct)
                pnl += (exit_price - entry_eff) * sell_qty
                qty -= sell_qty
                filled_tp2 = True
            # Remainder: trail from peak by trail_from_peak_pct
            if qty > 0:
                trail_exit = peak * (1 - cfg.trail_from_peak_pct)
                exit_price = trail_exit * (1 - cfg.exit_slippage_pct)
                # If trail exit is below entry after TP1/TP2, worst-case breakeven logic not modeled; keep simple
                pnl += (exit_price - entry_eff) * qty
                qty = 0
                stop_reason = 'TRAIL'
            else:
                stop_reason = 'TPs'

        equity += pnl
        daily_trades += 1
        open_slots -= 1
        trades.append({
            'token_address': r.get('token_address'),
            'entry_price': entry_eff,
            'peak_price': peak,
            'size_usd': size,
            'pnl_usd': pnl,
            'equity_after': equity,
            'filled_tp1': filled_tp1,
            'filled_tp2': filled_tp2,
            'stop_reason': stop_reason,
        })

    return pd.DataFrame(trades)


def main():
    ap = argparse.ArgumentParser(description='Paper trade simulator for alerts CSV')
    ap.add_argument('--csv', required=True)
    ap.add_argument('--initial', type=float, default=1000)
    ap.add_argument('--per_trade', type=float, default=120)
    ap.add_argument('--max_concurrent', type=int, default=4)
    ap.add_argument('--max_trades', type=int, default=5)
    args = ap.parse_args()

    cfg = Config(
        initial_equity=args.initial,
        per_trade_usd=args.per_trade,
        max_concurrent=args.max_concurrent,
        max_trades_per_day=args.max_trades,
    )

    trades = simulate(args.csv, cfg)
    if trades.empty:
        print('No trades simulated.')
        return
    print(trades)
    print('\nSummary:')
    print('Trades:', len(trades))
    print('Final equity: $%.2f' % trades.iloc[-1]['equity_after'])
    winners = (trades['pnl_usd'] > 0).sum()
    print('Win rate: %.2f%%' % (100 * winners / len(trades)))
    print('Avg PnL: $%.2f' % trades['pnl_usd'].mean())


if __name__ == '__main__':
    main()


