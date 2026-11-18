"""Offline workflow tests; no field-validation claim."""

from copy import deepcopy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

import pandas as pd

from solarna import batch, dashboard, reporting
from solarna.__main__ import main as single_main
from solarna.engine import EnergyModel, Site, System, optimize
from solarna.weather import irradiance_offset_hours, load_tmy
from test_engine import synthetic_weather


def provenance(offset=0.1626):
    return {'provider_metadata': {'inputs': {'location': {'irradiance_time_offset': offset}}},
            'source': 'SYNTHETIC TEST FIXTURE, NOT PVGIS production weather'}


def analytic_optimize(model, coarse_step=30, fine_step=1, **kwargs):
    def energy(tilt, azimuth):
        target = 180 + 20 * model.irradiance_time_offset_hours
        distance = (azimuth - target + 180) % 360 - 180
        return 2000 + model.irradiance_time_offset_hours - .1 * (tilt - 30) ** 2 - .01 * distance ** 2
    def simulate(tilt, azimuth):
        return pd.DataFrame({'ac_w': energy(tilt, azimuth) * 1000 / 8760,
                             'poa_w_m2': 250.0}, index=model.weather.index)
    with patch.object(model, 'energy_kwh', side_effect=energy), patch.object(model, 'simulate', side_effect=simulate):
        return optimize(model, coarse_step, fine_step)


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.weather = synthetic_weather(8760, '1990-01-01')

    def test_metadata_missing_invalid_and_zero(self):
        for value in (True, '0.5', None, float('nan'), float('inf'), -1, 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                irradiance_offset_hours(provenance(value))
        with self.assertRaisesRegex(ValueError, 'missing'):
            irradiance_offset_hours({})
        self.assertEqual(irradiance_offset_hours(provenance(0)), 0)
        self.assertEqual(irradiance_offset_hours(provenance()), .1626)

    def test_offset_survives_raw_cache_without_double_application(self):
        original = self.weather.copy(deep=True)
        with tempfile.TemporaryDirectory() as folder:
            with patch('solarna.weather.pvlib.iotools.get_pvgis_tmy', return_value=(self.weather, provenance()['provider_metadata'])):
                first, meta = load_tmy(Site(), Path(folder))
            cached_bytes = next(Path(folder).glob('*.json')).read_bytes()
            with patch('solarna.weather.pvlib.iotools.get_pvgis_tmy', side_effect=AssertionError('network')):
                second, cached_meta = load_tmy(Site(), Path(folder))
            self.assertEqual(irradiance_offset_hours(meta), irradiance_offset_hours(cached_meta))
            self.assertEqual(cached_bytes, next(Path(folder).glob('*.json')).read_bytes())
            pd.testing.assert_index_equal(first.index, second.index)
            pd.testing.assert_index_equal(original.index, second.index)

    def test_report_wiring_grid_and_sensitivity(self):
        original = self.weather.copy(deep=True)
        def energy(model, tilt, azimuth, months=None):
            target = 180 + 20 * model.irradiance_time_offset_hours
            distance = (azimuth - target + 180) % 360 - 180
            return (
                2000 + model.irradiance_time_offset_hours
                - .1 * (tilt - 30) ** 2
                - .01 * distance ** 2
            )

        with patch(
                'solarna.reporting.optimize',
                side_effect=analytic_optimize) as search, patch.object(
                    EnergyModel, "energy_kwh", energy):
            report = reporting.build_report(self.weather, provenance(), Site(), System(), 30,
                                            timing_sensitivity=True)
        self.assertEqual(search.call_count, 2)
        self.assertEqual([call.args[0].irradiance_time_offset_hours for call in search.call_args_list], [.1626, 0])
        self.assertEqual(report['schema_version'], 2)
        grid = report['search']['coarse_grid']
        self.assertEqual(len(grid['annual_ac_kwh']), 4)
        self.assertEqual(len(grid['annual_ac_kwh'][0]), 12)
        self.assertAlmostEqual(grid['annual_ac_kwh'][1][6], 2000 + .1626 - .01 * (20 * .1626) ** 2)
        comparison = report['timing_sensitivity']
        old = comparison['zero_offset_best']
        expected = energy(
            EnergyModel(self.weather, Site(), System(), .1626),
            old['tilt_deg'], old['azimuth_deg'])
        self.assertAlmostEqual(comparison['corrected_model_at_zero_offset_optimum_kwh'], expected)
        self.assertEqual(comparison['best_energy_change_kwh'], report['best']['annual_ac_kwh'] - old['annual_ac_kwh'])
        practical = report["practical_recommendation"]
        self.assertEqual(practical["tilt_deg"] % 5, 0)
        self.assertEqual(practical["azimuth_deg"] % 5, 0)
        self.assertGreaterEqual(practical["loss_from_numerical_best_kwh"], 0)
        self.assertGreater(practical["retained_energy_percent"], 99)
        self.assertLessEqual(practical["retained_energy_percent"], 100)
        pd.testing.assert_frame_equal(self.weather, original)
        dashboard.validate_report(report)

    def test_existing_orientation_uses_same_model_and_is_reported(self):
        calls = []

        def search(model, coarse_step=30, fine_step=1, **kwargs):
            calls.append(kwargs)
            return analytic_optimize(model, coarse_step, fine_step)

        with patch("solarna.reporting.optimize", side_effect=search):
            report = reporting.build_report(
                self.weather, provenance(), Site(), System(), 30,
                existing_orientation=(20, 180))
        self.assertEqual(
            calls[0]["required_orientations"], ((20.0, 180.0),))
        existing = report["existing_orientation"]
        self.assertEqual(existing["tilt_deg"], 20)
        self.assertEqual(existing["azimuth_deg"], 180)
        self.assertAlmostEqual(
            existing["gain_of_best_kwh"],
            report["best"]["annual_ac_kwh"] - existing["annual_ac_kwh"])
        self.assertAlmostEqual(
            existing["specific_yield_kwh_per_kwp"],
            existing["annual_ac_kwh"] / report["system"]["dc_capacity_kw"])
        self.assertEqual(
            reporting.normalize_existing_orientation((20, 360)),
            (20.0, 0.0))
        for value in ((20,), (91, 180), (20, 361), (True, 180)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                reporting.normalize_existing_orientation(value)

    def test_single_cli_uses_timing_and_writes_versioned_report(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'sfax.json'
            with patch('solarna.__main__.load_tmy', return_value=(self.weather, provenance())), \
                    patch('solarna.reporting.optimize', side_effect=analytic_optimize):
                self.assertEqual(single_main(['--coarse-step', '30', '--timing-sensitivity', '--output', str(output)]), 0)
            result = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(result['timing']['irradiance_time_offset_hours'], .1626)
            self.assertIn('timing_sensitivity', result)
            before = output.read_bytes()
            with patch('solarna.__main__.load_tmy', return_value=(self.weather, {})):
                self.assertEqual(single_main(['--output', str(output)]), 1)
            self.assertEqual(before, output.read_bytes())

    def test_no_comparison_unless_requested_and_atomic_serialization(self):
        with patch('solarna.reporting.optimize', side_effect=analytic_optimize) as search:
            report = reporting.build_report(self.weather, provenance(0), Site(), System(), 30)
        self.assertEqual(search.call_count, 1)
        self.assertNotIn('timing_sensitivity', report)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'report.json'
            reporting.write_report(report, path)
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                reporting.write_report({'bad': float('nan')}, path)
            self.assertEqual(path.read_bytes(), before)

    def test_selected_period_analysis_keeps_annual_and_period_energy_distinct(self):
        monthly = {
            str(month): (100 if month in {11, 12, 1, 2, 3} else 50)
            for month in range(1, 13)
        }
        raw = {
            'best': {
                'tilt_deg': 55,
                'azimuth_deg': 180,
                'annual_ac_kwh': 600,
                'annual_poa_kwh_m2': 2100,
                'monthly_ac_kwh': monthly,
            },
            'baselines': {
                '30_degrees_south': {
                    'tilt_deg': 30,
                    'azimuth_deg': 180,
                    'annual_ac_kwh': 560,
                    'gain_of_best_percent': 100 * (600 / 560 - 1),
                },
                'latitude_tilt_equator_facing': {
                    'tilt_deg': 34.7406,
                    'azimuth_deg': 180,
                    'annual_ac_kwh': 570,
                    'gain_of_best_percent': 100 * (600 / 570 - 1),
                },
            },
            'search': {
                'coarse_step_deg': 30,
                'fine_step_deg': 1,
                'candidate_count': 50,
                'near_optimal_fraction': 0.01,
                'near_optimal_sampled_orientations': [{
                    'tilt_deg': 55,
                    'azimuth_deg': 180,
                    'annual_ac_kwh': 600,
                }],
                'coarse_grid': {
                    'tilt_deg': [0, 30],
                    'azimuth_deg': [0, 180],
                    'annual_ac_kwh': [[100, 200], [300, 600]],
                },
            },
        }
        annual = {
            'best': {
                'annual_ac_kwh': 1000,
                'monthly_ac_kwh': {
                    str(month): (
                        90 if month in {11, 12, 1, 2, 3} else 550 / 7)
                    for month in range(1, 13)
                },
            }
        }
        model = EnergyModel(self.weather, Site(), System())
        with patch('solarna.reporting.optimize', return_value=raw):
            period = reporting.build_period_analysis(
                model, annual, 'winter', 30, 1)
        self.assertEqual(period['months'], [11, 12, 1, 2, 3])
        self.assertEqual(period['best']['period_ac_kwh'], 600)
        self.assertEqual(
            period['best']['annual_ac_kwh_at_period_optimum'], 850)
        self.assertEqual(period['annual_optimum_during_period_kwh'], 450)
        self.assertAlmostEqual(
            period['gain_over_annual_optimum_during_period_percent'],
            100 * (600 / 450 - 1))
        self.assertEqual(period['annual_energy_tradeoff_kwh'], -150)
        self.assertEqual(
            period['search']['coarse_grid']['period_ac_kwh'][1][1], 600)
        with patch('solarna.reporting.optimize', return_value=raw):
            custom = reporting.build_period_analysis(
                model, annual, 'custom', 30, 1,
                custom_months=[9, 10, 11])
        self.assertEqual(custom['months'], [9, 10, 11])
        self.assertEqual(custom['preset'], 'custom')
        self.assertIn('9, 10, 11', custom['label'])


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        weather = synthetic_weather(8760, '1990-01-01')
        with patch('solarna.reporting.optimize', side_effect=analytic_optimize):
            cls.report = reporting.build_report(weather, provenance(), Site(), System(), 30,
                                                timing_sensitivity=True)

    def test_mobile_artifacts_accessible_heatmap_escaping_and_icons(self):
        report = deepcopy(self.report)
        attack = '</script><script>alert(1)</script>'
        report['site']['name'] = attack
        report['weather_source']['source'] = attack
        artifacts = dashboard.build_artifacts([report, self.report])
        html = artifacts['index.html'].decode()
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('name="viewport"', html)
        self.assertIn('aria-labelledby="site-0-map-title"', html)
        self.assertIn('aria-labelledby="site-1-map-title"', html)
        self.assertIn('Accessible heatmap data', html)
        self.assertIn('Monthly AC energy', html)
        self.assertIn('not a native iOS app', html)
        manifest = json.loads(artifacts['manifest.webmanifest'])
        self.assertEqual(manifest['display'], 'standalone')
        self.assertEqual(manifest['start_url'], './index.html')
        for size in (180, 192, 512):
            raw = artifacts[f'icon-{size}.png']
            self.assertEqual(raw[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('!II', raw[16:24]), (size, size))
            self.assertEqual(raw[24], 8)
            self.assertIn(raw[25], (2, 6))
            channels = 3 if raw[25] == 2 else 4
            cursor, compressed = 8, bytearray()
            while cursor < len(raw):
                length = struct.unpack('!I', raw[cursor:cursor+4])[0]
                kind = raw[cursor+4:cursor+8]
                data = raw[cursor+8:cursor+8+length]
                crc = struct.unpack('!I', raw[cursor+8+length:cursor+12+length])[0]
                self.assertEqual(crc, zlib.crc32(kind + data) & 0xffffffff)
                if kind == b'IDAT':
                    compressed.extend(data)
                cursor += length + 12
            self.assertEqual(
                len(zlib.decompress(compressed)),
                size * (1 + size * channels))
        self.assertEqual(len(json.loads(artifacts['reports.json'])), 2)

    def test_old_or_corrupt_reports_are_rejected(self):
        changes = [lambda r: r.update(schema_version=1),
                   lambda r: r['best']['monthly_ac_kwh'].update({'1': 0}),
                   lambda r: r['search']['coarse_grid']['annual_ac_kwh'].pop(),
                   lambda r: r['search']['coarse_grid']['annual_ac_kwh'][0].pop(),
                   lambda r: r['search']['coarse_grid']['annual_ac_kwh'][0].__setitem__(0, float('nan'))]
        for change in changes:
            report = deepcopy(self.report)
            change(report)
            with self.assertRaises(ValueError):
                dashboard.build_artifacts([report])
        with self.assertRaises(ValueError):
            dashboard.build_artifacts([])

    def test_build_and_read_only_artifact_check(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reporting.write_report(self.report, root / 'sfax.json')
            args = ['--reports', str(root), '--output', str(root / 'web')]
            self.assertEqual(dashboard.main(args), 0)
            self.assertEqual(dashboard.main(args + ['--check']), 0)
            page = root / 'web' / 'index.html'
            page.write_text('stale', encoding='utf-8')
            self.assertEqual(dashboard.main(args + ['--check']), 1)
            self.assertEqual(page.read_text(), 'stale')


class BatchTests(unittest.TestCase):
    def test_official_governorate_capital_sample_has_24_sites(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "examples" / "tunisia-governorate-capitals.csv"
        )
        sites = batch.read_sites(path)
        self.assertEqual(len(sites), 24)
        self.assertEqual(len({key for key, _ in sites}), 24)
        sfax = dict(sites)["sfax"]
        self.assertAlmostEqual(sfax.latitude, 34.74056)
        self.assertAlmostEqual(sfax.longitude, 10.76028)
        self.assertTrue(all(site.altitude_m == 0 for _, site in sites))

    def test_csv_validation_precedes_fetch(self):
        header = 'id,name,latitude,longitude,altitude_m\n'
        valid = 'sfax,Sfax,34.7406,10.7603,0\n'
        bad_rows = ['../x,X,34,10,0\n', valid + valid, 'x,X,99,10,0\n',
                    'x,X,34,10,nan\n', 'x,X,34,10\n', 'x,X,34,10,0,extra\n', '']
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sites.csv'
            path.write_text(header + valid, encoding='utf-8')
            self.assertEqual(batch.read_sites(path)[0][0], 'sfax')
            for rows in bad_rows:
                path.write_text(header + rows, encoding='utf-8')
                with patch('solarna.batch.load_tmy') as fetch:
                    self.assertEqual(batch.main(['--sites', str(path)]), 1)
                    fetch.assert_not_called()

    def test_paced_success_failure_and_output_names(self):
        sites = [('sfax', Site()), ('tunis', Site(36.8065, 10.1815, name='Tunis')),
                 ('djerba', Site(33.8, 10.85, name='Djerba'))]
        with tempfile.TemporaryDirectory() as folder:
            with patch('solarna.batch.load_tmy', side_effect=[('weather', {}), OSError('offline'), ('weather', {})]), \
                    patch('solarna.batch.build_report', return_value={'test': True}) as build, \
                    patch('solarna.batch.time.sleep') as sleep:
                failed = batch.run_batch(sites, Path(folder), Path(folder) / 'cache', 2, 30, True)
            self.assertEqual(failed, ['tunis'])
            self.assertEqual(sleep.call_count, 2)
            sleep.assert_called_with(2)
            self.assertEqual(build.call_count, 2)
            self.assertTrue(build.call_args.kwargs['timing_sensitivity'])
            self.assertEqual(sorted(p.name for p in Path(folder).glob('*.json')), ['site-djerba.json', 'site-sfax.json'])
            for pause in (0, -1, float('nan')):
                with self.assertRaises(ValueError):
                    batch.run_batch(sites, Path(folder), Path(folder), pause)


class DeploymentTests(unittest.TestCase):
    def test_tunnel_profile_is_isolated_and_packages_native_downloads(self):
        root = Path(__file__).resolve().parents[1]
        dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
        compose = (root / "compose.tunnel.yaml").read_text(encoding="utf-8")
        ignored = (root / ".dockerignore").read_text(encoding="utf-8")
        package_script = (
            root / "scripts" / "build" / "package-server-release.ps1"
        ).read_text(encoding="utf-8")
        release_script = (
            root / "scripts" / "build" / "build-release.ps1"
        ).read_text(encoding="utf-8")
        production_launcher = (
            root / "scripts" / "production" / "start-solarna-production.ps1"
        ).read_text(encoding="utf-8")
        production_wrapper = (
            root / "scripts" / "production" / "run-solarna-production.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("Solarna-android.apk /app/downloads/", dockerfile)
        self.assertIn("Solarna-iOS-project.zip /app/downloads/", dockerfile)
        self.assertIn('"--android-apk"', dockerfile)
        self.assertIn('"--ios-project"', dockerfile)
        self.assertNotIn("\n    ports:", compose)
        self.assertIn("cloudflare/cloudflared:2026.9.1", compose)
        self.assertIn('network_mode: "service:solarna"', compose)
        self.assertIn('"8765"', compose)
        self.assertIn("http://127.0.0.1:8765", (
            root / "deploy" / "cloudflare-tunnel" / "README.md"
        ).read_text(encoding="utf-8"))
        self.assertIn("!outputs/deliverables/Solarna-android.apk", ignored)
        self.assertIn("!outputs/deliverables/Solarna-iOS-project.zip", ignored)
        self.assertIn('"compose.tunnel.yaml"', package_script)
        self.assertIn('"deploy\\cloudflare-tunnel"', package_script)
        self.assertIn(
            '"scripts\\production\\start-solarna-production.ps1"',
            package_script)
        self.assertIn(
            '"scripts\\production\\run-solarna-production.ps1"',
            package_script)
        self.assertIn(
            '"scripts\\production\\setup-solarna-production.ps1"',
            package_script)
        self.assertIn('$androidArguments = @{}', release_script)
        self.assertIn('$androidArguments["ApiUrl"] = $ApiUrl', release_script)
        self.assertIn("pv.solarnasystems.com", production_launcher)
        self.assertIn("cloudflared-token.txt", production_launcher)
        self.assertIn("SOLARNA_SUPABASE_URL", production_launcher)
        self.assertIn("SOLARNA_SUPABASE_PUBLISHABLE_KEY", production_launcher)
        self.assertIn("--token-file", production_launcher)
        self.assertIn("-WindowStyle Hidden", production_launcher)
        self.assertIn("launcher-error.log", production_wrapper)


if __name__ == '__main__':
    unittest.main()
