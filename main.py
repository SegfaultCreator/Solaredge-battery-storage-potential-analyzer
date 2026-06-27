
"""CLI entry point for the solar power chart tool."""

from __future__ import annotations

import argparse
from pathlib import Path

from analysis import analyze_battery_extension_potential, summarize_extension_potential
from data import DEFAULT_CSV, load_power_chart
from plot import plot_power_chart


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot Solar power chart data from CSV.")
    parser.add_argument(
        "--file",
        "-f",
        type=Path,
        default=DEFAULT_CSV,
        help="Path to the power chart CSV file.",
    )
    parser.add_argument(
        "--columns",
        "-c",
        nargs="+",
        help="Column names to plot. If omitted, defaults to production and consumption metrics.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Optional path to save the generated plot image.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not display the plot interactively.",
    )
    parser.add_argument(
        "--storage-capacity",
        "-s",
        type=float,
        help="Additional battery storage capacity in kWh for the analysis.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = load_power_chart(args.file)

    analysis = analyze_battery_extension_potential(
        df,
        additional_storage_capacity_kwh=args.storage_capacity,
    )
    summary = summarize_extension_potential(analysis)

    print("Battery extension potential summary:")
    if args.storage_capacity is not None:
        print(f"  Additional storage capacity: {args.storage_capacity:.2f} kWh")
    else:
        print("  Additional storage capacity: unlimited")
    print(f"  Total day generation: {summary['total_day_generation_kwh']:.2f} kWh")
    print(f"  Total day export: {summary['total_day_export_kwh']:.2f} kWh")
    print(f"  Total day import: {summary['total_day_import_kwh']:.2f} kWh")
    print(f"  Total unserved import: {summary['total_unserved_import_kwh']:.2f} kWh")
    print(f"  Potential coverage with specified size: {summary['total_provided_from_battery_limited_kwh']:.2f} kWh")
    print(f"  Potential coverage unlimited: {summary['total_provided_from_battery_unlimited_kwh']:.2f} kWh")
    print(f"  Coverage ratio (limited): {summary['coverage_ratio_limited']:.2%}")
    print(f"  Coverage ratio (unlimited): {summary['coverage_ratio_unlimited']:.2%}")

    plot_power_chart(
        df,
        columns=args.columns,
        output_path=args.output,
        show=not args.no_show,
    )


if __name__ == "__main__":
    main()
