from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW_DIR = Path("Raw")
MERGED_DIR = Path("Merged")
MONTHLY_RAW_DIR = RAW_DIR / "monthly"


def ensure_dirs() -> None:
    RAW_DIR.mkdir(exist_ok=True)
    MONTHLY_RAW_DIR.mkdir(exist_ok=True)
    MERGED_DIR.mkdir(exist_ok=True)


def monthly_cache_path(year: int, month: int) -> Path:
    return MONTHLY_RAW_DIR / f"{year:04d}-{month:02d}.csv"


def save_monthly_series(df: pd.DataFrame, year: int, month: int) -> Path:
    payload = df.copy()
    for column in ("timestamp", "consumption", "production", "FeedIn"):
        if column not in payload.columns:
            payload[column] = 0.0
    payload["timestamp"] = pd.to_datetime(payload["timestamp"], errors="coerce")
    payload = payload.dropna(subset=["timestamp"]).sort_values("timestamp")
    path = monthly_cache_path(year, month)
    path.parent.mkdir(exist_ok=True)
    payload.to_csv(path, index=False, encoding="utf-8")
    return path


def load_monthly_series(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8")
    if df.empty:
        return pd.DataFrame(columns=["timestamp", "consumption", "production", "FeedIn"])
    for column in ("timestamp", "consumption", "production", "FeedIn"):
        if column not in df.columns:
            df[column] = 0.0
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for column in ("consumption", "production", "FeedIn"):
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    return df.dropna(subset=["timestamp"]).sort_values("timestamp")


def list_monthly_cache_files() -> list[Path]:
    return sorted(MONTHLY_RAW_DIR.glob("*.csv"))


def write_merged_csv(df, path: Path | None = None) -> Path:
    output_path = path or MERGED_DIR / "merged.csv"
    output_path.parent.mkdir(exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path
