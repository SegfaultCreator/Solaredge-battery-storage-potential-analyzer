"""Fetch SolarEdge data per month, cache a monthly time-series CSV, and merge into CSV.

Usage:
  Set environment variables `SOLAREDGE_API_KEY` and `SOLAREDGE_SITE_ID`.
  Then run: `python fetch_and_merge.py --start 2026-01-01 --end 2026-01-30`

This will cache monthly CSV files under `Raw/monthly/` and write `Merged/merged.csv`.
"""

from __future__ import annotations

import argparse
import os

try:
    from .data_cache import ensure_dirs, monthly_cache_path, save_monthly_series, write_merged_csv
    from .data_transform import merge_monthly_cache_files, synthesize_target_dataframe
    from .solaredge_client import (
        coerce_end_datetime,
        fetch_monthly_time_series,
        month_range,
        month_start_end,
        parse_datetime,
    )
except ImportError:  # pragma: no cover
    from data_cache import ensure_dirs, monthly_cache_path, save_monthly_series, write_merged_csv
    from data_transform import merge_monthly_cache_files, synthesize_target_dataframe
    from solaredge_client import (
        coerce_end_datetime,
        fetch_monthly_time_series,
        month_range,
        month_start_end,
        parse_datetime,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    args = parser.parse_args()

    api_key = os.environ.get("SOLAREDGE_API_KEY")
    site_id = os.environ.get("SOLAREDGE_SITE_ID")

    start = parse_datetime(args.start)
    end = coerce_end_datetime(args.end)
    ensure_dirs()

    for year, month in month_range(start, end):
        cache_path = monthly_cache_path(year, month)
        if cache_path.exists():
            print(f"Using cached {cache_path}")
            continue

        month_start, month_end = month_start_end(year, month)
        if month_end < start or month_start > end:
            continue
        month_start = max(month_start, start)
        month_end = min(month_end, end)

        if not api_key or not site_id:
            print("No API credentials found; skipping fetch for this month.")
            continue

        print(f"Fetching {year:04d}-{month:02d} -> {month_start}..{month_end}")
        monthly_frame = fetch_monthly_time_series(api_key, site_id, month_start, month_end)
        save_monthly_series(monthly_frame, year, month)

    merged = merge_monthly_cache_files()
    if merged.empty:
        print("No time series data found in Raw/. Check raw files or API responses.")
        return

    out = synthesize_target_dataframe(merged)
    out_path = write_merged_csv(out)
    print(f"Wrote merged CSV: {out_path}")


if __name__ == "__main__":
    main()
