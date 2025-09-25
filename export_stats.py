import argparse
import csv
import os
from datetime import datetime
from typing import Optional
import sqlite3
import json


def export_db_summary(db_path: str, out_csv: str) -> None:
    con = sqlite3.connect(db_path)
    c = con.cursor()
    q = """
    SELECT 
      t.token_address,
      t.alerted_at,
      t.final_score,
      t.smart_money_detected,
      s.first_alert_at,
      s.last_checked_at,
      s.first_price_usd,
      s.first_market_cap_usd,
      s.first_liquidity_usd,
      s.last_price_usd,
      s.last_market_cap_usd,
      s.last_liquidity_usd,
      s.last_volume_24h_usd,
      s.peak_price_usd,
      s.peak_market_cap_usd,
      s.peak_volume_24h_usd,
      s.peak_price_at,
      s.peak_market_cap_at
    FROM alerted_token_stats s
    JOIN alerted_tokens t ON t.token_address = s.token_address
    ORDER BY s.first_alert_at ASC
    """
    rows = c.execute(q).fetchall()
    con.close()

    headers = [
        "token_address",
        "alerted_at",
        "final_score",
        "smart_money_detected",
        "first_alert_at",
        "last_checked_at",
        "first_price_usd",
        "first_market_cap_usd",
        "first_liquidity_usd",
        "last_price_usd",
        "last_market_cap_usd",
        "last_liquidity_usd",
        "last_volume_24h_usd",
        "peak_price_usd",
        "peak_market_cap_usd",
        "peak_volume_24h_usd",
        "peak_price_at",
        "peak_market_cap_at",
        "peak_x_price",
        "peak_x_mcap",
        "time_to_peak_price_s",
        "time_to_peak_mcap_s",
    ]

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            (
                token,
                alerted_at,
                final_score,
                smart_money,
                first_alert_at,
                last_checked_at,
                first_price,
                first_mcap,
                first_liq,
                last_price,
                last_mcap,
                last_liq,
                last_vol24,
                peak_price,
                peak_mcap,
                peak_vol24,
                peak_price_at,
                peak_mcap_at,
            ) = r
            peak_x_price = (peak_price / first_price) if (first_price or 0) else None
            peak_x_mcap = (peak_mcap / first_mcap) if (first_mcap or 0) else None

            # time deltas in seconds (strings -> naive parse)
            def _parse(ts: Optional[str]) -> Optional[datetime]:
                if not ts:
                    return None
                try:
                    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    try:
                        return datetime.fromisoformat(ts)
                    except Exception:
                        return None

            t0 = _parse(first_alert_at)
            tpp = _parse(peak_price_at)
            tpm = _parse(peak_mcap_at)
            ttp_s = int((tpp - t0).total_seconds()) if (t0 and tpp) else None
            ttm_s = int((tpm - t0).total_seconds()) if (t0 and tpm) else None

            w.writerow([
                token,
                alerted_at,
                final_score,
                smart_money,
                first_alert_at,
                last_checked_at,
                first_price,
                first_mcap,
                first_liq,
                last_price,
                last_mcap,
                last_liq,
                last_vol24,
                peak_price,
                peak_mcap,
                peak_vol24,
                peak_price_at,
                peak_mcap_at,
                peak_x_price,
                peak_x_mcap,
                ttp_s,
                ttm_s,
            ])


def export_jsonl(jsonl_path: str, out_csv: str) -> None:
    headers = set()
    records = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            records.append(obj)
            headers.update(obj.keys())

    headers = list(headers)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for obj in records:
            w.writerow([obj.get(h) for h in headers])


def main():
    ap = argparse.ArgumentParser(description="Export CALLSBOTONCHAIN stats to CSV")
    ap.add_argument("--mode", choices=["db", "alerts", "tracking"], default="db")
    ap.add_argument("--db", default="alerted_tokens.db")
    ap.add_argument("--logdir", default=os.getenv("CALLSBOT_LOG_DIR", "logs"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    if args.mode == "db":
        out = args.out or f"export_db_{ts}.csv"
        export_db_summary(args.db, out)
        print("Wrote:", out)
    elif args.mode == "alerts":
        out = args.out or f"export_alerts_{ts}.csv"
        export_jsonl(os.path.join(args.logdir, "alerts.jsonl"), out)
        print("Wrote:", out)
    else:
        out = args.out or f"export_tracking_{ts}.csv"
        export_jsonl(os.path.join(args.logdir, "tracking.jsonl"), out)
        print("Wrote:", out)


if __name__ == "__main__":
    main()


