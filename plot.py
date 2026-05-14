"""Plot helpers for solar power chart data."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import pandas as pd

DEFAULT_COLUMNS = [
    "Produktion (kW)",
    "Verbrauch (kW)",
    "Aus Solarenergie (kW)",
    "Vom Netz (kW)",
]


def plot_power_chart(
    df: pd.DataFrame,
    columns: Iterable[str] | None = None,
    title: str | None = None,
    output_path: Path | None = None,
    show: bool = True,
) -> None:
    columns = list(columns) if columns else DEFAULT_COLUMNS
    actual_columns = [col for col in columns if col in df.columns]
    if not actual_columns:
        raise ValueError(f"None of the requested columns were found in the CSV: {columns}")

    plt.figure(figsize=(14, 7))
    df[actual_columns].plot()
    plt.title(title or "Power chart overview")
    plt.xlabel("Time")
    plt.ylabel("kW")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()

    if output_path:
        output_path = output_path.expanduser()
        plt.savefig(output_path, dpi=150)
        print(f"Saved plot to: {output_path}")

    if show:
        plt.show()
    else:
        plt.close()
