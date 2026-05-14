"""Analysis helpers for battery storage extension potential."""

from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun
import pandas as pd


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


def _sunrise_sunset(
    day: date,
    latitude: float,
    longitude: float,
    timezone: str,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    tz = ZoneInfo(timezone)
    location = LocationInfo(
        name="analysis",
        region="",
        timezone=timezone,
        latitude=latitude,
        longitude=longitude,
    )
    sun_times = sun(location.observer, date=day, tzinfo=tz)
    return sun_times["sunrise"], sun_times["sunset"]


def analyze_battery_extension_potential(
    df: pd.DataFrame,
    additional_storage_capacity_kwh: float | None = None,
    export_column: str = "Ins Netz (kW)",
    generation_column: str | None = "Produktion (kW)",
    grid_import_column: str = "Vom Netz (kW)",
    latitude: float = 52.52,
    longitude: float = 10.45,
    timezone: str = "Europe/Berlin",
) -> pd.DataFrame:
    """Estimate how much day surplus could support the upcoming night.

    Extra energy exported during daylight is treated as storable energy for the
    upcoming night, limited by the available extra battery capacity.
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
    df.index = _localize_index(df, timezone)
    df = df.sort_index()

    duration_hours = _get_interval_hours(df)
    analysis = []
    dates = sorted({timestamp.date() for timestamp in df.index})

    for current_date in dates:
        sunrise = _sunrise_sunset(current_date, latitude, longitude, timezone)[0]
        sunset = _sunrise_sunset(current_date, latitude, longitude, timezone)[1]
        next_sunrise = _sunrise_sunset(current_date + timedelta(days=1), latitude, longitude, timezone)[0]

        day_group = df[(df.index >= sunrise) & (df.index < sunset)]
        night_group = df[(df.index >= sunset) & (df.index < next_sunrise)]

        day_export = (day_group[export_column] * duration_hours).sum()
        night_grid = (night_group[grid_import_column] * duration_hours).sum()
        day_generation = (
            (day_group[generation_column] * duration_hours).sum()
            if generation_column is not None
            else 0.0
        )
        energy_stored_limited = (
            day_export
            if additional_storage_capacity_kwh is None
            else min(day_export, additional_storage_capacity_kwh)
        )
        energy_stored_unlimited = day_export
        coverage_limited = min(energy_stored_limited, night_grid)
        coverage_unlimited = min(energy_stored_unlimited, night_grid)
        spilled_day_export = (
            0.0
            if additional_storage_capacity_kwh is None
            else max(0.0, day_export - additional_storage_capacity_kwh)
        )

        analysis.append(
            {
                "day": current_date,
                "day_generation_kwh": float(day_generation),
                "day_export_kwh": float(day_export),
                "energy_stored_kwh": float(energy_stored_limited),
                "energy_stored_unlimited_kwh": float(energy_stored_unlimited),
                "night_grid_kwh": float(night_grid),
                "potential_night_coverage_kwh": float(coverage_limited),
                "potential_night_coverage_unlimited_kwh": float(coverage_unlimited),
                "unserved_night_kwh": float(max(0.0, night_grid - coverage_limited)),
                "spilled_day_export_kwh": float(spilled_day_export),
            }
        )

    result = pd.DataFrame.from_records(analysis).set_index("day")
    return result


def summarize_extension_potential(analysis_df: pd.DataFrame) -> dict[str, float]:
    """Return an aggregated summary of battery extension potential."""
    total_generation = float(analysis_df["day_generation_kwh"].sum())
    total_export = float(analysis_df["day_export_kwh"].sum())
    total_stored = float(analysis_df["energy_stored_kwh"].sum())
    total_unlimited_stored = float(analysis_df["energy_stored_unlimited_kwh"].sum())
    total_spilled = float(analysis_df["spilled_day_export_kwh"].sum())
    total_night = float(analysis_df["night_grid_kwh"].sum())
    total_covered = float(analysis_df["potential_night_coverage_kwh"].sum())
    total_covered_unlimited = float(analysis_df["potential_night_coverage_unlimited_kwh"].sum())
    total_unserved = float(analysis_df["unserved_night_kwh"].sum())

    return {
        "total_day_generation_kwh": total_generation,
        "total_day_export_kwh": total_export,
        "total_energy_stored_kwh": total_stored,
        "total_energy_stored_unlimited_kwh": total_unlimited_stored,
        "total_spilled_day_export_kwh": total_spilled,
        "total_night_grid_kwh": total_night,
        "total_potential_coverage_kwh": total_covered,
        "total_potential_coverage_unlimited_kwh": total_covered_unlimited,
        "total_unserved_night_kwh": total_unserved,
        "coverage_ratio": float(total_covered / total_night if total_night else 0.0),
        "coverage_ratio_unlimited": float(total_covered_unlimited / total_night if total_night else 0.0),
    }
