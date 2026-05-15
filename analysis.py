"""Analysis helpers for battery storage extension potential."""

from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

import pandas as pd


@dataclass
class Battery:
    capacity_kwh: float | None
    charge_kwh: float = 0.0

    def store(self, amount_kwh: float) -> float:
        """Store energy, return amount actually stored."""
        if amount_kwh <= 0:
            return 0.0
        if self.capacity_kwh is None:
            self.charge_kwh += amount_kwh
            return amount_kwh
        available = self.capacity_kwh - self.charge_kwh
        stored = min(amount_kwh, available)
        self.charge_kwh += stored
        return stored

    def discharge(self, amount_kwh: float) -> float:
        """Discharge energy, return amount actually provided."""
        if amount_kwh <= 0:
            return 0.0
        provided = min(amount_kwh, self.charge_kwh)
        self.charge_kwh -= provided
        return provided


def _get_interval_hours(df: pd.DataFrame) -> float:
    if df.index.inferred_freq:
        freq = pd.tseries.frequencies.to_offset(df.index.inferred_freq)
        return pd.Timedelta(freq).total_seconds() / 3600

    delta = df.index.to_series().diff().dropna()
    if delta.empty:
        raise ValueError("Unable to infer row interval from the DataFrame index.")

    return delta.median().total_seconds() / 3600


def _localize_index(df: pd.DataFrame, timezone: str) -> pd.DatetimeIndex:
    tz = ZoneInfo(timezone)
    if df.index.tzinfo is None:
        return df.index.tz_localize(tz)
    return df.index.tz_convert(tz)


def analyze_battery_extension_potential(
    df: pd.DataFrame,
    additional_storage_capacity_kwh: float | None = None,
    export_column: str = "Ins Netz (kW)",
    generation_column: str | None = "Produktion (kW)",
    grid_import_column: str = "Vom Netz (kW)",
) -> pd.DataFrame:
    """Simulate battery storage behavior using generic battery models.

    Processes data chronologically, storing excess export and discharging for grid imports.
    """

    if export_column not in df.columns:
        raise KeyError(f"Expected export column not found: {export_column}")
    if grid_import_column not in df.columns:
        raise KeyError(f"Expected grid import column not found: {grid_import_column}")
    if generation_column is not None and generation_column not in df.columns:
        raise KeyError(f"Expected generation column not found: {generation_column}")
    if additional_storage_capacity_kwh is not None and additional_storage_capacity_kwh < 0:
        raise ValueError("additional_storage_capacity_kwh must be non-negative")

    df = df.copy()
    df = df.sort_index()

    duration_hours = _get_interval_hours(df)
    analysis = []
    dates = sorted({timestamp.date() for timestamp in df.index})

    # Initialize batteries once for the entire period
    battery_limited = Battery(capacity_kwh=additional_storage_capacity_kwh)
    battery_unlimited = Battery(capacity_kwh=None)

    for current_date in dates:
        day_data = df[df.index.date == current_date]

        # Aggregate for summary
        day_generation = (
            (day_data[generation_column] * duration_hours).sum()
            if generation_column is not None
            else 0.0
        )
        day_export_total = (day_data[export_column] * duration_hours).sum()
        day_import_total = (day_data[grid_import_column] * duration_hours).sum()

        stored_this_day_limited = 0.0
        stored_this_day_unlimited = 0.0
        covered_limited = 0.0
        covered_unlimited = 0.0

        # Process each row chronologically
        for _, row in day_data.iterrows():
            export_kwh = row[export_column] * duration_hours
            import_kwh = row[grid_import_column] * duration_hours

            # Store excess export
            stored_this_day_limited += battery_limited.store(export_kwh)
            stored_this_day_unlimited += battery_unlimited.store(export_kwh)

            # Discharge for grid import
            covered_limited += battery_limited.discharge(import_kwh)
            covered_unlimited += battery_unlimited.discharge(import_kwh)

        analysis.append(
            {
                "day": current_date,
                "day_generation_kwh": float(day_generation),
                "day_export_kwh": float(day_export_total),
                "day_import_kwh": float(day_import_total),
                "charged_to_battery_limited_kwh": float(stored_this_day_limited),
                "charged_to_battery_unlimited_kwh": float(stored_this_day_unlimited),
                "energy_stored_cumulative_limited_kwh": float(battery_limited.charge_kwh),
                "energy_stored_cumulative_unlimited_kwh": float(battery_unlimited.charge_kwh),
                "provided_from_battery_limited_kwh": float(covered_limited),
                "provided_from_battery_unlimited_kwh": float(covered_unlimited),
                "unserved_import_this_day_kwh": float(max(0.0, day_import_total - covered_limited)),
            }
        )

    result = pd.DataFrame.from_records(analysis).set_index("day")
    return result


def summarize_extension_potential(analysis_df: pd.DataFrame) -> dict[str, float]:
    """Return an aggregated summary of battery extension potential."""
    total_generation = float(analysis_df["day_generation_kwh"].sum())
    total_export = float(analysis_df["day_export_kwh"].sum())
    total_import = float(analysis_df["day_import_kwh"].sum())
    total_charged_to_battery_limited = float(analysis_df["charged_to_battery_limited_kwh"].sum())
    total_charged_to_battery_unlimited = float(analysis_df["charged_to_battery_unlimited_kwh"].sum())
    total_stored_cumulative_limited = float(analysis_df["energy_stored_cumulative_limited_kwh"].iloc[-1] if not analysis_df.empty else 0.0)
    total_stored_cumulative_unlimited = float(analysis_df["energy_stored_cumulative_unlimited_kwh"].iloc[-1] if not analysis_df.empty else 0.0)
    total_provided_from_battery_limited = float(analysis_df["provided_from_battery_limited_kwh"].sum())
    total_provided_from_battery_unlimited = float(analysis_df["provided_from_battery_unlimited_kwh"].sum())
    total_unserved = float(analysis_df["unserved_import_this_day_kwh"].sum())

    return {
        "total_day_generation_kwh": total_generation,
        "total_day_export_kwh": total_export,
        "total_day_import_kwh": total_import,
        "total_charged_to_battery_limited_kwh": total_charged_to_battery_limited,
        "total_charged_to_battery_unlimited_kwh": total_charged_to_battery_unlimited,
        "final_energy_stored_limited_kwh": total_stored_cumulative_limited,
        "final_energy_stored_unlimited_kwh": total_stored_cumulative_unlimited,
        "total_provided_from_battery_limited_kwh": total_provided_from_battery_limited,
        "total_provided_from_battery_unlimited_kwh": total_provided_from_battery_unlimited,
        "total_unserved_import_kwh": total_unserved,
        "coverage_ratio_limited": float(total_provided_from_battery_limited / total_import if total_import else 0.0),
        "coverage_ratio_unlimited": float(total_provided_from_battery_unlimited / total_import if total_import else 0.0),
    }
