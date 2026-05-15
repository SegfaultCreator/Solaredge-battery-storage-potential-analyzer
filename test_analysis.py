"""Test cases for battery analysis."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

import pandas as pd

from analysis import analyze_battery_extension_potential, summarize_extension_potential


class TestBatteryAnalysis(unittest.TestCase):
    def setUp(self):
        # Base date for tests
        self.base_date = datetime(2026, 5, 14)

    def _create_test_data(self, generation_profile: dict, import_profile: dict) -> pd.DataFrame:
        """Create test DataFrame with hourly data from 8am to 8pm."""
        data = []
        for hour in range(0, 24):  # 8am to 8pm
            timestamp = self.base_date.replace(hour=hour)
            row = {
                "Messzeit": timestamp.strftime("%d. %B %Y %H:%M"),
                "Produktion (kW)": generation_profile.get(hour, 0.0),
                "Ins Netz (kW)": generation_profile.get(hour, 0.0),  # Assuming export = generation for simplicity
                "Vom Netz (kW)": import_profile.get(hour, 0.0),
            }
            data.append(row)

        df = pd.DataFrame(data)
        df["Messzeit"] = pd.to_datetime(df["Messzeit"], dayfirst=True, errors="coerce")
        df = df.set_index("Messzeit")
        return df

    def test_case_1_excess_1kwh_consumption_1kwh(self):
        """Test case 1: 1 kWh generation 8am-4pm, 1 kWh consumption 4pm-8pm."""
        generation = {h: 1.0 for h in range(8, 16)}  
        consumption = {h: 1.0 for h in range(16, 24)} 

        df = self._create_test_data(generation, consumption)
        result = analyze_battery_extension_potential(df, additional_storage_capacity_kwh=4.0)

        self.assertAlmostEqual(result.loc[self.base_date.date(), "charged_to_battery_unlimited_kwh"], 8.0, places=1)
        self.assertAlmostEqual(result.loc[self.base_date.date(), "charged_to_battery_limited_kwh"], 4.0, places=1)
        self.assertAlmostEqual(result.loc[self.base_date.date(), "provided_from_battery_limited_kwh"], 4.0, places=1)
        self.assertAlmostEqual(result.loc[self.base_date.date(), "provided_from_battery_unlimited_kwh"], 8.0, places=1)
        self.assertAlmostEqual(result.loc[self.base_date.date(), "energy_stored_cumulative_limited_kwh"], 0.0, places=1)
        self.assertAlmostEqual(result.loc[self.base_date.date(), "energy_stored_cumulative_unlimited_kwh"], 0.0, places=1)

    def test_case_2_two_day_carryover(self):
        """Test case 2: 2-day battery carryover with post-day consumption."""
        data = []
        for day_offset in range(2):
            current_date = self.base_date + timedelta(days=day_offset)
            for hour in range(24):
                timestamp = current_date.replace(hour=hour)
                generation = 1.0 if 8 <= hour < 16 else 0.0
                consumption = 0.0
                if day_offset == 1 and 16 <= hour < 24:
                    consumption = 2.0
                data.append({
                    "Messzeit": timestamp.strftime("%d. %B %Y %H:%M"),
                    "Produktion (kW)": generation,
                    "Ins Netz (kW)": generation,
                    "Vom Netz (kW)": consumption,
                })

        df = pd.DataFrame(data)
        df["Messzeit"] = pd.to_datetime(df["Messzeit"], dayfirst=True, errors="coerce")
        df = df.set_index("Messzeit")

        result = analyze_battery_extension_potential(df, additional_storage_capacity_kwh=4.0)
        summary = summarize_extension_potential(result)

        self.assertAlmostEqual(summary["total_provided_from_battery_limited_kwh"], 4.0, places=1)
        self.assertAlmostEqual(summary["total_provided_from_battery_unlimited_kwh"], 16.0, places=1)
        self.assertAlmostEqual(summary["final_energy_stored_limited_kwh"], 0.0, places=1)
        self.assertAlmostEqual(summary["final_energy_stored_unlimited_kwh"], 0.0, places=1)

    def test_case_3_three_day_with_day2_and_day3_consumption(self):
        """Test case 3: 3-day sequence with consumption on days 2 and 3 only."""
        data = []
        for day_offset in range(3):
            current_date = self.base_date + timedelta(days=day_offset)
            for hour in range(24):
                timestamp = current_date.replace(hour=hour)
                generation = 1.0 if 8 <= hour < 16 else 0.0
                consumption = 1.0 if day_offset >= 1 and 16 <= hour < 20 else 0.0
                data.append({
                    "Messzeit": timestamp.strftime("%d. %B %Y %H:%M"),
                    "Produktion (kW)": generation,
                    "Ins Netz (kW)": generation,
                    "Vom Netz (kW)": consumption,
                })

        df = pd.DataFrame(data)
        df["Messzeit"] = pd.to_datetime(df["Messzeit"], dayfirst=True, errors="coerce")
        df = df.set_index("Messzeit")

        result = analyze_battery_extension_potential(df, additional_storage_capacity_kwh=4.0)
        summary = summarize_extension_potential(result)

        self.assertAlmostEqual(summary["total_provided_from_battery_limited_kwh"], 8.0, places=1)
        self.assertAlmostEqual(summary["total_provided_from_battery_unlimited_kwh"], 8.0, places=1)
        self.assertAlmostEqual(summary["final_energy_stored_limited_kwh"], 0.0, places=1)
        self.assertAlmostEqual(summary["final_energy_stored_unlimited_kwh"], 16.0, places=1)
        self.assertAlmostEqual(summary["total_charged_to_battery_limited_kwh"], 8.0, places=1)
        self.assertAlmostEqual(summary["total_charged_to_battery_unlimited_kwh"], 24.0, places=1)


    def test_case_4_three_day_each_complete_charge_discharge_100_coverage(self):
        """Test case 3: 3-day sequence with consumption on days 2 and 3 only."""
        data = []
        for day_offset in range(3):
            current_date = self.base_date + timedelta(days=day_offset)
            for hour in range(24):
                timestamp = current_date.replace(hour=hour)
                generation = 0.5 if 8 <= hour < 16 else 0.0
                consumption = 0.5 if 16 <= hour else 0.0
                data.append({
                    "Messzeit": timestamp.strftime("%d. %B %Y %H:%M"),
                    "Produktion (kW)": generation,
                    "Ins Netz (kW)": generation,
                    "Vom Netz (kW)": consumption,
                })

        df = pd.DataFrame(data)
        df["Messzeit"] = pd.to_datetime(df["Messzeit"], dayfirst=True, errors="coerce")
        df = df.set_index("Messzeit")

        result = analyze_battery_extension_potential(df, additional_storage_capacity_kwh=4.0)
        summary = summarize_extension_potential(result)

        self.assertAlmostEqual(summary["total_provided_from_battery_limited_kwh"], 12.0, places=1)
        self.assertAlmostEqual(summary["total_provided_from_battery_unlimited_kwh"], 12.0, places=1)
        
        # Not really necessary, since it is the same as above on average
        self.assertAlmostEqual(summary["total_charged_to_battery_limited_kwh"], 12.0, places=1)
        self.assertAlmostEqual(summary["total_charged_to_battery_unlimited_kwh"], 12.0, places=1)
        
        self.assertAlmostEqual(summary["final_energy_stored_limited_kwh"], 0.0, places=1)
        self.assertAlmostEqual(summary["final_energy_stored_unlimited_kwh"], 0.0, places=1)

    def test_case_5_three_day_each_complete_charge_discharge_50_coverage(self):
        """Test case 3: 3-day sequence with consumption on days 2 and 3 only."""
        data = []
        for day_offset in range(3):
            current_date = self.base_date + timedelta(days=day_offset)
            for hour in range(24):
                timestamp = current_date.replace(hour=hour)
                generation = 1.0 if 8 <= hour < 16 else 0.0
                consumption = 1.0 if 16 <= hour else 0.0
                data.append({
                    "Messzeit": timestamp.strftime("%d. %B %Y %H:%M"),
                    "Produktion (kW)": generation,
                    "Ins Netz (kW)": generation,
                    "Vom Netz (kW)": consumption,
                })

        df = pd.DataFrame(data)
        df["Messzeit"] = pd.to_datetime(df["Messzeit"], dayfirst=True, errors="coerce")
        df = df.set_index("Messzeit")

        result = analyze_battery_extension_potential(df, additional_storage_capacity_kwh=4.0)
        summary = summarize_extension_potential(result)

        self.assertAlmostEqual(summary["total_provided_from_battery_limited_kwh"], 12.0, places=1)
        self.assertAlmostEqual(summary["total_provided_from_battery_unlimited_kwh"], 24.0, places=1)
        
        self.assertAlmostEqual(summary["final_energy_stored_limited_kwh"], 0.0, places=1)
        self.assertAlmostEqual(summary["final_energy_stored_unlimited_kwh"], 0.0, places=1)


    def test_case_6_three_day_each_complete_charge_partial_discharge(self):
        """Test case 3: 3-day sequence with consumption on days 2 and 3 only."""
        data = []
        for day_offset in range(3):
            current_date = self.base_date + timedelta(days=day_offset)
            for hour in range(24):
                timestamp = current_date.replace(hour=hour)
                generation = 0.5 if 8 <= hour < 16 else 0.0
                consumption = 0.5 if 16 <= hour < 20 else 0.0
                data.append({
                    "Messzeit": timestamp.strftime("%d. %B %Y %H:%M"),
                    "Produktion (kW)": generation,
                    "Ins Netz (kW)": generation,
                    "Vom Netz (kW)": consumption,
                })

        df = pd.DataFrame(data)
        df["Messzeit"] = pd.to_datetime(df["Messzeit"], dayfirst=True, errors="coerce")
        df = df.set_index("Messzeit")

        result = analyze_battery_extension_potential(df, additional_storage_capacity_kwh=4.0)
        summary = summarize_extension_potential(result)

        self.assertAlmostEqual(summary["total_provided_from_battery_limited_kwh"], 6.0, places=1)
        self.assertAlmostEqual(summary["total_provided_from_battery_unlimited_kwh"], 6.0, places=1)
        
        self.assertAlmostEqual(summary["final_energy_stored_limited_kwh"], 2.0, places=1)
        self.assertAlmostEqual(summary["final_energy_stored_unlimited_kwh"], 6.0, places=1)

    # def test_case_2_excess_1kwh_consumption_2kwh(self):
    #     """Test case 2: 1 kWh generation 8am-4pm, 2 kWh consumption 4pm-8pm."""
    #     generation = {h: 1.0 for h in range(8, 17)}
    #     consumption = {h: 2.0 for h in range(17, 21)}

    #     df = self._create_test_data(generation, consumption)
    #     result = analyze_battery_extension_potential(df, additional_storage_capacity_kwh=5.0)

    #     # Stores 5 kWh, discharges 8 kWh but only has 5, so covers 5 kWh, unserved 3 kWh
    #     self.assertAlmostEqual(result.loc[self.base_date.date(), "day_export_kwh"], 8.0, places=1)
    #     self.assertAlmostEqual(result.loc[self.base_date.date(), "day_import_kwh"], 8.0, places=1)
    #     self.assertAlmostEqual(result.loc[self.base_date.date(), "potential_coverage_limited_kwh"], 5.0, places=1)
    #     self.assertAlmostEqual(result.loc[self.base_date.date(), "unserved_import_kwh"], 3.0, places=1)
    #     self.assertAlmostEqual(result.loc[self.base_date.date(), "energy_stored_limited_kwh"], 0.0, places=1)  # Depleted

    # def test_case_3_excess_2kwh_consumption_1kwh(self):
    #     """Test case 3: 2 kWh generation 8am-4pm, 1 kWh consumption 4pm-8pm."""
    #     generation = {h: 2.0 for h in range(8, 17)}
    #     consumption = {h: 1.0 for h in range(17, 21)}

    #     df = self._create_test_data(generation, consumption)
    #     result = analyze_battery_extension_potential(df, additional_storage_capacity_kwh=5.0)

    #     # Stores 5 kWh (reaches limit after 3 hours), then continues storing but capped.
    #     # Discharges 4 kWh, fully covered.
    #     self.assertAlmostEqual(result.loc[self.base_date.date(), "day_export_kwh"], 16.0, places=1)  # 8*2
    #     self.assertAlmostEqual(result.loc[self.base_date.date(), "day_import_kwh"], 4.0, places=1)
    #     self.assertAlmostEqual(result.loc[self.base_date.date(), "potential_coverage_limited_kwh"], 4.0, places=1)
    #     self.assertAlmostEqual(result.loc[self.base_date.date(), "energy_stored_limited_kwh"], 1.0, places=1)  # 5 - 4


if __name__ == "__main__":
    unittest.main()