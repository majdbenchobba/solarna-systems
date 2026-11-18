"""Fixed monofacial PV energy model. Angles are degrees; azimuth is true-north based."""

from dataclasses import asdict, dataclass
from functools import lru_cache
import math

import numpy as np
import pandas as pd
import pvlib


SAPM_TEMPERATURE_MODELS = (
    "open_rack_glass_glass",
    "close_mount_glass_glass",
    "open_rack_glass_polymer",
    "insulated_back_glass_polymer",
)


@dataclass(frozen=True)
class Site:
    latitude: float = 34.7406
    longitude: float = 10.7603
    altitude_m: float = 0.0
    name: str = "Sfax (approximate city centre)"

    def __post_init__(self):
        if not all(math.isfinite(v) for v in (self.latitude, self.longitude, self.altitude_m)):
            raise ValueError("Site coordinates and altitude must be finite")
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ValueError("Latitude/longitude outside valid geographic ranges")
        if not -500 <= self.altitude_m <= 9000:
            raise ValueError("Altitude outside supported range (-500 to 9000 m)")


@dataclass(frozen=True)
class System:
    dc_capacity_kw: float = 1.0
    gamma_pdc_per_c: float = -0.004
    dc_ac_ratio: float = 1.2
    inverter_efficiency: float = 0.96
    albedo: float = 0.2
    other_dc_loss_fraction: float = 0.0
    temperature_model: str = "open_rack_glass_glass"

    def __post_init__(self):
        numeric = (
            self.dc_capacity_kw,
            self.gamma_pdc_per_c,
            self.dc_ac_ratio,
            self.inverter_efficiency,
            self.albedo,
            self.other_dc_loss_fraction,
        )
        if not all(math.isfinite(v) for v in numeric):
            raise ValueError("System parameters must be finite")
        if self.dc_capacity_kw <= 0 or self.dc_ac_ratio <= 0:
            raise ValueError("Capacity and DC/AC ratio must be positive")
        if not 0 < self.inverter_efficiency <= 1 or not 0 <= self.albedo <= 1:
            raise ValueError("Invalid inverter efficiency or albedo")
        if not 0 <= self.other_dc_loss_fraction < 1:
            raise ValueError("Other DC losses must be in [0, 1)")
        if not -0.02 <= self.gamma_pdc_per_c <= 0:
            raise ValueError("Unsupported PV power temperature coefficient")
        if self.temperature_model not in SAPM_TEMPERATURE_MODELS:
            raise ValueError("Unsupported SAPM module/mounting temperature model")


def validate_weather(weather: pd.DataFrame, require_year: bool = False):
    required = ["ghi", "dni", "dhi", "temp_air", "wind_speed"]
    if not set(required).issubset(weather.columns):
        raise ValueError(f"Weather requires columns: {required}")
    if not isinstance(weather.index, pd.DatetimeIndex) or weather.index.tz is None:
        raise ValueError("Weather needs a timezone-aware DatetimeIndex")
    if str(weather.index.tz) != "UTC":
        raise ValueError("Normalize weather timestamps to UTC before modeling")
    if len(weather) < 2 or not weather.index.is_unique or not weather.index.is_monotonic_increasing:
        raise ValueError("Weather timestamps must be unique and increasing")
    if not (weather.index.to_series().diff().iloc[1:] == pd.Timedelta(1, unit="h")).all():
        raise ValueError("Only complete, regularly spaced hourly weather is supported")
    values = weather[required].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Weather contains missing or non-finite values")
    if (weather[["ghi", "dni", "dhi", "wind_speed"]] < 0).any().any():
        raise ValueError("Irradiance and wind speed cannot be negative")
    if require_year:
        first, last = weather.index[0], weather.index[-1]
        expected = 8784 if first.is_leap_year else 8760
        if (len(weather) != expected or first.year != last.year
                or (first.month, first.day, first.hour) != (1, 1, 0)
                or (last.month, last.day, last.hour) != (12, 31, 23)):
            raise ValueError("Annual optimization requires one complete UTC calendar year")


def normalize_months(months) -> tuple[int, ...]:
    if not isinstance(months, (list, tuple, set)) or not months:
        raise ValueError("Months must be a non-empty collection")
    values = tuple(int(month) for month in months)
    if (any(isinstance(month, bool) for month in months)
            or len(values) != len(set(values))
            or any(month < 1 or month > 12 for month in values)):
        raise ValueError("Months must be unique integers from 1 to 12")
    return values


@lru_cache(maxsize=512)
def diffuse_iam(tilt: float):
    # Integrates cover optics over isotropic sky/ground directions. Applying the
    # sky factor to aggregate Perez diffuse is an explicitly approximate treatment.
    return pvlib.iam.marion_diffuse("physical", tilt)


class EnergyModel:
    def __init__(self, weather: pd.DataFrame, site: Site, system: System,
                 irradiance_time_offset_hours: float = 0.0):
        validate_weather(weather)
        if (isinstance(irradiance_time_offset_hours, bool)
                or not math.isfinite(irradiance_time_offset_hours)
                or not -1 < irradiance_time_offset_hours < 1):
            raise ValueError("Irradiance timing offset must be finite and strictly between -1 and 1 hour")
        self.weather = weather.copy()
        self.site = site
        self.system = system
        self.irradiance_time_offset_hours = float(irradiance_time_offset_hours)
        # Shift geometry only. Keep row pairing, temperature/wind, monthly labels,
        # and one-hour integration unchanged; never shift/resample raw weather.
        self.solar_times = weather.index + pd.Timedelta(
            self.irradiance_time_offset_hours, unit="h"
        )
        self.position = pvlib.solarposition.get_solarposition(
            self.solar_times, site.latitude, site.longitude, altitude=site.altitude_m,
            temperature=weather["temp_air"].to_numpy(), method="nrel_numpy",
        ).set_axis(weather.index)
        self.dni_extra = pvlib.irradiance.get_extra_radiation(self.solar_times).set_axis(weather.index)
        self.airmass = pvlib.atmosphere.get_relative_airmass(self.position["apparent_zenith"])

    def simulate(self, tilt: float, azimuth: float):
        if not math.isfinite(tilt) or not 0 <= tilt <= 90:
            raise ValueError("Tilt must be finite and between 0 and 90 degrees")
        if not math.isfinite(azimuth) or not 0 <= azimuth < 360:
            raise ValueError("Azimuth must be finite and in [0, 360)")
        w, s, sun = self.weather, self.system, self.position
        poa = pvlib.irradiance.get_total_irradiance(
            surface_tilt=tilt, surface_azimuth=azimuth,
            solar_zenith=sun["apparent_zenith"], solar_azimuth=sun["azimuth"],
            dni=w["dni"], ghi=w["ghi"], dhi=w["dhi"],
            dni_extra=self.dni_extra, airmass=self.airmass,
            albedo=s.albedo, model="perez-driesse",
        )
        # Perez clearness is undefined at DHI=0. Its physical sky contribution
        # is zero, including direct-only daylight; retain beam/ground components.
        poa.loc[w["dhi"] == 0, "poa_sky_diffuse"] = 0.0
        poa["poa_diffuse"] = poa["poa_sky_diffuse"] + poa["poa_ground_diffuse"]
        poa["poa_global"] = poa["poa_direct"] + poa["poa_diffuse"]
        # Perez can be undefined below the horizon. No night generation is modeled.
        night = sun["apparent_elevation"] <= 0
        poa.loc[night, :] = 0.0
        if not np.isfinite(poa.to_numpy()).all():
            raise ValueError("Transposition produced invalid daylight irradiance")
        poa = poa.clip(lower=0)
        aoi = pvlib.irradiance.aoi(tilt, azimuth, sun["apparent_zenith"], sun["azimuth"])
        beam_iam = pvlib.iam.physical(aoi)
        diffuse = diffuse_iam(float(tilt))
        effective = (
            poa["poa_direct"] * beam_iam
            + poa["poa_sky_diffuse"] * diffuse["sky"]
            + poa["poa_ground_diffuse"] * diffuse["ground"]
        ).clip(lower=0)
        thermal = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS[
            "sapm"][s.temperature_model]
        cell_temperature = pvlib.temperature.sapm_cell(
            poa["poa_global"], w["temp_air"], w["wind_speed"], **thermal,
        )
        dc = pvlib.pvsystem.pvwatts_dc(
            effective, cell_temperature, pdc0=s.dc_capacity_kw * 1000,
            gamma_pdc=s.gamma_pdc_per_c,
        ).clip(lower=0) * (1 - s.other_dc_loss_fraction)
        ac_rating_w = s.dc_capacity_kw * 1000 / s.dc_ac_ratio
        ac = pvlib.inverter.pvwatts(
            dc, pdc0=ac_rating_w / s.inverter_efficiency,
            eta_inv_nom=s.inverter_efficiency,
        ).clip(lower=0)
        if not np.isfinite(ac.to_numpy()).all():
            raise ValueError("Electrical model produced non-finite power")
        return pd.DataFrame({
            "poa_w_m2": poa["poa_global"], "effective_w_m2": effective,
            "cell_temperature_c": cell_temperature, "ac_w": ac,
        }, index=w.index)

    def energy_kwh(self, tilt: float, azimuth: float, months=None):
        # Hourly samples represent hourly mean power: sum(P * 1 hour), not trapz.
        power = self.simulate(tilt, azimuth)["ac_w"]
        if months is not None:
            selected = normalize_months(months)
            power = power[power.index.month.isin(selected)]
        return float(power.sum() / 1000)


def optimize(model: EnergyModel, coarse_step: int = 5, fine_step: float = 1.0,
             near_fraction: float = 0.01, progress_callback=None,
             required_orientations=()):
    """Global coarse grid, then local refinement. Not a continuous-global guarantee."""
    validate_weather(model.weather, require_year=True)
    if coarse_step not in (5, 10, 15, 30):
        raise ValueError("Coarse step must be 5, 10, 15, or 30 degrees")
    if fine_step not in (0.5, 1.0) or not 0 <= near_fraction < 1:
        raise ValueError("Fine step must be 0.5 or 1 degree; tolerance must be in [0, 1)")
    samples = {}

    def evaluate(tilt, azimuth):
        key = (round(float(tilt), 6), round(float(azimuth) % 360, 6))
        if key not in samples:
            energy = model.energy_kwh(*key)
            if not math.isfinite(energy) or energy < 0:
                raise ValueError("Candidate energy must be finite and nonnegative")
            samples[key] = energy
        return samples[key]

    coarse_tilts = list(range(0, 91, coarse_step))
    coarse_azimuths = list(range(0, 360, coarse_step))
    coarse_total = len(coarse_tilts) * len(coarse_azimuths)
    coarse_done = 0
    if progress_callback:
        progress_callback("coarse_search", 0, coarse_total)
    for tilt in coarse_tilts:
        for azimuth in coarse_azimuths:
            evaluate(tilt, azimuth)
            coarse_done += 1
            if progress_callback and (coarse_done == coarse_total
                                      or coarse_done % max(1, coarse_total // 100) == 0):
                progress_callback("coarse_search", coarse_done, coarse_total)
    centre = max(samples, key=samples.get)
    fine_tilts = np.arange(max(0, centre[0] - coarse_step),
                           min(90, centre[0] + coarse_step) + fine_step / 2, fine_step)
    fine_azimuths = np.arange(centre[1] - coarse_step,
                              centre[1] + coarse_step + fine_step / 2, fine_step)
    fine_total = len(fine_tilts) * len(fine_azimuths)
    fine_done = 0
    if progress_callback:
        progress_callback("fine_search", 0, fine_total)
    for tilt in fine_tilts:
        for azimuth in fine_azimuths:
            evaluate(tilt, azimuth)
            fine_done += 1
            if progress_callback and (fine_done == fine_total
                                      or fine_done % max(1, fine_total // 100) == 0):
                progress_callback("fine_search", fine_done, fine_total)

    # Baselines and explicitly requested comparisons also participate in the
    # final candidate comparison, so the reported optimum cannot underperform
    # an evaluated existing installation.
    required_orientations = tuple(required_orientations)
    final_total = 2 + len(required_orientations)
    if progress_callback:
        progress_callback("finalizing", 0, final_total)
    south_energy = evaluate(30, 180)
    latitude_tilt = abs(model.site.latitude)
    latitude_azimuth = 180.0 if model.site.latitude >= 0 else 0.0
    latitude_energy = evaluate(latitude_tilt, latitude_azimuth)
    for index, orientation in enumerate(required_orientations, start=1):
        if (not isinstance(orientation, (tuple, list))
                or len(orientation) != 2):
            raise ValueError(
                "Required orientations must contain tilt/azimuth pairs")
        evaluate(orientation[0], orientation[1])
        if progress_callback:
            progress_callback("finalizing", 2 + index, final_total)
    if progress_callback and not required_orientations:
        progress_callback("finalizing", final_total, final_total)
    best_angles = max(samples, key=samples.get)
    best_energy = samples[best_angles]
    if best_energy <= 0:
        raise ValueError("No modeled electrical generation: cannot identify an optimum")
    best_run = model.simulate(*best_angles)
    near = [
        {"tilt_deg": t, "azimuth_deg": a, "annual_ac_kwh": e}
        for (t, a), e in sorted(samples.items())
        if e >= best_energy * (1 - near_fraction)
    ]

    def baseline(tilt, azimuth, energy):
        return {
            "tilt_deg": tilt, "azimuth_deg": azimuth, "annual_ac_kwh": energy,
            "average_daily_ac_kwh": energy / 365,
            "gain_of_best_percent": 100 * (best_energy / energy - 1) if energy > 0 else None,
        }

    return {
        "schema_version": 2,
        "timing": {
            "irradiance_time_offset_hours": model.irradiance_time_offset_hours,
            "method": "Solar geometry = nominal UTC timestamp + irradiance offset; "
                      "weather row pairing, monthly labels and one-hour integration are unchanged.",
        },
        "site": asdict(model.site), "system": asdict(model.system),
        "angle_convention": "Tilt from horizontal; azimuth clockwise from true north (south=180).",
        "weather_period": {"start": str(model.weather.index[0]),
                           "end": str(model.weather.index[-1]), "hours": len(model.weather)},
        "best": {
            "tilt_deg": best_angles[0], "azimuth_deg": best_angles[1],
            "annual_ac_kwh": best_energy,
            "average_daily_ac_kwh": best_energy / 365,
            "specific_yield_kwh_per_kwp": best_energy / model.system.dc_capacity_kw,
            "annual_poa_kwh_m2": float(best_run["poa_w_m2"].sum() / 1000),
            "monthly_ac_kwh": {
                str(int(month)): float(energy / 1000)
                for month, energy in best_run["ac_w"].groupby(best_run.index.month).sum().items()
            },
        },
        "baselines": {
            "30_degrees_south": baseline(30, 180, south_energy),
            "latitude_tilt_equator_facing": baseline(latitude_tilt, latitude_azimuth, latitude_energy),
        },
        "search": {
            "coarse_step_deg": coarse_step, "fine_step_deg": fine_step,
            "candidate_count": len(samples), "near_optimal_fraction": near_fraction,
            "coarse_grid": {
                "tilt_deg": list(range(0, 91, coarse_step)),
                "azimuth_deg": list(range(0, 360, coarse_step)),
                "annual_ac_kwh": [
                    [samples[(float(t), float(a))] for a in range(0, 360, coarse_step)]
                    for t in range(0, 91, coarse_step)
                ],
                "layout": "Rows are tilt; columns are true-north azimuth. Coarse samples only.",
            },
            "near_optimal_sampled_orientations": near,
            "note": "Near-optimal points are sampled alternatives, not a confidence interval. "
                    "Coarse-to-fine search does not prove the continuous global optimum.",
        },
        "assumptions_and_limitations": [
            "Fixed monofacial array; unconstrained tilt 0..90 and azimuth 0..360 degrees.",
            "No nearby shading, row shading, roof constraints, snow, bifacial gain, or tracking.",
            f"SAPM {model.system.temperature_model.replace('_', ' ')} thermal preset, "
            "not a calibrated model of the selected installation.",
            "Generic PVWatts electrical model; no module-specific spectral model or MPPT dynamics.",
            "Physical glass IAM uses pvlib defaults; no measured cover/coating parameters.",
            "Continuous Perez-Driesse sky diffuse with isotropic-integrated sky IAM "
            "is an optical approximation.",
            "Atmospheric refraction uses NREL SPA; no extra atmospheric attenuation is applied to weather irradiance.",
            "Solar geometry uses the report's irradiance timing offset; no weather resampling is performed. "
            "Hourly irradiance approximation and subhourly/cloud effects remain.",
            "Albedo and optional other DC losses are constant, not locally calibrated.",
            "No quantified uncertainty or field validation; fine angle resolution is not physical accuracy.",
        ],
    }
