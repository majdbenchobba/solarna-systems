"""Historical-year robustness checks for selected fixed orientations."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .engine import EnergyModel, Site, System
from .weather import validate_historical_weather


def _orientation(tilt, azimuth):
    values = (tilt, azimuth)
    if (any(isinstance(value, bool) for value in values)
            or not all(isinstance(value, (int, float)) for value in values)
            or not all(math.isfinite(value) for value in values)
            or not 0 <= tilt <= 90 or not 0 <= azimuth <= 360):
        raise ValueError("Historical orientation is outside the supported range")
    return float(tilt), float(azimuth % 360)


def _annual_energy(model: EnergyModel, tilt: float, azimuth: float):
    power = model.simulate(tilt, azimuth)["ac_w"]
    annual = power.groupby(power.index.year).sum() / 1000
    if (annual.empty or not np.isfinite(annual.to_numpy()).all()
            or (annual <= 0).any()):
        raise ValueError("Historical annual energy must be finite and positive")
    return annual.astype(float)


def _summary(annual: pd.Series, capacity_kw: float):
    values = annual.to_numpy(dtype=float)
    specific = values / capacity_kw
    mean = float(np.mean(values))
    standard_deviation = float(np.std(values, ddof=0))
    return {
        "annual_ac_kwh_by_year": {
            str(int(year)): float(value)
            for year, value in annual.items()
        },
        "annual_specific_yield_kwh_per_kwp_by_year": {
            str(int(year)): float(value / capacity_kw)
            for year, value in annual.items()
        },
        "minimum_ac_kwh": float(np.min(values)),
        "p10_ac_kwh": float(np.quantile(values, 0.10)),
        "median_ac_kwh": float(np.median(values)),
        "mean_ac_kwh": mean,
        "p90_ac_kwh": float(np.quantile(values, 0.90)),
        "maximum_ac_kwh": float(np.max(values)),
        "standard_deviation_ac_kwh": standard_deviation,
        "coefficient_of_variation_percent": (
            100 * standard_deviation / mean),
        "minimum_specific_yield_kwh_per_kwp": float(np.min(specific)),
        "p10_specific_yield_kwh_per_kwp": float(np.quantile(specific, 0.10)),
        "median_specific_yield_kwh_per_kwp": float(np.median(specific)),
        "p90_specific_yield_kwh_per_kwp": float(np.quantile(specific, 0.90)),
        "maximum_specific_yield_kwh_per_kwp": float(np.max(specific)),
    }


def _comparison(reference: pd.Series, comparison: pd.Series):
    if not reference.index.equals(comparison.index):
        raise ValueError("Historical comparison years do not match")
    delta = reference - comparison
    percent = delta / comparison * 100
    return {
        "annual_gain_kwh_by_year": {
            str(int(year)): float(value)
            for year, value in delta.items()
        },
        "annual_gain_percent_by_year": {
            str(int(year)): float(value)
            for year, value in percent.items()
        },
        "minimum_gain_kwh": float(delta.min()),
        "median_gain_kwh": float(delta.median()),
        "maximum_gain_kwh": float(delta.max()),
        "minimum_gain_percent": float(percent.min()),
        "median_gain_percent": float(percent.median()),
        "maximum_gain_percent": float(percent.max()),
        "years_reference_higher": int((delta > 0).sum()),
        "years_equal": int(np.isclose(delta.to_numpy(), 0, atol=1e-9).sum()),
        "year_count": int(len(delta)),
    }


def build_historical_range(
        weather: pd.DataFrame,
        provenance: dict,
        site: Site,
        system: System,
        report: dict,
        existing_orientation=None,
        progress_callback=None):
    """Evaluate selected orientations across complete historical calendar years.

    This deliberately does not re-optimize each year. It tests whether the TMY
    recommendation and its practical comparisons remain useful across the
    available historical weather series.
    """
    start_year = int(provenance["start_year"])
    end_year = int(provenance["end_year"])
    validate_historical_weather(weather, start_year, end_year)
    best = report["best"]
    baseline = report["baselines"]["30_degrees_south"]
    orientations = [
        ("tmy_optimum", *_orientation(best["tilt_deg"], best["azimuth_deg"])),
        ("30_degrees_south",
         *_orientation(baseline["tilt_deg"], baseline["azimuth_deg"])),
    ]
    if existing_orientation is not None:
        orientations.append(
            ("existing_installation", *_orientation(*existing_orientation)))

    model = EnergyModel(weather, site, system, 0.0)
    results = {}
    series = {}
    total = len(orientations)
    if progress_callback:
        progress_callback(0, total)
    for index, (key, tilt, azimuth) in enumerate(orientations, start=1):
        annual = _annual_energy(model, tilt, azimuth)
        series[key] = annual
        results[key] = {
            "tilt_deg": tilt,
            "azimuth_deg": azimuth,
            **_summary(annual, system.dc_capacity_kw),
        }
        if progress_callback:
            progress_callback(index, total)

    comparisons = {
        "tmy_optimum_minus_30_degrees_south": _comparison(
            series["tmy_optimum"], series["30_degrees_south"]),
    }
    if "existing_installation" in series:
        comparisons["tmy_optimum_minus_existing_installation"] = _comparison(
            series["tmy_optimum"], series["existing_installation"])

    return {
        "status": "available",
        "source": provenance["source"],
        "start_year": start_year,
        "end_year": end_year,
        "year_count": end_year - start_year + 1,
        "timestamp_minute_utc": provenance["timestamp_minute_utc"],
        "orientations": results,
        "comparisons": comparisons,
        "weather_source": provenance,
        "method": (
            "Apply the same Solarna optical, thermal and electrical model to "
            "each complete PVGIS historical calendar year at the selected "
            "orientations. No yearly angle re-optimization is performed."),
        "limitations": [
            "Historical modeled weather is not measured PV production.",
            "P10-P90 describes the sampled historical years, not a confidence interval.",
            "This checks yield and comparison robustness at selected orientations; "
            "it does not estimate how the optimum angle moves year to year.",
            "Equipment, shading, soiling and downtime assumptions remain unchanged.",
        ],
    }
