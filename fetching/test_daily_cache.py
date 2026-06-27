from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from fetching import data_cache
from fetching.data_transform import merge_monthly_cache_files, synthesize_target_dataframe
from fetching.solaredge_client import build_monthly_time_series, flatten_power_details_payload


class DailyCacheTests(unittest.TestCase):
    def test_flatten_power_details_payload_to_long_format(self) -> None:
        payload = {
            "powerDetails": {
                "meters": [
                    {
                        "type": "Production",
                        "values": [
                            {"date": "2026-01-01 00:00:00", "value": 100.0},
                            {"date": "2026-01-01 00:15:00", "value": 200.0},
                        ],
                    }
                ]
            }
        }

        df = flatten_power_details_payload(payload)

        self.assertEqual(list(df.columns), ["timestamp", "meter_type", "value"])
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]["meter_type"], "Production")
        self.assertEqual(df.iloc[1]["value"], 200.0)

    def test_merge_monthly_cache_files_pivots_to_timeseries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_cache.RAW_DIR = Path(tmpdir)
            data_cache.MERGED_DIR = Path(tmpdir) / "Merged"
            data_cache.RAW_DIR.mkdir(exist_ok=True)
            data_cache.MERGED_DIR.mkdir(exist_ok=True)

            first_month = pd.DataFrame(
                [
                    {"timestamp": "2026-01-01 00:00:00", "consumption": 1.0, "production": 2.0, "FeedIn": 0.5},
                    {"timestamp": "2026-01-01 00:15:00", "consumption": 2.0, "production": 3.0, "FeedIn": 1.0},
                ]
            )
            second_month = pd.DataFrame(
                [
                    {"timestamp": "2026-02-01 00:00:00", "consumption": 3.0, "production": 4.0, "FeedIn": 1.5},
                ]
            )

            data_cache.save_monthly_series(first_month, 2026, 1)
            data_cache.save_monthly_series(second_month, 2026, 2)

            merged = merge_monthly_cache_files()
            self.assertEqual(list(merged.columns), ["timestamp", "consumption", "production", "FeedIn"])
            self.assertEqual(merged.iloc[0]["timestamp"].strftime("%Y-%m-%d %H:%M:%S"), "2026-01-01 00:00:00")
            self.assertEqual(float(merged.iloc[0]["production"]), 2.0)

            target = synthesize_target_dataframe(merged)
            self.assertEqual(
                list(target.columns),
                [
                    "Messzeit",
                    "Produktion (kW)",
                    "Ins Gebäude (kW)",
                    "Ins Netz (kW)",
                    "Zum Speicher (kW)",
                    "Verbrauch (kW)",
                    "Aus PV-Energie (kW)",
                    "Vom Netz (kW)",
                    "Vom Speicher (kW)",
                ],
            )
            self.assertEqual(float(target.iloc[0]["Produktion (kW)"]), 2.0)
            self.assertEqual(float(target.iloc[0]["Verbrauch (kW)"]), 1.0)


if __name__ == "__main__":
    unittest.main()
