"""CSV data loader for the solar power chart."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DEFAULT_CSV = Path("power-chart-data 05_14_2026 08_53 PM.csv")
MONTHS_GERMAN = {
    "Januar": "January",
    "Februar": "February",
    "März": "March",
    "April": "April",
    "Mai": "May",
    "Juni": "June",
    "Juli": "July",
    "August": "August",
    "September": "September",
    "Oktober": "October",
    "November": "November",
    "Dezember": "December",
}


def parse_german_datetime(value: str) -> pd.Timestamp:
    value = value.strip().strip('"')
    for german, english in MONTHS_GERMAN.items():
        if german in value:
            value = value.replace(german, english)
            break
    return pd.to_datetime(value, dayfirst=True, errors="coerce")


def load_power_chart(path: Path) -> pd.DataFrame:
    path = path.expanduser()
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    df = pd.read_csv(
        path,
        encoding="utf-8-sig",
        quotechar='"',
        delimiter=",",
    )

    if "Messzeit" not in df.columns:
        raise ValueError("Expected a 'Messzeit' column in the Power chart CSV.")

    df["Messzeit"] = df["Messzeit"].apply(parse_german_datetime)
    df = df.dropna(subset=["Messzeit"]).set_index("Messzeit")

    numeric_columns = [col for col in df.columns if col != "Messzeit"]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", "."), errors="coerce")

    return df
