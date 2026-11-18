"""Multi-site validation workflow tests; provider access is mocked."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from solarna.engine import Site, System
from solarna import validation


def report_fixture(name):
    return {
        "weather_source": {"cache_hit": True},
        "best": {
            "tilt_deg": 32,
            "azimuth_deg": 181,
            "annual_ac_kwh": 8500,
            "specific_yield_kwh_per_kwp": 1888.888,
        },
        "site": {"name": name},
    }


def benchmark_fixture(yield_delta=-1.5):
    return {
        "status": "available",
        "pvgis_result": {
            "tilt_deg": 33,
            "azimuth_deg_true_north": 180,
            "annual_ac_kwh_per_kwp": 1920,
            "interannual_sd_kwh_per_kwp": 30,
            "interannual_sd_percent": 1.5625,
        },
        "comparison": {
            "solarna_tilt_deg": 32,
            "pvgis_tilt_deg": 33,
            "tilt_delta_deg": -1,
            "solarna_azimuth_deg_true_north": 181,
            "pvgis_azimuth_deg_true_north": 180,
            "azimuth_delta_deg": 1,
            "solarna_specific_yield_kwh_per_kwp": 1888.888,
            "pvgis_specific_yield_kwh_per_kwp": 1920,
            "specific_yield_delta_kwh_per_kwp": -31.112,
            "specific_yield_delta_percent_of_pvgis": yield_delta,
            "monthly_mae_kwh_per_kwp": 7,
            "monthly_rmse_kwh_per_kwp": 8,
        },
    }


class ValidationTests(unittest.TestCase):
    def test_sample_spans_six_governorate_capitals(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "examples" / "tunisia-validation-sample.csv"
        )
        sites = validation.read_sites(path)
        self.assertEqual(
            [key for key, _ in sites],
            ["bizerte", "tunis", "kairouan", "sfax", "gafsa", "tataouine"],
        )

    def test_summary_aggregates_signed_and_absolute_differences(self):
        results = [
            {"comparison": benchmark_fixture(-2)["comparison"]},
            {"comparison": benchmark_fixture(1)["comparison"]},
        ]
        summary = validation.build_summary(
            Path("sites.csv"), System(), 10, 1, results, [])
        aggregate = summary["aggregate"]
        self.assertEqual(summary["totals"]["succeeded"], 2)
        self.assertAlmostEqual(
            aggregate["mean_specific_yield_delta_percent_of_pvgis"], -0.5)
        self.assertAlmostEqual(
            aggregate[
                "mean_absolute_specific_yield_delta_percent_of_pvgis"], 1.5)
        self.assertEqual(
            aggregate[
                "maximum_absolute_specific_yield_delta_percent_of_pvgis"], 2)

    def test_paced_partial_failure_writes_reports_and_summary(self):
        sites = [
            ("sfax", Site(name="Sfax")),
            ("tunis", Site(36.8, 10.18, name="Tunis")),
            ("gafsa", Site(34.425, 8.784, name="Gafsa")),
        ]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reports = root / "reports"
            summary_path = root / "summary.json"
            reports_returned = [
                report_fixture("Sfax"),
                report_fixture("Gafsa"),
            ]
            with patch(
                    "solarna.validation.load_tmy",
                    side_effect=[
                        ("weather", {
                            "cache_hit": True,
                            "provider_metadata": {
                                "inputs": {"location": {"elevation": 3}}
                            },
                        }),
                        OSError("offline"),
                        ("weather", {
                            "cache_hit": False,
                            "provider_metadata": {
                                "inputs": {"location": {"elevation": 297}}
                            },
                        }),
                    ]), patch(
                        "solarna.validation.build_report",
                        side_effect=reports_returned), patch(
                            "solarna.validation.load_pvgis_benchmark",
                            return_value={"provider": True}), patch(
                                "solarna.validation.compare_with_report",
                                side_effect=[
                                    benchmark_fixture(-1.5),
                                    benchmark_fixture(0.5),
                                ]), patch(
                                    "solarna.validation.time.sleep") as sleep:
                failures, summary = validation.run_validation(
                    sites, Path("sites.csv"), reports, summary_path,
                    root / "cache", System(), pause_seconds=2,
                    provider_retries=0)

            self.assertEqual([item["id"] for item in failures], ["tunis"])
            self.assertEqual(sleep.call_count, 2)
            self.assertEqual(
                sorted(path.name for path in reports.glob("*.json")),
                ["site-gafsa.json", "site-sfax.json"],
            )
            self.assertEqual(summary["totals"], {
                "requested": 3,
                "succeeded": 2,
                "failed": 1,
            })
            saved = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["totals"], summary["totals"])
            self.assertAlmostEqual(
                saved["aggregate"][
                    "mean_absolute_specific_yield_delta_percent_of_pvgis"], 1)

    def test_invalid_pause_is_rejected_before_provider_access(self):
        with patch("solarna.validation.load_tmy") as fetch:
            with self.assertRaises(ValueError):
                validation.run_validation(
                    [("sfax", Site())], Path("sites.csv"), Path("reports"),
                    Path("summary.json"), Path("cache"), System(),
                    pause_seconds=0)
        fetch.assert_not_called()

    def test_transient_provider_failure_is_retried(self):
        operation = Mock(
            side_effect=[OSError("connection reset"), "ok"])
        with patch("solarna.validation.time.sleep") as sleep:
            result = validation._retry_provider_call(operation, 2, 1.5)
        self.assertEqual(result, "ok")
        self.assertEqual(operation.call_count, 2)
        sleep.assert_called_once_with(1.5)


if __name__ == "__main__":
    unittest.main()
