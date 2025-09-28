import argparse
import glob
import os
from typing import List, Tuple

import numpy as np
import pandas as pd


REQUIRED_COLUMNS: List[str] = [
    "token_address",
    "alerted_at",
    "final_score",
    "smart_money_detected",
    "conviction_type",
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
    "outcome",
    "outcome_at",
    "peak_drawdown_pct",
    "peak_x_price",
    "peak_x_mcap",
    "time_to_peak_price_s",
    "time_to_peak_mcap_s",
]


def validate_file(path: str) -> Tuple[bool, List[Tuple[str, object]]]:
    issues: List[Tuple[str, object]] = []
    df = pd.read_csv(
        path,
        parse_dates=[
            c
            for c in [
                "alerted_at",
                "first_alert_at",
                "last_checked_at",
                "peak_price_at",
                "peak_market_cap_at",
                "outcome_at",
            ]
            if c in pd.read_csv(path, nrows=0).columns
        ],
    )

    # Columns
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        issues.append(("missing_columns", missing))

    # Duplicates by token_address
    dups = int(df.duplicated(subset=["token_address"]).sum()) if "token_address" in df.columns else 0
    if dups:
        issues.append(("duplicate_token_address_rows", dups))

    # NA rates on criticals
    crit = [
        "token_address",
        "alerted_at",
        "final_score",
        "first_price_usd",
        "first_market_cap_usd",
        "peak_price_usd",
        "peak_market_cap_usd",
        "peak_x_price",
        "peak_x_mcap",
    ]
    na = {c: int(df[c].isna().sum()) for c in crit if c in df.columns}
    if any(na.values()):
        issues.append(("na_counts", na))

    # Non-negative checks
    nn_cols = [
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
        "peak_x_price",
        "peak_x_mcap",
    ]
    negative_in = [c for c in nn_cols if c in df.columns and (df[c].dropna() < 0).any()]
    if negative_in:
        issues.append(("negative_values_in", negative_in))

    # Ratio integrity: peak_x ~= peak/first
    def ratio_mismatch(a: pd.Series, b: pd.Series, x: pd.Series, eps: float = 1e-6) -> int:
        ok = (a.fillna(0) == 0) | (np.isclose(x, a / b, atol=eps, rtol=1e-6))
        return int((~ok).sum())

    if set(["peak_price_usd", "first_price_usd", "peak_x_price"]) <= set(df.columns):
        px_mis = ratio_mismatch(
            df["peak_price_usd"], df["first_price_usd"].replace(0, np.nan), df["peak_x_price"]
        )
        if px_mis:
            issues.append(("peak_x_price_mismatch_rows", px_mis))
    if set(["peak_market_cap_usd", "first_market_cap_usd", "peak_x_mcap"]) <= set(df.columns):
        mx_mis = ratio_mismatch(
            df["peak_market_cap_usd"], df["first_market_cap_usd"].replace(0, np.nan), df["peak_x_mcap"]
        )
        if mx_mis:
            issues.append(("peak_x_mcap_mismatch_rows", mx_mis))

    # Time deltas integrity
    def delta_mismatch(t0: pd.Series, tp: pd.Series, secs_col: str) -> int:
        if secs_col not in df.columns:
            return 0
        m = (t0.notna() & tp.notna() & df[secs_col].notna())
        if not m.any():
            return 0
        calc = (tp[m] - t0[m]).dt.total_seconds().astype("int64", errors="ignore")
        mis = int((np.abs(calc - df.loc[m, secs_col].astype("int64", errors="ignore")) > 5).sum())
        return mis

    if set(["first_alert_at", "peak_price_at"]) <= set(df.columns):
        tdp = delta_mismatch(df["first_alert_at"], df["peak_price_at"], "time_to_peak_price_s")
        if tdp:
            issues.append(("time_to_peak_price_mismatch_rows", tdp))
    if set(["first_alert_at", "peak_market_cap_at"]) <= set(df.columns):
        tdm = delta_mismatch(df["first_alert_at"], df["peak_market_cap_at"], "time_to_peak_mcap_s")
        if tdm:
            issues.append(("time_to_peak_mcap_mismatch_rows", tdm))

    # Rug consistency (soft)
    if "outcome" in df.columns and "peak_drawdown_pct" in df.columns:
        rugs = df["outcome"].fillna("").str.lower().eq("rug")
        rug_missing = int((rugs & df["peak_drawdown_pct"].isna()).sum())
        if rug_missing:
            issues.append(("rugs_missing_drawdown_pct", rug_missing))

    return (len(issues) == 0), issues


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate alerts training CSVs for completeness and consistency")
    ap.add_argument("--csv", nargs="+", required=True, help="One or more CSV paths or globs")
    ap.add_argument("--strict", action="store_true", help="Exit non-zero if any file has issues")
    args = ap.parse_args()

    paths: List[str] = []
    for p in args.csv:
        expanded = glob.glob(p)
        if expanded:
            paths.extend(expanded)
        else:
            paths.append(p)

    if not paths:
        print("No CSV files matched")
        raise SystemExit(2)

    any_issues = False
    for p in sorted(set(paths)):
        ok, issues = validate_file(p)
        print(f"file: {p}")
        print(f"ok: {ok}")
        print(f"issues: {issues if issues else 'none'}")
        print("")
        if not ok or issues:
            any_issues = True

    if args.strict and any_issues:
        raise SystemExit(1)


if __name__ == "__main__":
    print("Not a standalone entrypoint. Use: python scripts/bot.py run|web|trade")


