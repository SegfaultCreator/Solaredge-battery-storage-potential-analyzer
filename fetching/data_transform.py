from __future__ import annotations

import pandas as pd

try:
    from .data_cache import list_monthly_cache_files, load_monthly_series
except ImportError:  # pragma: no cover
    from data_cache import list_monthly_cache_files, load_monthly_series


def merge_monthly_cache_files() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in list_monthly_cache_files():
        monthly_frame = load_monthly_series(path)
        if monthly_frame.empty:
            continue
        frames.append(monthly_frame)

    if not frames:
        return pd.DataFrame(columns=["timestamp", "consumption", "production", "FeedIn"])

    merged = pd.concat(frames, axis=0, ignore_index=True)
    merged["timestamp"] = pd.to_datetime(merged["timestamp"], errors="coerce")
    merged = merged.dropna(subset=["timestamp"]).sort_values("timestamp")
    return merged.groupby("timestamp", as_index=False).sum()


def synthesize_target_dataframe(merged: pd.DataFrame) -> pd.DataFrame:
    if merged.empty:
        return pd.DataFrame(
            columns=[
                "Messzeit",
                "Produktion (kW)",
                "Ins Gebäude (kW)",
                "Ins Netz (kW)",
                "Zum Speicher (kW)",
                "Verbrauch (kW)",
                "Aus PV-Energie (kW)",
                "Vom Netz (kW)",
                "Vom Speicher (kW)",
            ]
        )

    frame = merged.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp")
    for column in ("consumption", "production", "FeedIn"):
        if column not in frame.columns:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)

    return pd.DataFrame(
        {
            "Messzeit": frame["timestamp"],
            "Produktion (kW)": frame["production"],
            "Ins Gebäude (kW)": frame["consumption"],
            "Ins Netz (kW)": frame["FeedIn"],
            "Zum Speicher (kW)": 0.0,
            "Verbrauch (kW)": frame["consumption"],
            "Aus PV-Energie (kW)": frame["production"],
            "Vom Netz (kW)": 0.0,
            "Vom Speicher (kW)": 0.0,
        }
    )
