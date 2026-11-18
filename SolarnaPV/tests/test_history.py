"""Historical PVGIS acquisition and robustness-report tests."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from solarna.engine import Site, System
from solarna.history import build_historical_range
from solarna.weather import (
    load_hourly_history,
    pvgis_hourly_to_weather,
    validate_historical_weather,
)


def provider_hourly(year=2023):
    hours = 8784 if pd.Timestamp(year, 1, 1).is_leap_year else 8760
    index = pd.date_range(
        f"{year}-01-01 00:09", periods=hours, freq="h", tz="UTC")
    elevation = np.maximum(
        0,
        60 * np.sin(2 * np.pi * (np.arange(hours) % 24 - 6) / 24),
    )
    direct = np.where(elevation > 0, 500 * np.sin(np.radians(elevation)), 0)
    diffuse = np.where(elevation > 0, 100, 0)
    return pd.DataFrame({
        "poa_direct": direct,
        "poa_sky_diffuse": diffuse,
        "poa_ground_diffuse": 0.0,
        "solar_elevation": elevation,
        "temp_air": 20.0,
        "wind_speed": 2.0,
        "Int": 0,
    }, index=index)


def model_weather(start_year=2005, end_year=2006):
    frames = []
    for year in range(start_year, end_year + 1):
        hourly, _ = pvgis_hourly_to_weather(provider_hourly(year))
        frames.append(hourly)
    return pd.concat(frames)


class HistoricalWeatherTests(unittest.TestCase):
    def test_horizontal_components_are_converted_to_weather(self):
        hourly = provider_hourly()
        weather, adjustments = pvgis_hourly_to_weather(hourly)
        self.assertEqual(adjustments, [])
        self.assertEqual(list(weather.columns), [
            "ghi", "dni", "dhi", "temp_air", "wind_speed"])
        daylight = hourly["solar_elevation"] > 0
        self.assertTrue(np.allclose(weather.loc[daylight, "dni"], 500))
        self.assertTrue(np.allclose(
            weather["ghi"],
            hourly["poa_direct"] + hourly["poa_sky_diffuse"],
        ))

    def test_invalid_horizontal_ground_component_is_rejected(self):
        hourly = provider_hourly()
        hourly.loc[hourly.index[0], "poa_ground_diffuse"] = 1
        with self.assertRaises(ValueError):
            pvgis_hourly_to_weather(hourly)

    def test_complete_historical_years_are_required(self):
        weather = model_weather()
        validate_historical_weather(weather, 2005, 2006)
        with self.assertRaises(ValueError):
            validate_historical_weather(weather.iloc[:-1], 2005, 2006)
        with self.assertRaises(ValueError):
            validate_historical_weather(weather, 2004, 2006)

    def test_fetch_then_cache_without_network(self):
        hourly = provider_hourly()
        metadata = {"fixture": "PVGIS hourly history"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch(
                    "solarna.weather.pvlib.iotools.get_pvgis_hourly",
                    return_value=(hourly, metadata)) as fetch:
                first, provenance = load_hourly_history(
                    Site(), root, start_year=2023, end_year=2023)
                self.assertFalse(provenance["cache_hit"])
                self.assertEqual(provenance["timestamp_minute_utc"], 9)
                self.assertEqual(provenance["reconstructed_hours"], 0)
                self.assertEqual(fetch.call_args.kwargs["surface_tilt"], 0)
                self.assertEqual(fetch.call_args.kwargs["surface_azimuth"], 180)
            with patch(
                    "solarna.weather.pvlib.iotools.get_pvgis_hourly",
                    side_effect=AssertionError("Unexpected network")):
                cached, provenance = load_hourly_history(
                    Site(), root, start_year=2023, end_year=2023)
            self.assertTrue(provenance["cache_hit"])
            self.assertEqual(list(first.index), list(cached.index))
            self.assertAlmostEqual(first["ghi"].sum(), cached["ghi"].sum())


class HistoricalRangeTests(unittest.TestCase):
    def test_selected_orientations_are_summarized_by_year(self):
        weather = model_weather()
        provenance = {
            "source": "test history",
            "start_year": 2005,
            "end_year": 2006,
            "timestamp_minute_utc": 9,
        }
        report = {
            "best": {"tilt_deg": 32, "azimuth_deg": 182},
            "baselines": {
                "30_degrees_south": {
                    "tilt_deg": 30,
                    "azimuth_deg": 180,
                },
            },
        }

        def simulated(tilt, azimuth):
            values = np.where(
                weather.index.year == 2005,
                100.0 if (tilt, azimuth) == (32.0, 182.0) else 99.0,
                110.0 if (tilt, azimuth) == (32.0, 182.0) else 108.0,
            )
            if (tilt, azimuth) == (20.0, 180.0):
                values -= 5
            return pd.DataFrame({"ac_w": values}, index=weather.index)

        with patch("solarna.history.EnergyModel") as energy_model:
            energy_model.return_value.simulate.side_effect = simulated
            progress = []
            result = build_historical_range(
                weather,
                provenance,
                Site(),
                System(),
                report,
                existing_orientation=(20, 180),
                progress_callback=lambda done, total: progress.append(
                    (done, total)),
            )

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["year_count"], 2)
        self.assertEqual(progress, [(0, 3), (1, 3), (2, 3), (3, 3)])
        optimum = result["orientations"]["tmy_optimum"]
        self.assertGreater(
            optimum["annual_ac_kwh_by_year"]["2006"],
            optimum["annual_ac_kwh_by_year"]["2005"])
        comparison = result["comparisons"][
            "tmy_optimum_minus_30_degrees_south"]
        self.assertEqual(comparison["years_reference_higher"], 2)
        self.assertIn(
            "tmy_optimum_minus_existing_installation",
            result["comparisons"])


if __name__ == "__main__":
    unittest.main()
