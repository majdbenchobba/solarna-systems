"""Offline synthetic tests verify implementation, not real Sfax production."""

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import pvlib

from solarna.engine import (
    EnergyModel,
    Site,
    System,
    diffuse_iam,
    normalize_months,
    optimize,
    validate_weather,
)


def synthetic_weather(periods=48, start="1990-06-20"):
    index = pd.date_range(start, periods=periods, freq="h", tz="UTC")
    site = Site()
    location = pvlib.location.Location(site.latitude, site.longitude, tz="UTC", altitude=site.altitude_m)
    weather = location.get_clearsky(index)[["ghi", "dni", "dhi"]]
    weather["temp_air"] = 25.0
    weather["wind_speed"] = 2.0
    return weather


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.weather = synthetic_weather()
        self.model = EnergyModel(self.weather, Site(), System())

    def test_facing_sun_has_zero_incidence_angle(self):
        self.assertAlmostEqual(float(pvlib.irradiance.aoi(30, 180, 30, 180)), 0, places=5)

    def test_optical_modifiers_are_physical(self):
        self.assertAlmostEqual(float(pvlib.iam.physical(0)), 1)
        self.assertLess(float(pvlib.iam.physical(80)), 1)
        self.assertEqual(float(pvlib.iam.physical(100)), 0)
        for value in diffuse_iam(30).values():
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 1)

    def test_night_zero_and_power_bounded_by_inverter(self):
        result = self.model.simulate(30, 180)
        night = self.model.position["apparent_elevation"] <= 0
        self.assertTrue((result.loc[night, "ac_w"] == 0).all())
        self.assertTrue((result["ac_w"] >= 0).all())
        self.assertLessEqual(result["ac_w"].max(), 1000 / 1.2 + 1e-8)
        self.assertGreater(result["ac_w"].sum(), 0)
        self.assertTrue((result["effective_w_m2"] <= result["poa_w_m2"] + 1e-8).all())

    def test_zero_irradiance_during_daylight_produces_zero_power(self):
        weather = self.weather.copy()
        weather[["ghi", "dni", "dhi"]] = 0.0
        result = EnergyModel(weather, Site(), System()).simulate(30, 180)
        self.assertTrue(np.isfinite(result.to_numpy()).all())
        self.assertTrue((result[["poa_w_m2", "effective_w_m2", "ac_w"]] == 0).all().all())

    def test_zero_diffuse_retains_direct_beam(self):
        weather = self.weather.copy()
        weather["dhi"] = 0.0
        weather["ghi"] = weather["dni"] * np.maximum(
            0, np.cos(np.radians(self.model.position["apparent_zenith"])))
        model = EnergyModel(weather, Site(), System())
        result = model.simulate(0, 180)
        self.assertTrue(np.isfinite(result.to_numpy()).all())
        np.testing.assert_allclose(result["poa_w_m2"], weather["ghi"], atol=1e-8)
        self.assertGreater(result["ac_w"].sum(), 0)

    def test_horizontal_output_independent_of_azimuth(self):
        self.assertAlmostEqual(self.model.energy_kwh(0, 0), self.model.energy_kwh(0, 180), places=8)

    def test_capacity_scaling_and_hourly_units(self):
        double = EnergyModel(self.weather, Site(), System(dc_capacity_kw=2))
        self.assertAlmostEqual(double.energy_kwh(30, 180), 2 * self.model.energy_kwh(30, 180))
        expected = self.model.simulate(30, 180)["ac_w"].sum() / 1000
        self.assertAlmostEqual(self.model.energy_kwh(30, 180), expected)
        selected = self.model.energy_kwh(30, 180, [6])
        self.assertAlmostEqual(selected, expected)
        self.assertEqual(self.model.energy_kwh(30, 180, [1]), 0)
        self.assertEqual(normalize_months([12, 1, 2]), (12, 1, 2))
        for months in ([], [0], [13], [1, 1], [True]):
            with self.subTest(months=months), self.assertRaises(ValueError):
                normalize_months(months)

    def test_higher_temperature_reduces_unclipped_output(self):
        hot = self.weather.copy()
        hot["temp_air"] = 45
        system = System(dc_ac_ratio=0.8)
        self.assertLess(EnergyModel(hot, Site(), system).energy_kwh(30, 180),
                        EnergyModel(self.weather, Site(), system).energy_kwh(30, 180))

    def test_mounting_thermal_preset_changes_yield(self):
        open_rack = System(
            dc_ac_ratio=0.8, temperature_model="open_rack_glass_polymer")
        insulated = System(
            dc_ac_ratio=0.8, temperature_model="insulated_back_glass_polymer")
        self.assertGreater(
            EnergyModel(self.weather, Site(), open_rack).energy_kwh(30, 180),
            EnergyModel(self.weather, Site(), insulated).energy_kwh(30, 180),
        )

    def test_invalid_weather_is_rejected(self):
        bad_frames = []
        bad = self.weather.copy(); bad.iloc[0, 0] = np.nan; bad_frames.append(bad)
        bad = self.weather.copy(); bad.iloc[0, 1] = -1; bad_frames.append(bad)
        bad = self.weather.copy(); bad.index = bad.index.tz_localize(None); bad_frames.append(bad)
        bad_frames.extend([self.weather.iloc[::-1], self.weather.drop(self.weather.index[3]),
                           self.weather.drop(columns="dni")])
        for bad in bad_frames:
            with self.subTest(shape=bad.shape), self.assertRaises(ValueError):
                validate_weather(bad)
        with self.assertRaises(ValueError):
            validate_weather(self.weather, require_year=True)

    def test_invalid_configuration(self):
        for create in (lambda: Site(latitude=91), lambda: Site(longitude=float("nan")),
                       lambda: System(dc_capacity_kw=0), lambda: System(albedo=2),
                       lambda: System(other_dc_loss_fraction=1),
                       lambda: System(temperature_model="unknown")):
            with self.assertRaises(ValueError):
                create()
        for angles in [(-1, 180), (91, 180), (30, 360), (30, float("nan"))]:
            with self.assertRaises(ValueError):
                self.model.simulate(*angles)

    def test_annual_real_physics_smoke(self):
        weather = synthetic_weather(8760, "1990-01-01")
        validate_weather(weather, require_year=True)
        annual = EnergyModel(weather, Site(), System())
        self.assertGreater(annual.energy_kwh(30, 180), annual.energy_kwh(90, 0))

    def test_search_finds_known_optimum_and_reports_baselines(self):
        # Analytic surface isolates the optimizer from expensive PV simulation.
        weather = synthetic_weather(8760, "1990-01-01")
        model = EnergyModel(weather, Site(), System())
        def energy(tilt, azimuth):
            distance = abs((azimuth - 183 + 180) % 360 - 180)
            return 2000 - 0.1 * (tilt - 28) ** 2 - 0.01 * distance ** 2
        def simulate(tilt, azimuth):
            return pd.DataFrame({"ac_w": energy(tilt, azimuth) * 1000 / 8760,
                                 "poa_w_m2": 250.0}, index=weather.index)
        with patch.object(model, "energy_kwh", side_effect=energy), patch.object(model, "simulate", side_effect=simulate):
            report = optimize(model, coarse_step=15)
        self.assertEqual(report["best"]["tilt_deg"], 28)
        self.assertEqual(report["best"]["azimuth_deg"], 183)
        self.assertAlmostEqual(sum(report["best"]["monthly_ac_kwh"].values()), 2000)
        self.assertAlmostEqual(report["best"]["average_daily_ac_kwh"], 2000 / 365)
        self.assertAlmostEqual(
            report["baselines"]["30_degrees_south"]["average_daily_ac_kwh"],
            report["baselines"]["30_degrees_south"]["annual_ac_kwh"] / 365)
        self.assertGreaterEqual(report["baselines"]["30_degrees_south"]["gain_of_best_percent"], 0)
        self.assertTrue(all(p["annual_ac_kwh"] >= 1980
                            for p in report["search"]["near_optimal_sampled_orientations"]))

    def test_search_wraps_north_and_rejects_zero_generation(self):
        weather = synthetic_weather(8760, "1990-01-01")
        model = EnergyModel(weather, Site(), System())
        def energy(tilt, azimuth):
            distance = abs((azimuth - 359 + 180) % 360 - 180)
            return 2000 - 0.1 * (tilt - 28) ** 2 - 0.01 * distance ** 2
        with patch.object(model, "energy_kwh", side_effect=energy):
            report = optimize(model, coarse_step=30)
        self.assertEqual(report["best"]["azimuth_deg"], 359)
        with patch.object(model, "energy_kwh", return_value=0), self.assertRaises(ValueError):
            optimize(model, coarse_step=30)

    def test_required_orientation_participates_in_best_candidate(self):
        weather = synthetic_weather(8760, "1990-01-01")
        model = EnergyModel(weather, Site(), System())
        required = (12.5, 123.5)

        def energy(tilt, azimuth):
            if (tilt, azimuth) == required:
                return 2100
            return 2000 - 0.1 * tilt

        def simulate(tilt, azimuth):
            return pd.DataFrame({
                "ac_w": energy(tilt, azimuth) * 1000 / 8760,
                "poa_w_m2": 250.0,
            }, index=weather.index)

        with patch.object(model, "energy_kwh", side_effect=energy), \
                patch.object(model, "simulate", side_effect=simulate):
            report = optimize(
                model, coarse_step=30,
                required_orientations=(required,))
        self.assertEqual(
            (report["best"]["tilt_deg"], report["best"]["azimuth_deg"]),
            required)
        self.assertEqual(report["best"]["annual_ac_kwh"], 2100)
        self.assertTrue(any(
            point["tilt_deg"] == required[0]
            and point["azimuth_deg"] == required[1]
            for point in report["search"]["near_optimal_sampled_orientations"]))

    def test_search_progress_reports_coarse_refinement_and_finalization(self):
        weather = synthetic_weather(8760, "1990-01-01")
        model = EnergyModel(weather, Site(), System())
        events = []
        with patch.object(model, "energy_kwh", return_value=1000), \
                patch.object(model, "simulate", return_value=pd.DataFrame(
                    {"ac_w": 1000 * 1000 / 8760, "poa_w_m2": 200},
                    index=weather.index)):
            optimize(model, coarse_step=30,
                     progress_callback=lambda phase, done, total:
                     events.append((phase, done, total)))
        self.assertEqual(events[0][0:2], ("coarse_search", 0))
        self.assertIn(("coarse_search", 48, 48), events)
        self.assertTrue(any(event[0] == "fine_search" and event[1] == event[2]
                            for event in events))
        self.assertEqual(events[-1], ("finalizing", 2, 2))


class TimingTests(unittest.TestCase):
    def test_geometry_offset_preserves_rows_and_matches_shifted_spa(self):
        weather = synthetic_weather(48, "1990-12-30")
        original = weather.copy(deep=True)
        for offset in (0.0, 0.1626, 0.5, -0.25):
            with self.subTest(offset=offset):
                model = EnergyModel(weather, Site(), System(), offset)
                shifted = weather.index + pd.Timedelta(offset, unit="h")
                expected = pvlib.solarposition.get_solarposition(
                    shifted, Site().latitude, Site().longitude, altitude=0,
                    temperature=weather["temp_air"].to_numpy(), method="nrel_numpy")
                np.testing.assert_allclose(model.position, expected)
                np.testing.assert_allclose(model.dni_extra, pvlib.irradiance.get_extra_radiation(shifted))
                pd.testing.assert_index_equal(model.position.index, weather.index)
                result = model.simulate(30, 180)
                pd.testing.assert_index_equal(result.index, weather.index)
                self.assertTrue(np.isfinite(result.to_numpy()).all())
                self.assertAlmostEqual(model.energy_kwh(30, 180), result["ac_w"].sum() / 1000)
        pd.testing.assert_frame_equal(weather, original)

    def test_annual_boundaries_stay_nominal(self):
        weather = synthetic_weather(8760, "1990-01-01")
        model = EnergyModel(weather, Site(), System(), -0.25)
        self.assertEqual(model.solar_times[0].year, 1989)
        validate_weather(model.weather, require_year=True)
        self.assertEqual(len(model.simulate(30, 180)), 8760)
        self.assertFalse(model.position.equals(EnergyModel(weather, Site(), System()).position))

    def test_invalid_offset_is_rejected(self):
        for offset in (True, float("nan"), float("inf"), -1, 1):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                EnergyModel(synthetic_weather(), Site(), System(), offset)


if __name__ == "__main__":
    unittest.main()
