"""Interactive application tests; network and real optimization are mocked."""

import json
from pathlib import Path
import tempfile
from threading import Event, Thread
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from solarna.app import (
    JobCapacityError,
    SolarnaApplication,
    create_server,
    normalize_access_token,
    normalize_android_apk_path,
    normalize_ios_project_path,
    normalize_login_email,
    normalize_login_password,
    normalize_origin,
    normalize_supabase_publishable_key,
    normalize_supabase_url,
    parse_request,
    web_asset,
)


def valid_payload():
    return {
        "name": "Sfax test",
        "latitude": 34.7406,
        "longitude": 10.7603,
        "altitude_m": 0,
        "capacity_kw": 1,
        "dc_ac_ratio": 1.2,
        "albedo": 0.2,
        "other_dc_loss_percent": 3,
        "gamma_pdc_percent_per_c": -0.38,
        "inverter_efficiency_percent": 97,
        "temperature_model": "close_mount_glass_glass",
        "panel_model": "JinkoSolar JKM550M-72HL4-V",
        "inverter_model": "Sungrow SG4.0RS",
        "coarse_step": 10,
        "fine_step": 1,
        "timing_sensitivity": False,
        "period_analysis": "none",
        "pvgis_benchmark": False,
        "historical_range": False,
    }


def fake_report(*args, progress_callback=None, **kwargs):
    if progress_callback:
        progress_callback("corrected_timing", "coarse_search", 1, 2)
        progress_callback("corrected_timing", "coarse_search", 2, 2)
        progress_callback("corrected_timing", "fine_search", 1, 1)
        progress_callback("corrected_timing", "finalizing", 2, 2)
    return {
        "schema_version": 2,
        "site": {"name": "Sfax test"},
        "best": {"tilt_deg": 32, "azimuth_deg": 182, "annual_ac_kwh": 1861},
        "assumptions_and_limitations": [],
    }


class RequestValidationTests(unittest.TestCase):
    def test_queue_configuration_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for workers, pending in ((0, 4), (True, 4), (2, 1), (1, 0)):
                with self.subTest(workers=workers, pending=pending), \
                        self.assertRaises(ValueError):
                    SolarnaApplication(
                        root / "cache", root / "reports",
                        max_workers=workers, max_pending_jobs=pending)

    def test_access_token_validation(self):
        self.assertIsNone(normalize_access_token(None))
        self.assertIsNone(normalize_access_token(""))
        self.assertEqual(
            normalize_access_token("correct-horse-battery-staple"),
            "correct-horse-battery-staple")
        for value in ("short", " leading-space-token", "trailing-space-token "):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_access_token(value)

    def test_login_credential_validation(self):
        self.assertIsNone(normalize_login_email(None))
        self.assertEqual(
            normalize_login_email("Owner@SolarnaSystems.com"),
            "owner@solarnasystems.com")
        self.assertIsNone(normalize_login_password(None))
        self.assertEqual(
            normalize_login_password("correct-horse-battery-staple"),
            "correct-horse-battery-staple")
        for value in ("invalid", "user @example.com", "user@example"):
            with self.subTest(email=value), self.assertRaises(ValueError):
                normalize_login_email(value)
        for value in ("short", " leading-password", "trailing-password "):
            with self.subTest(password=value), self.assertRaises(ValueError):
                normalize_login_password(value)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(ValueError):
                SolarnaApplication(
                    root / "cache", root / "reports",
                    login_email="owner@example.com")

    def test_supabase_configuration_validation(self):
        url = "https://example.supabase.co"
        key = "sb_publishable_abcdefghijklmnopqrstuvwxyz"
        self.assertEqual(normalize_supabase_url(url + "/"), url)
        self.assertEqual(normalize_supabase_publishable_key(key), key)
        with self.assertRaises(ValueError):
            normalize_supabase_url("http://example.supabase.co")
        with self.assertRaises(ValueError):
            normalize_supabase_publishable_key("legacy-anon-key")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(ValueError):
                SolarnaApplication(
                    root / "cache", root / "reports",
                    supabase_url=url)

    def test_android_download_path_validation(self):
        self.assertIsNone(normalize_android_apk_path(None))
        self.assertEqual(
            normalize_android_apk_path("Solarna.apk").suffix, ".apk")
        with self.assertRaises(ValueError):
            normalize_android_apk_path("Solarna.zip")

    def test_ios_project_download_path_validation(self):
        self.assertIsNone(normalize_ios_project_path(None))
        self.assertEqual(
            normalize_ios_project_path("Solarna.zip").suffix, ".zip")
        with self.assertRaises(ValueError):
            normalize_ios_project_path("Solarna.ipa")

    def test_allowed_origin_validation(self):
        self.assertEqual(
            normalize_origin("https://solarna.example.com/"),
            "https://solarna.example.com")
        self.assertEqual(
            normalize_origin("capacitor://localhost"),
            "capacitor://localhost")
        for value in (
                "", "ftp://example.com", "https://user@example.com",
                "https://example.com/path", "https://example.com?x=1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_origin(value)

    def test_valid_request_builds_engine_configuration(self):
        request = parse_request(valid_payload())
        self.assertEqual(request.site.name, "Sfax test")
        self.assertEqual(request.site.latitude, 34.7406)
        self.assertAlmostEqual(request.system.other_dc_loss_fraction, 0.03)
        self.assertAlmostEqual(request.system.gamma_pdc_per_c, -0.0038)
        self.assertAlmostEqual(request.system.inverter_efficiency, 0.97)
        self.assertEqual(
            request.system.temperature_model, "close_mount_glass_glass")
        self.assertEqual(
            request.panel_model, "JinkoSolar JKM550M-72HL4-V")
        self.assertEqual(request.inverter_model, "Sungrow SG4.0RS")
        self.assertEqual(
            request.public()["panel_model"], "JinkoSolar JKM550M-72HL4-V")
        self.assertEqual(
            request.public()["inverter_model"], "Sungrow SG4.0RS")
        self.assertEqual(request.coarse_step, 10)
        self.assertFalse(request.timing_sensitivity)
        self.assertIsNone(request.period_analysis)
        self.assertFalse(request.pvgis_benchmark)
        self.assertFalse(request.historical_range)
        self.assertIsNone(request.existing_orientation)
        self.assertFalse(request.normalized_capacity)
        self.assertFalse(request.use_pvgis_elevation)
        self.assertIsNone(request.period_months)

        automatic = valid_payload()
        automatic["elevation_mode"] = "pvgis"
        automatic["altitude_m"] = None
        automatic["period_analysis"] = "custom"
        automatic["period_months"] = [11, 12, 1, 2, 3]
        request = parse_request(automatic)
        self.assertTrue(request.use_pvgis_elevation)
        self.assertEqual(request.period_analysis, "custom")
        self.assertEqual(request.period_months, (11, 12, 1, 2, 3))
        self.assertIsNone(request.public()["altitude_m"])
        self.assertEqual(request.public()["elevation_mode"], "pvgis")

        compared = valid_payload()
        compared["existing_tilt_deg"] = 20
        compared["existing_azimuth_deg"] = 180
        request = parse_request(compared)
        self.assertEqual(request.existing_orientation, (20.0, 180.0))
        self.assertEqual(request.public()["existing_tilt_deg"], 20.0)
        self.assertEqual(request.public()["existing_azimuth_deg"], 180.0)

        normalized = valid_payload()
        normalized["capacity_kw"] = 1
        normalized["normalized_capacity"] = True
        request = parse_request(normalized)
        self.assertTrue(request.normalized_capacity)
        self.assertTrue(request.public()["normalized_capacity"])
        self.assertEqual(request.system.dc_capacity_kw, 1)

        legacy = valid_payload()
        for key in (
                "gamma_pdc_percent_per_c",
                "inverter_efficiency_percent",
                "temperature_model"):
            legacy.pop(key)
        request = parse_request(legacy)
        self.assertEqual(request.system.gamma_pdc_per_c, -0.004)
        self.assertEqual(request.system.inverter_efficiency, 0.96)
        self.assertEqual(
            request.system.temperature_model, "open_rack_glass_glass")

        engineering = valid_payload()
        engineering["loss_model"] = "engineering"
        engineering["engineering_losses_percent"] = {
            "soiling": 2,
            "shading": 0,
            "mismatch": 1.5,
            "wiring": 1.5,
            "availability": 1,
            "quality": 1,
        }
        request = parse_request(engineering)
        self.assertEqual(
            request.public()["loss_model"], "engineering")
        self.assertEqual(
            request.public()["engineering_losses_percent"]["soiling"], 2)
        self.assertAlmostEqual(
            request.system.other_dc_loss_fraction,
            1 - 0.98 * 1 * 0.985 * 0.985 * 0.99 * 0.99)

    def test_invalid_payloads_are_rejected(self):
        changes = [
            ("latitude", 91),
            ("longitude", "10"),
            ("altitude_m", float("nan")),
            ("capacity_kw", 0),
            ("dc_ac_ratio", 4),
            ("albedo", -0.1),
            ("other_dc_loss_percent", 81),
            ("gamma_pdc_percent_per_c", -3),
            ("inverter_efficiency_percent", 75),
            ("temperature_model", "roof"),
            ("coarse_step", 7),
            ("fine_step", 0.25),
            ("timing_sensitivity", 1),
            ("period_analysis", "monsoon"),
            ("elevation_mode", "device"),
            ("pvgis_benchmark", 1),
            ("historical_range", 1),
            ("normalized_capacity", 1),
            ("name", ""),
        ]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                payload = valid_payload()
                payload[key] = value
                with self.assertRaises(ValueError):
                    parse_request(payload)
        with self.assertRaises(ValueError):
            parse_request([])
        for tilt, azimuth in (
                (20, None), (None, 180), (-1, 180), (91, 180),
                (20, -1), (20, 361), (True, 180)):
            with self.subTest(tilt=tilt, azimuth=azimuth), \
                    self.assertRaises(ValueError):
                payload = valid_payload()
                payload["existing_tilt_deg"] = tilt
                payload["existing_azimuth_deg"] = azimuth
                parse_request(payload)
        payload = valid_payload()
        payload["normalized_capacity"] = True
        payload["capacity_kw"] = 4.5
        with self.assertRaises(ValueError):
            parse_request(payload)
        payload = valid_payload()
        payload["normalized_capacity"] = True
        payload["dc_ac_ratio"] = 1.1
        with self.assertRaises(ValueError):
            parse_request(payload)
        payload = valid_payload()
        payload["period_analysis"] = "custom"
        payload["period_months"] = []
        with self.assertRaises(ValueError):
            parse_request(payload)
        payload = valid_payload()
        payload["loss_model"] = "engineering"
        payload["engineering_losses_percent"] = {"soiling": 2}
        with self.assertRaises(ValueError):
            parse_request(payload)
        payload = valid_payload()
        payload["loss_model"] = "unsupported"
        with self.assertRaises(ValueError):
            parse_request(payload)
        for key, value in (
                ("panel_model", ""),
                ("panel_model", " JinkoSolar JKM550M-72HL4-V"),
                ("panel_model", "x" * 161),
                ("inverter_model", True)):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                payload = valid_payload()
                payload[key] = value
                parse_request(payload)


class JobTests(unittest.TestCase):
    def test_pvgis_elevation_is_used_for_the_energy_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            application = SolarnaApplication(
                root / "cache", root / "reports")
            payload = valid_payload()
            payload["elevation_mode"] = "pvgis"
            payload["altitude_m"] = None
            provenance = {
                "cache_hit": True,
                "provider_metadata": {
                    "inputs": {"location": {"elevation": 247.0}}
                },
            }
            try:
                with patch(
                        "solarna.app.load_tmy",
                        return_value=("weather", provenance)), patch(
                        "solarna.app.build_report",
                        side_effect=fake_report) as build:
                    submitted = application.submit(payload)
                    final = application.wait(submitted["id"], timeout=5)
                self.assertEqual(final["status"], "completed")
                self.assertEqual(build.call_args.args[2].altitude_m, 247.0)
                report = application.report(submitted["id"])
                self.assertEqual(report["site_elevation"], {
                    "altitude_m": 247.0,
                    "source": "PVGIS terrain model",
                })
            finally:
                application.close()

    def test_queue_rejects_unbounded_work(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            release = Event()
            application = SolarnaApplication(
                root / "cache", root / "reports", max_pending_jobs=1)
            application._execute = lambda job_id, request: release.wait(5)
            try:
                application.submit(valid_payload())
                self.assertEqual(application.queue_status(), {
                    "active_jobs": 1,
                    "max_pending_jobs": 1,
                    "accepting_jobs": False,
                })
                with self.assertRaises(JobCapacityError):
                    application.submit(valid_payload())
            finally:
                release.set()
                application.close()

    def test_successful_job_reports_progress_and_persists_atomically(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            application = SolarnaApplication(root / "cache", root / "reports")
            try:
                with patch("solarna.app.load_tmy",
                           return_value=("weather", {"cache_hit": True})), \
                        patch("solarna.app.build_report", side_effect=fake_report):
                    submitted = application.submit(valid_payload())
                    final = application.wait(submitted["id"], timeout=5)
                self.assertEqual(final["status"], "completed")
                self.assertEqual(final["progress"], 1)
                self.assertIn("job-", Path(final["report_path"]).name)
                report = application.report(submitted["id"])
                self.assertEqual(report["best"]["tilt_deg"], 32)
                saved = json.loads(Path(final["report_path"]).read_text(encoding="utf-8"))
                self.assertEqual(saved["application_request"]["coarse_step"], 10)
                self.assertFalse(
                    saved["application_request"]["normalized_capacity"])
            finally:
                application.close()

    def test_failed_job_is_inspectable_and_has_no_report(self):
        with tempfile.TemporaryDirectory() as folder:
            application = SolarnaApplication(Path(folder) / "cache", Path(folder) / "reports")
            try:
                with patch("solarna.app.load_tmy", side_effect=OSError("offline")):
                    submitted = application.submit(valid_payload())
                    final = application.wait(submitted["id"], timeout=5)
                self.assertEqual(final["status"], "failed")
                self.assertIn("offline", final["error"])
                with self.assertRaises(RuntimeError):
                    application.report(submitted["id"])
            finally:
                application.close()

    def test_normalized_job_records_capacity_basis(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            application = SolarnaApplication(root / "cache", root / "reports")
            payload = valid_payload()
            payload["normalized_capacity"] = True
            try:
                with patch(
                        "solarna.app.load_tmy",
                        return_value=("weather", {"cache_hit": True})), patch(
                        "solarna.app.build_report", side_effect=fake_report):
                    submitted = application.submit(payload)
                    final = application.wait(submitted["id"], timeout=5)
                self.assertEqual(final["status"], "completed")
                report = application.report(submitted["id"])
                self.assertTrue(
                    report["application_request"]["normalized_capacity"])
                self.assertIn(
                    "total installation energy is not estimated",
                    report["assumptions_and_limitations"][0])
            finally:
                application.close()

    def test_optional_benchmark_is_attached_without_losing_core_result(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            application = SolarnaApplication(root / "cache", root / "reports")
            payload = valid_payload()
            payload["pvgis_benchmark"] = True
            try:
                with patch(
                        "solarna.app.load_tmy",
                        return_value=("weather", {"cache_hit": True})), patch(
                        "solarna.app.build_report",
                        side_effect=fake_report), patch(
                        "solarna.app.load_pvgis_benchmark",
                        return_value={"status": "available"}), patch(
                        "solarna.app.compare_with_report",
                        side_effect=lambda report, benchmark: {
                            "status": benchmark["status"],
                        }):
                    submitted = application.submit(payload)
                    final = application.wait(submitted["id"], timeout=5)
                self.assertEqual(final["status"], "completed")
                report = application.report(submitted["id"])
                self.assertEqual(
                    report["pvgis_benchmark"]["status"], "available")

                with patch(
                        "solarna.app.load_tmy",
                        return_value=("weather", {"cache_hit": True})), patch(
                        "solarna.app.build_report",
                        side_effect=fake_report), patch(
                        "solarna.app.load_pvgis_benchmark",
                        side_effect=OSError("PVGIS unavailable")):
                    submitted = application.submit(payload)
                    final = application.wait(submitted["id"], timeout=5)
                self.assertEqual(final["status"], "completed")
                report = application.report(submitted["id"])
                self.assertEqual(
                    report["pvgis_benchmark"]["status"], "unavailable")
                self.assertIn(
                    "PVGIS unavailable", report["pvgis_benchmark"]["error"])
            finally:
                application.close()

    def test_optional_historical_range_is_attached_without_losing_core_result(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            application = SolarnaApplication(root / "cache", root / "reports")
            payload = valid_payload()
            payload["historical_range"] = True
            try:
                with patch(
                        "solarna.app.load_tmy",
                        return_value=("weather", {"cache_hit": True})), patch(
                        "solarna.app.build_report",
                        side_effect=fake_report), patch(
                        "solarna.app.load_hourly_history",
                        return_value=(
                            "history",
                            {"cache_hit": True},
                        )), patch(
                        "solarna.app.build_historical_range",
                        return_value={"status": "available"}):
                    submitted = application.submit(payload)
                    final = application.wait(submitted["id"], timeout=5)
                self.assertEqual(final["status"], "completed")
                report = application.report(submitted["id"])
                self.assertEqual(
                    report["historical_range"]["status"], "available")
                self.assertTrue(
                    report["application_request"]["historical_range"])

                with patch(
                        "solarna.app.load_tmy",
                        return_value=("weather", {"cache_hit": True})), patch(
                        "solarna.app.build_report",
                        side_effect=fake_report), patch(
                        "solarna.app.load_hourly_history",
                        side_effect=OSError("history unavailable")):
                    submitted = application.submit(payload)
                    final = application.wait(submitted["id"], timeout=5)
                self.assertEqual(final["status"], "completed")
                report = application.report(submitted["id"])
                self.assertEqual(
                    report["historical_range"]["status"], "unavailable")
                self.assertIn(
                    "history unavailable",
                    report["historical_range"]["error"])
            finally:
                application.close()

    def test_saved_report_history_is_validated_and_filename_scoped(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reports = root / "reports"
            reports.mkdir()
            name = f"job-{'a' * 32}.json"
            report = {
                "generated_at_utc": "2026-09-17T12:00:00+00:00",
                "site": {
                    "name": "Sfax saved",
                    "latitude": 34.74056,
                    "longitude": 10.76028,
                },
                "system": {"dc_capacity_kw": 1},
                "best": {
                    "tilt_deg": 32,
                    "azimuth_deg": 182,
                    "annual_ac_kwh": 1861,
                },
            }
            (reports / name).write_text(json.dumps(report), encoding="utf-8")
            (reports / f"job-{'b' * 32}.json").write_text(
                "not json", encoding="utf-8")
            (reports / "notes.json").write_text("{}", encoding="utf-8")
            application = SolarnaApplication(root / "cache", reports)
            try:
                with patch("solarna.app.validate_report"):
                    summaries = application.list_reports()
                    loaded = application.saved_report(name)
                self.assertEqual(len(summaries), 1)
                self.assertEqual(summaries[0]["name"], name)
                self.assertEqual(summaries[0]["site_name"], "Sfax saved")
                self.assertEqual(loaded["best"]["tilt_deg"], 32)
                for unsafe in ("notes.json", "../notes.json", "job-a.json"):
                    with self.subTest(unsafe=unsafe), self.assertRaises(KeyError):
                        application.saved_report(unsafe)
            finally:
                application.close()


class AssetAndHTTPTests(unittest.TestCase):
    def test_installable_shell_assets_are_packaged(self):
        page = web_asset("index.html").decode()
        login = web_asset("login.html").decode()
        reset = web_asset("reset-password.html").decode()
        privacy = web_asset("privacy.html").decode()
        script = web_asset("app.js").decode()
        login_script = web_asset("login.js").decode()
        supabase_client = web_asset("supabase-client.js").decode()
        system_config = web_asset("system-config.js").decode()
        cloud_storage = web_asset("cloud-storage.js").decode()
        i18n = web_asset("i18n.js").decode()
        worker = web_asset("service-worker.js").decode()
        manifest = json.loads(web_asset("manifest.webmanifest"))
        self.assertIn('name="viewport"', page)
        self.assertIn('rel="manifest"', page)
        self.assertIn('src="/config.js?v=44"', page)
        self.assertIn('src="/i18n.js?v=44"', page)
        self.assertIn('src="/supabase-client.js?v=44"', page)
        self.assertIn('src="/system-config.js?v=44"', page)
        self.assertIn('src="/result-summary.js?v=44"', page)
        self.assertIn('src="/install-support.js?v=44"', page)
        self.assertIn('src="/cloud-storage.js?v=44"', page)
        self.assertIn('src="/app.js?v=44"', page)
        self.assertIn('src="/solarna-mark.svg?v=44"', page)
        self.assertIn("Solarna Systems", page)
        self.assertNotIn('id="native-server-panel"', page)
        self.assertIn('id="login-email"', login)
        self.assertIn('id="login-password"', login)
        self.assertIn('id="forgot-password-button"', login)
        self.assertIn('id="reset-form"', reset)
        self.assertNotIn('id="access-code"', page)
        self.assertIn('id="existing-orientation-enabled"', page)
        self.assertIn('id="existing-orientation-summary"', page)
        self.assertIn('id="android-download-link"', page)
        self.assertNotIn('id="ios-download-link"', page)
        self.assertIn('<button id="connection-status"', page)
        self.assertIn('id="pvgis-benchmark"', page)
        self.assertIn('id="historical-range"', page)
        self.assertIn('id="analysis-profile"', page)
        self.assertIn('id="loss-preset"', page)
        self.assertIn('id="loss-mode"', page)
        self.assertIn('id="engineering-loss-fields"', page)
        self.assertIn('id="loss-chart"', page)
        self.assertIn('id="performance-ratio"', page)
        self.assertIn('id="temperature-model"', page)
        self.assertIn('id="inverter-model"', page)
        self.assertIn('id="panel-model"', page)
        self.assertIn('id="equipment-catalog"', page)
        self.assertIn('id="panel-spec-card"', page)
        self.assertIn('id="inverter-spec-card"', page)
        self.assertIn('id="system-size-mode"', page)
        self.assertIn('value="normalized"', page)
        self.assertIn('id="panel-count"', page)
        self.assertIn('id="panel-power"', page)
        self.assertIn('id="inverter-ac-rating"', page)
        self.assertIn('id="annual-energy-label"', page)
        self.assertIn('id="period-analysis"', page)
        self.assertIn('id="custom-months-field"', page)
        self.assertIn('id="elevation-mode"', page)
        self.assertIn('id="practical-orientation"', page)
        self.assertIn('id="practical-range"', page)
        self.assertIn('id="model-agreement"', page)
        self.assertIn('id="accuracy-summary"', page)
        self.assertIn('id="planning-range"', page)
        self.assertIn('id="mounting-accuracy-note"', page)
        self.assertIn('id="improvement-suggestions"', page)
        self.assertIn('id="tunisia-site-comparison"', page)
        self.assertIn("Tunisia research comparison", page)
        self.assertIn("Energy Reports 2018", page)
        self.assertIn("Applied Physics A 2018", page)
        self.assertIn("Ben Slama 2009", page)
        self.assertIn('id="saved-report-select"', page)
        self.assertIn('id="project-storage-status"', page)
        self.assertIn('id="production-import-button"', page)
        self.assertIn('id="production-summary"', page)
        self.assertIn('id="production-chart"', page)
        self.assertIn('id="production-table"', page)
        self.assertIn('id="csv-button"', page)
        self.assertIn('id="print-button"', page)
        self.assertIn('id="share-button"', page)
        self.assertIn('id="ios-install-dialog"', page)
        self.assertIn("Install on iPhone", page)
        self.assertIn("Tap Add to Home Screen, then Add.", page)
        self.assertIn('href="/privacy.html"', page)
        self.assertIn("Solarna PV privacy notice.", privacy)
        self.assertIn("European Commission Joint Research", privacy)
        self.assertIn("no advertising, cross-app tracking", privacy)
        self.assertIn('value="ariana"', page)
        self.assertIn('value="tataouine"', page)
        self.assertIn('value="34.74056"', page)
        self.assertIn("Plan fixed solar systems with confidence.", page)
        self.assertIn("Sungrow SG4.0RS", page)
        self.assertIn("Panel capacity (DC)", page)
        self.assertIn("Inverter output limit (AC)", page)
        self.assertIn("Ventilated rails · glass/backsheet", page)
        self.assertIn("Choose by airflow behind the panels.", page)
        self.assertNotIn("Enter panel count and panel power.", page)
        self.assertNotIn("Typical run:", page)
        self.assertNotIn("Tunisia research evidence", page)
        self.assertNotIn("<script>", page)
        self.assertIn("/api/jobs", script)
        self.assertIn("solarna:api-base", script)
        self.assertIn("solarna:session-token", script)
        self.assertNotIn("solarna:access-code", script)
        self.assertIn("signInWithPassword", login_script)
        self.assertIn("resetPasswordForEmail", login_script)
        self.assertIn("createClient", supabase_client)
        self.assertIn("parseProductionCsv", cloud_storage)
        self.assertIn("compareProduction", cloud_storage)
        self.assertNotIn("service_role", cloud_storage)
        self.assertIn('SUPPORTED = Object.freeze(["en", "fr", "ar"])', i18n)
        self.assertIn("document.documentElement.dir", i18n)
        self.assertIn("Français", i18n)
        self.assertIn("العربية", i18n)
        self.assertNotIn("service_role", supabase_client)
        self.assertIn("android_download_url", script)
        self.assertIn("!iosInstallAvailable", script)
        self.assertNotIn('byId("ios-download-link")', script)
        self.assertIn('t("mobile_https_error")', script)
        self.assertIn('t("panel_limit"', script)
        self.assertIn('t("sizing_summary"', script)
        self.assertIn("existing_tilt_deg", script)
        self.assertIn("normalized_capacity", script)
        self.assertIn("historical_range", script)
        self.assertIn("period_months", script)
        self.assertIn("elevation_mode", script)
        self.assertIn('value="spring"', page)
        self.assertIn('value="autumn"', page)
        self.assertIn('value="custom"', page)
        for month in range(1, 13):
            self.assertIn(f'id="period-month-{month}"', page)
        self.assertIn('t("historical_note")', script)
        self.assertIn('t("accuracy_site"', script)
        self.assertIn('t("planning_basic")', script)
        self.assertIn('t("daily_varies")', script)
        self.assertIn("average_daily_ac_energy", script)
        self.assertIn("engineering_losses_percent", script)
        self.assertIn("renderLossDiagram", script)
        self.assertIn('id="daily-energy"', page)
        self.assertNotIn("30° south retains", script)
        self.assertNotIn("Gain vs 30° south", page)
        self.assertIn('t("mounting_limited")', script)
        self.assertIn("applyAnalysisProfile", script)
        self.assertIn("applyLossPreset", script)
        self.assertIn('t("normalized_summary")', script)
        self.assertIn('t("current_summary"', script)
        self.assertRegex(
            page, r'id="existing-tilt" type="number"\s+placeholder="e\.g\. 30"')
        self.assertRegex(
            page, r'id="existing-azimuth" type="number"\s+placeholder="e\.g\. 180"')
        self.assertIn("navigator.serviceWorker", script)
        self.assertIn("shouldOfferIosInstall", script)
        self.assertIn('model: "SG4.0RS"', system_config)
        self.assertIn('model: "SUN2000-4KTL-L1"', system_config)
        self.assertIn('model: "GW4.2K-DNS-G40"', system_config)
        self.assertIn('modelForPower: power => `JKM${power}M-72HL4-V`',
                      system_config)
        self.assertIn('modelForPower: power => `LR5-72HTH-${power}M`',
                      system_config)
        self.assertIn('modelForPower: power => `JAM72S30-${power}/MR`',
                      system_config)
        self.assertIn('modelForPower: power => `TSM-DEG19C.20 ${power}W`',
                      system_config)
        self.assertIn('modelForPower: power => `CS6W-${power}MS`',
                      system_config)
        self.assertIn('modelForPower: power => `RSM110-8-${power}M`',
                      system_config)
        self.assertIn('model: "SG6.0RS-L2"', system_config)
        self.assertIn('model: "MIN 4200TL-X"', system_config)
        self.assertIn('model: "S6-GR1P6K-S"', system_config)
        self.assertIn('model: "SUN-4K-G04P1-EU-AM1"', system_config)
        self.assertIn('model: "Sunny Boy 5.0"', system_config)
        self.assertIn('model: "Primo GEN24 6.0 Plus"', system_config)
        self.assertIn("Technical source", page)
        self.assertIn("PANEL_PRESETS", system_config)
        self.assertIn("efficiencyPercent: 97.2", system_config)
        self.assertIn("maxEfficiencyPercent: 97.9", system_config)
        self.assertIn("recommendedMaxPvInputKw: 7.2", system_config)
        self.assertIn("NORMALIZED_CAPACITY_KW", system_config)
        self.assertIn("NORMALIZED_DC_AC_RATIO", system_config)
        self.assertIn("caches.open", worker)
        self.assertIn("systemCapacityKw", system_config)
        self.assertIn("solarna-shell-v44", worker)
        self.assertIn("/i18n.js?v=44", worker)
        self.assertIn("/install-support.js?v=44", worker)
        self.assertIn("/cloud-storage.js?v=44", worker)
        self.assertIn('"/login.html"', worker)
        self.assertIn('"/reset-password.html"', worker)
        self.assertIn('"/privacy.html"', worker)
        self.assertIn('url.pathname.startsWith("/downloads/")', worker)
        self.assertIn('event.request.mode === "navigate"', worker)
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual({icon["sizes"] for icon in manifest["icons"]},
                         {"192x192", "512x512"})

    def test_http_health_static_headers_and_bad_request(self):
        with tempfile.TemporaryDirectory() as folder:
            application = SolarnaApplication(Path(folder) / "cache", Path(folder) / "reports")
            server = create_server(application, "127.0.0.1", 0)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with urlopen(base + "/api/health", timeout=5) as response:
                    health = json.load(response)
                    self.assertEqual(health["status"], "ok")
                    self.assertEqual(health["version"], "0.5.0")
                    self.assertFalse(health["authentication_required"])
                    self.assertEqual(health["authentication_mode"], "none")
                    self.assertIsNone(health["supabase_url"])
                    self.assertIsNone(health["supabase_publishable_key"])
                    self.assertEqual(health["queue"], {
                        "active_jobs": 0,
                        "max_pending_jobs": 4,
                        "accepting_jobs": True,
                    })
                    self.assertIsNone(health["android_download_url"])
                    self.assertIsNone(health["ios_project_download_url"])
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertIn("default-src 'self'",
                                  response.headers["Content-Security-Policy"])
                with urlopen(base + "/", timeout=5) as response:
                    self.assertIn(b"PV orientation optimizer", response.read())
                    self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                    self.assertEqual(response.headers["Cache-Control"], "no-cache")
                with urlopen(base + "/privacy.html", timeout=5) as response:
                    self.assertIn(b"Solarna PV privacy notice", response.read())
                    self.assertEqual(response.headers["Cache-Control"], "no-cache")
                with urlopen(base + "/login.html", timeout=5) as response:
                    self.assertIn(b"Sign in", response.read())
                with urlopen(base + "/reset-password.html", timeout=5) as response:
                    self.assertIn(b"Set new password", response.read())
                with urlopen(base + "/favicon.ico", timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["Content-Type"], "image/png")
                with urlopen(base + "/api/reports", timeout=5) as response:
                    self.assertEqual(json.load(response), {"reports": []})
                with urlopen(base + "/config.js", timeout=5) as response:
                    self.assertIn(b"nativeShell", response.read())
                with urlopen(base + "/i18n.js", timeout=5) as response:
                    self.assertIn(b'SUPPORTED = Object.freeze(["en", "fr", "ar"])',
                                  response.read())
                    self.assertEqual(
                        response.headers["Content-Type"],
                        "text/javascript; charset=utf-8")
                with urlopen(base + "/system-config.js", timeout=5) as response:
                    self.assertIn(b"panelCapacityKw", response.read())
                with urlopen(base + "/result-summary.js", timeout=5) as response:
                    self.assertIn(b"summarizeNearOptimal", response.read())
                with urlopen(base + "/solarna-mark.svg", timeout=5) as response:
                    self.assertIn(b"Solarna Systems solar engineering mark", response.read())
                    self.assertEqual(response.headers["Content-Type"], "image/svg+xml")
                request = Request(
                    base + "/api/jobs", data=b"{}", method="POST",
                    headers={"Content-Type": "application/json"})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(request, timeout=5)
                self.assertEqual(caught.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()
                application.close()
                thread.join(timeout=5)

    def test_http_queue_limit_returns_retryable_status(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            release = Event()
            application = SolarnaApplication(
                root / "cache", root / "reports", max_pending_jobs=1)
            application._execute = lambda job_id, request: release.wait(5)
            server = create_server(application, "127.0.0.1", 0)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            body = json.dumps(valid_payload()).encode()
            try:
                request = Request(
                    base + "/api/jobs", data=body, method="POST",
                    headers={"Content-Type": "application/json"})
                with urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 202)

                request = Request(
                    base + "/api/jobs", data=body, method="POST",
                    headers={"Content-Type": "application/json"})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(request, timeout=5)
                self.assertEqual(caught.exception.code, 429)
                self.assertEqual(caught.exception.headers["Retry-After"], "5")
                self.assertIn(
                    "queue is full",
                    json.load(caught.exception)["error"].lower())
            finally:
                release.set()
                server.shutdown()
                server.server_close()
                application.close()
                thread.join(timeout=5)

    def test_android_installer_download(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            apk = root / "Solarna-test.apk"
            apk.write_bytes(b"test-apk-content")
            application = SolarnaApplication(
                root / "cache", root / "reports", android_apk_path=apk)
            server = create_server(application, "127.0.0.1", 0)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with urlopen(base + "/api/health", timeout=5) as response:
                    self.assertEqual(
                        json.load(response)["android_download_url"],
                        "/downloads/solarna-android.apk")
                with urlopen(
                        base + "/downloads/solarna-android.apk",
                        timeout=5) as response:
                    self.assertEqual(response.read(), b"test-apk-content")
                    self.assertEqual(
                        response.headers["Content-Type"],
                        "application/vnd.android.package-archive")
                    self.assertEqual(
                        response.headers["Content-Disposition"],
                        'attachment; filename="Solarna-android.apk"')
                    self.assertEqual(
                        response.headers["Cache-Control"], "no-store")
            finally:
                server.shutdown()
                server.server_close()
                application.close()
                thread.join(timeout=5)

    def test_ios_project_download(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ios_project = root / "Solarna-test.zip"
            ios_project.write_bytes(b"test-ios-project-content")
            application = SolarnaApplication(
                root / "cache", root / "reports",
                ios_project_path=ios_project)
            server = create_server(application, "127.0.0.1", 0)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with urlopen(base + "/api/health", timeout=5) as response:
                    self.assertEqual(
                        json.load(response)["ios_project_download_url"],
                        "/downloads/solarna-ios-project.zip")
                with urlopen(
                        base + "/downloads/solarna-ios-project.zip",
                        timeout=5) as response:
                    self.assertEqual(
                        response.read(), b"test-ios-project-content")
                    self.assertEqual(
                        response.headers["Content-Type"], "application/zip")
                    self.assertEqual(
                        response.headers["Content-Disposition"],
                        'attachment; filename="Solarna-iOS-project.zip"')
                    self.assertEqual(
                        response.headers["Cache-Control"], "no-store")
            finally:
                server.shutdown()
                server.server_close()
                application.close()
                thread.join(timeout=5)

    def test_login_protects_reports_and_jobs(self):
        with tempfile.TemporaryDirectory() as folder:
            email = "owner@solarnasystems.com"
            password = "correct-horse-battery-staple"
            application = SolarnaApplication(
                Path(folder) / "cache",
                Path(folder) / "reports",
                login_email=email,
                login_password=password)
            server = create_server(application, "127.0.0.1", 0)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with urlopen(base + "/api/health", timeout=5) as response:
                    health = json.load(response)
                    self.assertTrue(health["authentication_required"])
                    self.assertEqual(health["authentication_mode"], "login")

                with self.assertRaises(HTTPError) as caught:
                    urlopen(base + "/api/reports", timeout=5)
                self.assertEqual(caught.exception.code, 401)
                self.assertEqual(
                    json.load(caught.exception)["error"], "Login required")

                failed_login = Request(
                    base + "/api/login",
                    data=json.dumps({
                        "email": email,
                        "password": "wrong-password-value",
                    }).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json"})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(failed_login, timeout=5)
                self.assertEqual(caught.exception.code, 401)

                login = Request(
                    base + "/api/login",
                    data=json.dumps({
                        "email": email.upper(),
                        "password": password,
                    }).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json"})
                with urlopen(login, timeout=5) as response:
                    session = json.load(response)
                self.assertEqual(session["token_type"], "Bearer")
                self.assertEqual(session["expires_in_seconds"], 43200)
                token = session["token"]

                authorized = {"Authorization": f"Bearer {token}"}
                with urlopen(
                        Request(base + "/api/reports", headers=authorized),
                        timeout=5) as response:
                    self.assertEqual(json.load(response), {"reports": []})

                logout = Request(
                    base + "/api/logout",
                    data=b"{}",
                    method="POST",
                    headers={
                        **authorized,
                        "Content-Type": "application/json",
                    })
                with urlopen(logout, timeout=5) as response:
                    self.assertEqual(
                        json.load(response), {"status": "logged_out"})

                with self.assertRaises(HTTPError) as caught:
                    urlopen(
                        Request(base + "/api/reports", headers=authorized),
                        timeout=5)
                self.assertEqual(caught.exception.code, 401)
            finally:
                server.shutdown()
                server.server_close()
                application.close()
                thread.join(timeout=5)

    def test_legacy_access_token_remains_supported(self):
        with tempfile.TemporaryDirectory() as folder:
            token = "test-access-token-123"
            application = SolarnaApplication(
                Path(folder) / "cache",
                Path(folder) / "reports",
                access_token=token)
            server = create_server(application, "127.0.0.1", 0)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with urlopen(base + "/api/health", timeout=5) as response:
                    health = json.load(response)
                    self.assertTrue(health["authentication_required"])
                    self.assertEqual(health["authentication_mode"], "token")

                for authorization in (None, "Bearer wrong-access-token"):
                    headers = (
                        {"Authorization": authorization}
                        if authorization else {})
                    request = Request(base + "/api/reports", headers=headers)
                    with self.subTest(authorization=authorization), \
                            self.assertRaises(HTTPError) as caught:
                        urlopen(request, timeout=5)
                    self.assertEqual(caught.exception.code, 401)
                    self.assertEqual(
                        caught.exception.headers["WWW-Authenticate"],
                        'Bearer realm="Solarna"')

                request = Request(
                    base + "/api/reports",
                    headers={"Authorization": f"Bearer {token}"})
                with urlopen(request, timeout=5) as response:
                    self.assertEqual(json.load(response), {"reports": []})

                request = Request(
                    base + "/api/jobs",
                    data=json.dumps(valid_payload()).encode(),
                    method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer wrong-access-token",
                    })
                with self.assertRaises(HTTPError) as caught:
                    urlopen(request, timeout=5)
                self.assertEqual(caught.exception.code, 401)
            finally:
                server.shutdown()
                server.server_close()
                application.close()
                thread.join(timeout=5)

    def test_supabase_login_protects_api_and_caches_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            url = "https://example.supabase.co"
            key = "sb_publishable_abcdefghijklmnopqrstuvwxyz"
            application = SolarnaApplication(
                Path(folder) / "cache",
                Path(folder) / "reports",
                supabase_url=url,
                supabase_publishable_key=key,
                supabase_authorized_emails=("owner@example.com",))
            server = create_server(application, "127.0.0.1", 0)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            auth_response = MagicMock()
            auth_response.__enter__.return_value = auth_response
            auth_response.read.return_value = (
                b'{"id":"user-123","email":"owner@example.com"}')
            try:
                with urlopen(base + "/api/health", timeout=5) as response:
                    health = json.load(response)
                self.assertTrue(health["authentication_required"])
                self.assertEqual(health["authentication_mode"], "supabase")
                self.assertEqual(health["supabase_url"], url)
                self.assertEqual(health["supabase_publishable_key"], key)

                with self.assertRaises(HTTPError) as caught:
                    urlopen(base + "/api/reports", timeout=5)
                self.assertEqual(caught.exception.code, 401)

                token = "header.payload.signature-that-is-long-enough"
                headers = {"Authorization": f"Bearer {token}"}
                with patch(
                        "solarna.app.urlopen",
                        return_value=auth_response) as auth_request:
                    for _ in range(2):
                        with urlopen(
                                Request(base + "/api/reports", headers=headers),
                                timeout=5) as response:
                            self.assertEqual(
                                json.load(response), {"reports": []})
                self.assertEqual(auth_request.call_count, 1)
                request = auth_request.call_args.args[0]
                self.assertEqual(request.full_url, url + "/auth/v1/user")
                self.assertEqual(request.get_header("Apikey"), key)
                self.assertEqual(
                    request.get_header("Authorization"), f"Bearer {token}")
            finally:
                server.shutdown()
                server.server_close()
                application.close()
                thread.join(timeout=5)

    def test_mobile_origin_preflight_and_response_headers(self):
        with tempfile.TemporaryDirectory() as folder:
            origin = "capacitor://localhost"
            application = SolarnaApplication(
                Path(folder) / "cache",
                Path(folder) / "reports",
                allowed_origins=(origin,))
            server = create_server(application, "127.0.0.1", 0)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                request = Request(
                    base + "/api/health", method="OPTIONS",
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "GET",
                    })
                with urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 204)
                    self.assertEqual(
                        response.headers["Access-Control-Allow-Origin"], origin)
                    self.assertIn(
                        "Authorization",
                        response.headers["Access-Control-Allow-Headers"])

                request = Request(
                    base + "/api/health", headers={"Origin": origin})
                with urlopen(request, timeout=5) as response:
                    self.assertEqual(json.load(response)["status"], "ok")
                    self.assertEqual(
                        response.headers["Access-Control-Allow-Origin"], origin)

                rejected = Request(
                    base + "/api/health", method="OPTIONS",
                    headers={"Origin": "https://untrusted.example"})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(rejected, timeout=5)
                self.assertEqual(caught.exception.code, 403)
            finally:
                server.shutdown()
                server.server_close()
                application.close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
