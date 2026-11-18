import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from solarna.__main__ import main
from solarna.engine import Site
from solarna.weather import (
    load_tmy,
    normalize_pvgis_weather,
    pvgis_elevation_m,
)
from test_engine import synthetic_weather


class WeatherTests(unittest.TestCase):
    def test_pvgis_elevation_is_validated(self):
        provenance = {
            "provider_metadata": {
                "inputs": {"location": {"elevation": 247.0}}
            }
        }
        self.assertEqual(pvgis_elevation_m(provenance), 247.0)
        for value in (None, True, "247", float("nan"), -501, 9001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                pvgis_elevation_m({
                    "provider_metadata": {
                        "inputs": {"location": {"elevation": value}}
                    }
                })
        with self.assertRaises(ValueError):
            pvgis_elevation_m({})

    def test_fetch_then_cache_without_network(self):
        weather = synthetic_weather(8760, "1990-01-01")
        metadata = {"test_fixture": "Synthetic clear sky, NOT real PVGIS weather"}
        with tempfile.TemporaryDirectory() as folder:
            with patch("solarna.weather.pvlib.iotools.get_pvgis_tmy", return_value=(weather, metadata)) as fetch:
                first, provenance = load_tmy(Site(), Path(folder))
                self.assertFalse(provenance["cache_hit"])
                self.assertTrue(fetch.call_args.kwargs["usehorizon"])
                self.assertEqual(fetch.call_args.kwargs["coerce_year"], 1990)
            with patch("solarna.weather.pvlib.iotools.get_pvgis_tmy", side_effect=AssertionError("Unexpected network")):
                cached, provenance = load_tmy(Site(), Path(folder))
                self.assertTrue(provenance["cache_hit"])
                self.assertEqual(list(first.index), list(cached.index))
                self.assertAlmostEqual(first["ghi"].sum(), cached["ghi"].sum())
            with patch("solarna.weather.pvlib.iotools.get_pvgis_tmy", return_value=(weather, metadata)) as fetch:
                load_tmy(Site(), Path(folder), refresh=True)
                load_tmy(Site(latitude=36.8, longitude=10.18), Path(folder))
                self.assertEqual(fetch.call_count, 2)

    def test_provider_failure_is_not_replaced_with_synthetic_data(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("solarna.weather.pvlib.iotools.get_pvgis_tmy", side_effect=OSError("offline")):
                with self.assertRaises(OSError):
                    load_tmy(Site(), Path(folder))
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_small_negative_provider_wind_is_clipped_and_recorded(self):
        weather = synthetic_weather(8760, "1990-01-01")
        weather.loc[weather.index[100], "wind_speed"] = -0.67
        metadata = {"test_fixture": "PVGIS provider anomaly fixture"}
        with tempfile.TemporaryDirectory() as folder:
            with patch(
                    "solarna.weather.pvlib.iotools.get_pvgis_tmy",
                    return_value=(weather, metadata)):
                normalized, provenance = load_tmy(Site(), Path(folder))
            self.assertEqual(normalized.iloc[100]["wind_speed"], 0)
            adjustment = provenance["weather_adjustments"][0]
            self.assertEqual(adjustment["field"], "wind_speed")
            self.assertEqual(adjustment["count"], 1)
            self.assertAlmostEqual(adjustment["minimum_original_m_s"], -0.67)

    def test_large_negative_provider_wind_is_rejected(self):
        weather = synthetic_weather(8760, "1990-01-01")
        weather.loc[weather.index[100], "wind_speed"] = -1.01
        with self.assertRaises(ValueError):
            normalize_pvgis_weather(weather)

    def test_invalid_coordinates_fail_before_fetch(self):
        with patch("solarna.__main__.load_tmy") as fetch:
            self.assertEqual(main(["--latitude", "95"]), 1)
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
