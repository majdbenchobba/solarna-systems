"""PVGIS PVcalc benchmark tests; all provider responses are offline fixtures."""

from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from solarna.benchmark import (
    approximate_pvgis_system_loss_percent,
    compare_with_report,
    load_pvgis_benchmark,
    pvgis_aspect_to_true_north,
)
from solarna.engine import Site, System


def pvgis_payload():
    return {
        "inputs": {
            "location": {
                "latitude": 34.7406,
                "longitude": 10.7603,
                "elevation": 20,
            },
            "meteo_data": {
                "radiation_db": "PVGIS-SARAH3",
                "year_min": 2005,
                "year_max": 2023,
            },
            "mounting_system": {
                "fixed": {
                    "slope": {"value": 31, "optimal": True},
                    "azimuth": {"value": -2, "optimal": True},
                }
            },
        },
        "outputs": {
            "monthly": {
                "fixed": [
                    {
                        "month": month,
                        "E_m": 120 + month,
                        "H(i)_m": 130 + month,
                        "SD_m": 4,
                    }
                    for month in range(1, 13)
                ]
            },
            "totals": {
                "fixed": {
                    "E_y": 1780.0,
                    "H(i)_y": 2130.0,
                    "SD_y": 72.0,
                    "l_aoi": -2.5,
                    "l_spec": "0.48",
                    "l_tg": -7.8,
                    "l_total": -14.3,
                }
            },
        },
        "meta": {"inputs": {}, "outputs": {}},
    }


class FakeResponse:
    def __init__(self, payload):
        self.status = 200
        self._stream = BytesIO(json.dumps(payload).encode("utf-8"))

    def read(self):
        return self._stream.read()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class BenchmarkTests(unittest.TestCase):
    def test_angle_and_loss_conventions(self):
        self.assertEqual(pvgis_aspect_to_true_north(0), 180)
        self.assertEqual(pvgis_aspect_to_true_north(90), 270)
        self.assertEqual(pvgis_aspect_to_true_north(-90), 90)
        system = System(inverter_efficiency=0.96, other_dc_loss_fraction=0.05)
        self.assertAlmostEqual(
            approximate_pvgis_system_loss_percent(system), 8.8)

    def test_fetch_normalize_then_cache_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch(
                    "solarna.benchmark.urlopen",
                    return_value=FakeResponse(pvgis_payload())) as fetch:
                first = load_pvgis_benchmark(
                    Site(), System(), Path(folder), timeout=4)
            request = fetch.call_args.args[0]
            query = parse_qs(urlsplit(request.full_url).query)
            self.assertEqual(query["optimalangles"], ["1"])
            self.assertEqual(query["raddatabase"], ["PVGIS-SARAH3"])
            self.assertEqual(query["peakpower"], ["1.0"])
            self.assertEqual(query["loss"], ["4.0"])
            self.assertEqual(first["pvgis_result"]["tilt_deg"], 31)
            self.assertEqual(
                first["pvgis_result"]["azimuth_deg_true_north"], 178)
            self.assertEqual(
                first["pvgis_result"]["provider_loss_breakdown_percent"]["l_spec"],
                0.48)
            self.assertFalse(first["cache_hit"])
            with patch(
                    "solarna.benchmark.urlopen",
                    side_effect=AssertionError("unexpected network")):
                second = load_pvgis_benchmark(Site(), System(), Path(folder))
            self.assertTrue(second["cache_hit"])
            self.assertEqual(
                second["pvgis_result"]["annual_ac_kwh_per_kwp"], 1780)

    def test_comparison_math_and_malformed_response(self):
        benchmark = {
            "status": "available",
            "pvgis_result": {
                "tilt_deg": 31,
                "azimuth_deg_true_north": 178,
                "annual_ac_kwh_per_kwp": 1780,
                "monthly_ac_kwh_per_kwp": {
                    str(month): 100 for month in range(1, 13)
                },
            },
        }
        report = {
            "system": {"dc_capacity_kw": 2},
            "best": {
                "tilt_deg": 32,
                "azimuth_deg": 182,
                "specific_yield_kwh_per_kwp": 1800,
                "monthly_ac_kwh": {
                    str(month): 220 for month in range(1, 13)
                },
            },
        }
        compared = compare_with_report(report, benchmark)["comparison"]
        self.assertEqual(compared["tilt_delta_deg"], 1)
        self.assertEqual(compared["azimuth_delta_deg"], 4)
        self.assertAlmostEqual(
            compared["specific_yield_delta_percent_of_pvgis"],
            100 * (1800 / 1780 - 1))
        self.assertEqual(compared["monthly_mae_kwh_per_kwp"], 10)
        self.assertEqual(compared["monthly_rmse_kwh_per_kwp"], 10)

        broken = pvgis_payload()
        del broken["outputs"]["totals"]["fixed"]["E_y"]
        with tempfile.TemporaryDirectory() as folder, patch(
                "solarna.benchmark.urlopen",
                return_value=FakeResponse(broken)):
            with self.assertRaises(ValueError):
                load_pvgis_benchmark(Site(), System(), Path(folder))


if __name__ == "__main__":
    unittest.main()
