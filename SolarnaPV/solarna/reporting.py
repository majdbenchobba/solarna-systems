"""Shared report workflow for single sites and paced batches."""

from datetime import datetime, timezone
import json
import math
from pathlib import Path

import pvlib

from . import __version__
from .engine import EnergyModel, normalize_months, optimize
from .weather import irradiance_offset_hours


PERIOD_ANALYSES = {
    "winter": {
        "label": "Winter focus (November-March)",
        "months": (11, 12, 1, 2, 3),
    },
    "summer": {
        "label": "Summer focus (June-August)",
        "months": (6, 7, 8),
    },
    "spring": {
        "label": "Spring focus (March-May)",
        "months": (3, 4, 5),
    },
    "autumn": {
        "label": "Autumn focus (September-November)",
        "months": (9, 10, 11),
    },
}


def normalize_existing_orientation(value):
    if value is None:
        return None
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError(
            "Existing orientation must contain a tilt and an azimuth")
    tilt, azimuth = value
    if (isinstance(tilt, bool) or isinstance(azimuth, bool)
            or not isinstance(tilt, (int, float))
            or not isinstance(azimuth, (int, float))
            or not math.isfinite(tilt) or not math.isfinite(azimuth)
            or not 0 <= tilt <= 90 or not 0 <= azimuth <= 360):
        raise ValueError(
            "Existing tilt must be 0-90° and azimuth must be 0-360°")
    return float(tilt), float(azimuth % 360)


class PeriodEnergyModel:
    """Adapter that scores selected months while retaining a full-year simulation."""

    def __init__(self, model: EnergyModel, months):
        self.model = model
        self.months = normalize_months(months)
        self.weather = model.weather
        self.site = model.site
        self.system = model.system
        self.irradiance_time_offset_hours = model.irradiance_time_offset_hours

    def energy_kwh(self, tilt, azimuth):
        return self.model.energy_kwh(tilt, azimuth, self.months)

    def simulate(self, tilt, azimuth):
        return self.model.simulate(tilt, azimuth)


def build_period_analysis(model, annual_report, preset, coarse_step, fine_step,
                          progress_callback=None, existing_orientation=None,
                          custom_months=None):
    if preset == "custom":
        months = normalize_months(custom_months)
        definition = {
            "label": "Custom month focus (" +
                     ", ".join(str(month) for month in months) + ")",
            "months": months,
        }
    elif preset in PERIOD_ANALYSES:
        definition = PERIOD_ANALYSES[preset]
        months = definition["months"]
    else:
        raise ValueError(
            "Period analysis must be winter, summer, spring, autumn, or custom")
    period_model = PeriodEnergyModel(model, months)
    optimize_options = {"progress_callback": progress_callback}
    if existing_orientation is not None:
        optimize_options["required_orientations"] = (existing_orientation,)
    raw = optimize(period_model, coarse_step, fine_step, **optimize_options)
    raw_best = raw["best"]
    period_best_energy = raw_best["annual_ac_kwh"]
    annual_at_period_best = sum(raw_best["monthly_ac_kwh"].values())
    annual_best_period_energy = sum(
        annual_report["best"]["monthly_ac_kwh"][str(month)]
        for month in months
    )
    if annual_best_period_energy <= 0:
        raise ValueError("Annual optimum has no energy in the selected period")

    def baseline(value):
        return {
            "tilt_deg": value["tilt_deg"],
            "azimuth_deg": value["azimuth_deg"],
            "period_ac_kwh": value["annual_ac_kwh"],
            "gain_of_period_best_percent": value["gain_of_best_percent"],
        }

    coarse = raw["search"]["coarse_grid"]
    return {
        "preset": preset,
        "label": definition["label"],
        "months": list(months),
        "best": {
            "tilt_deg": raw_best["tilt_deg"],
            "azimuth_deg": raw_best["azimuth_deg"],
            "period_ac_kwh": period_best_energy,
            "period_specific_yield_kwh_per_kwp": (
                period_best_energy / model.system.dc_capacity_kw),
            "annual_ac_kwh_at_period_optimum": annual_at_period_best,
            "annual_poa_kwh_m2_at_period_optimum": raw_best["annual_poa_kwh_m2"],
            "monthly_ac_kwh": raw_best["monthly_ac_kwh"],
        },
        "annual_optimum_during_period_kwh": annual_best_period_energy,
        "gain_over_annual_optimum_during_period_percent": (
            100 * (period_best_energy / annual_best_period_energy - 1)),
        "annual_energy_tradeoff_kwh": (
            annual_at_period_best - annual_report["best"]["annual_ac_kwh"]),
        "baselines": {
            "30_degrees_south": baseline(
                raw["baselines"]["30_degrees_south"]),
            "latitude_tilt_equator_facing": baseline(
                raw["baselines"]["latitude_tilt_equator_facing"]),
        },
        "search": {
            "coarse_step_deg": raw["search"]["coarse_step_deg"],
            "fine_step_deg": raw["search"]["fine_step_deg"],
            "candidate_count": raw["search"]["candidate_count"],
            "near_optimal_fraction": raw["search"]["near_optimal_fraction"],
            "near_optimal_sampled_orientations": [
                {
                    "tilt_deg": item["tilt_deg"],
                    "azimuth_deg": item["azimuth_deg"],
                    "period_ac_kwh": item["annual_ac_kwh"],
                }
                for item in raw["search"]["near_optimal_sampled_orientations"]
            ],
            "coarse_grid": {
                "tilt_deg": coarse["tilt_deg"],
                "azimuth_deg": coarse["azimuth_deg"],
                "period_ac_kwh": coarse["annual_ac_kwh"],
                "layout": "Rows are tilt; columns are true-north azimuth. "
                          "Values are selected-period AC energy.",
            },
        },
        "note": "This is an additional selected-month electrical-energy objective. "
                "The main report remains the all-year optimum.",
    }


def build_report(weather, provenance, site, system, coarse_step=5, fine_step=1.0,
                 timing_sensitivity=False, period_analysis=None,
                 progress_callback=None, existing_orientation=None,
                 period_months=None):
    existing_orientation = normalize_existing_orientation(existing_orientation)
    offset = irradiance_offset_hours(provenance)
    model = EnergyModel(weather, site, system, offset)
    primary_progress = None
    if progress_callback:
        primary_progress = lambda phase, done, total: progress_callback(
            "corrected_timing", phase, done, total)
    optimize_options = {}
    if primary_progress:
        optimize_options["progress_callback"] = primary_progress
    if existing_orientation is not None:
        optimize_options["required_orientations"] = (existing_orientation,)
    report = optimize(model, coarse_step, fine_step, **optimize_options)
    numerical_best = report["best"]
    practical_tilt = min(
        90.0, max(0.0, round(numerical_best["tilt_deg"] / 5) * 5.0))
    practical_azimuth = (
        round(numerical_best["azimuth_deg"] / 5) * 5.0) % 360
    practical_energy = model.energy_kwh(
        practical_tilt, practical_azimuth)
    report["practical_recommendation"] = {
        "tilt_deg": practical_tilt,
        "azimuth_deg": practical_azimuth,
        "annual_ac_kwh": practical_energy,
        "average_daily_ac_kwh": practical_energy / 365,
        "specific_yield_kwh_per_kwp": (
            practical_energy / model.system.dc_capacity_kw),
        "retained_energy_percent": (
            100 * practical_energy / numerical_best["annual_ac_kwh"]),
        "loss_from_numerical_best_kwh": (
            numerical_best["annual_ac_kwh"] - practical_energy),
        "loss_from_numerical_best_percent": (
            100 * (
                numerical_best["annual_ac_kwh"] - practical_energy
            ) / numerical_best["annual_ac_kwh"]),
        "rounding_step_deg": 5,
        "note": (
            "Rounded installation setting derived from the same model. "
            "Confirm roof, shading and structural constraints on site."),
    }
    report['generated_at_utc'] = datetime.now(timezone.utc).isoformat()
    report['weather_source'] = provenance
    report['software'] = {'solarna': __version__, 'pvlib': pvlib.__version__}
    report['timing']['source'] = 'PVGIS inputs.location.irradiance_time_offset (hours)'
    if timing_sensitivity:
        zero_model = EnergyModel(weather, site, system, 0.0)
        zero_progress = None
        if progress_callback:
            zero_progress = lambda phase, done, total: progress_callback(
                "zero_offset_comparison", phase, done, total)
        zero_options = {}
        if zero_progress:
            zero_options["progress_callback"] = zero_progress
        if existing_orientation is not None:
            zero_options["required_orientations"] = (existing_orientation,)
        zero_report = optimize(
            zero_model, coarse_step, fine_step, **zero_options)
        best, zero_best = report['best'], zero_report['best']
        corrected_at_zero = model.energy_kwh(zero_best['tilt_deg'], zero_best['azimuth_deg'])
        zero_at_corrected = zero_model.energy_kwh(best['tilt_deg'], best['azimuth_deg'])
        report['timing_sensitivity'] = {
            'note': 'Same weather, system and search; geometry timing alone changes. '
                    'Not a PVGIS model benchmark, field validation, or uncertainty interval.',
            'zero_offset_best': zero_best,
            'zero_offset_30_degrees_south': zero_report['baselines']['30_degrees_south'],
            'corrected_model_at_zero_offset_optimum_kwh': corrected_at_zero,
            'zero_offset_model_at_corrected_optimum_kwh': zero_at_corrected,
            'best_energy_change_kwh': best['annual_ac_kwh'] - zero_best['annual_ac_kwh'],
            'tilt_change_deg': best['tilt_deg'] - zero_best['tilt_deg'],
            'azimuth_change_deg': (best['azimuth_deg'] - zero_best['azimuth_deg'] + 180) % 360 - 180,
        }
    if period_analysis:
        period_progress = None
        if progress_callback:
            period_progress = lambda phase, done, total: progress_callback(
                "period_analysis", phase, done, total)
        report["period_analysis"] = build_period_analysis(
            model, report, period_analysis, coarse_step, fine_step,
            progress_callback=period_progress,
            existing_orientation=existing_orientation,
            custom_months=period_months)
    if existing_orientation is not None:
        tilt, azimuth = existing_orientation
        annual_energy = model.energy_kwh(tilt, azimuth)
        best_energy = report["best"]["annual_ac_kwh"]
        report["existing_orientation"] = {
            "tilt_deg": tilt,
            "azimuth_deg": azimuth,
            "annual_ac_kwh": annual_energy,
            "average_daily_ac_kwh": annual_energy / 365,
            "specific_yield_kwh_per_kwp": (
                annual_energy / model.system.dc_capacity_kw),
            "gain_of_best_kwh": best_energy - annual_energy,
            "gain_of_best_percent": (
                100 * (best_energy / annual_energy - 1)
                if annual_energy > 0 else None),
            "note": "Same modeled weather and electrical assumptions; "
                    "not a measurement of the installed plant.",
        }
    return report


def write_report(report, path):
    """Do not truncate an existing report on serialization failure."""
    text = json.dumps(report, indent=2, default=str, allow_nan=False)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)
