"""Repeatable multi-site validation against PVGIS PVcalc."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import math
from pathlib import Path
from statistics import mean, median
import sys
import time

from . import __version__
from .batch import read_sites
from .benchmark import compare_with_report, load_pvgis_benchmark
from .engine import SAPM_TEMPERATURE_MODELS, System
from .reporting import build_report, write_report
from .weather import load_tmy, pvgis_elevation_m


def _system_payload(system: System) -> dict:
    return {
        "dc_capacity_kw": system.dc_capacity_kw,
        "dc_ac_ratio": system.dc_ac_ratio,
        "inverter_ac_rating_kw": system.dc_capacity_kw / system.dc_ac_ratio,
        "gamma_pdc_percent_per_c": system.gamma_pdc_per_c * 100,
        "inverter_efficiency_percent": system.inverter_efficiency * 100,
        "other_dc_loss_percent": system.other_dc_loss_fraction * 100,
        "albedo": system.albedo,
        "temperature_model": system.temperature_model,
    }


def _site_result(key: str, site, report: dict, report_path: Path) -> dict:
    comparison = report["pvgis_benchmark"]["comparison"]
    pvgis = report["pvgis_benchmark"]["pvgis_result"]
    return {
        "id": key,
        "name": site.name,
        "latitude": site.latitude,
        "longitude": site.longitude,
        "report_path": str(report_path),
        "weather_cache_hit": bool(report["weather_source"].get("cache_hit")),
        "solarna": {
            "tilt_deg": report["best"]["tilt_deg"],
            "azimuth_deg_true_north": report["best"]["azimuth_deg"],
            "annual_ac_kwh": report["best"]["annual_ac_kwh"],
            "specific_yield_kwh_per_kwp": (
                report["best"]["specific_yield_kwh_per_kwp"]),
        },
        "pvgis": {
            "tilt_deg": pvgis["tilt_deg"],
            "azimuth_deg_true_north": pvgis["azimuth_deg_true_north"],
            "specific_yield_kwh_per_kwp": pvgis["annual_ac_kwh_per_kwp"],
            "interannual_sd_kwh_per_kwp": pvgis[
                "interannual_sd_kwh_per_kwp"],
            "interannual_sd_percent": pvgis["interannual_sd_percent"],
        },
        "comparison": comparison,
    }


def _aggregate(results: list[dict]) -> dict | None:
    if not results:
        return None
    comparisons = [item["comparison"] for item in results]
    tilt = [abs(item["tilt_delta_deg"]) for item in comparisons]
    azimuth = [abs(item["azimuth_delta_deg"]) for item in comparisons]
    yield_delta = [
        item["specific_yield_delta_percent_of_pvgis"]
        for item in comparisons
    ]
    monthly_mae = [
        item["monthly_mae_kwh_per_kwp"] for item in comparisons
    ]
    monthly_rmse = [
        item["monthly_rmse_kwh_per_kwp"] for item in comparisons
    ]
    return {
        "site_count": len(results),
        "mean_absolute_tilt_delta_deg": mean(tilt),
        "maximum_absolute_tilt_delta_deg": max(tilt),
        "mean_absolute_azimuth_delta_deg": mean(azimuth),
        "maximum_absolute_azimuth_delta_deg": max(azimuth),
        "mean_specific_yield_delta_percent_of_pvgis": mean(yield_delta),
        "median_specific_yield_delta_percent_of_pvgis": median(yield_delta),
        "mean_absolute_specific_yield_delta_percent_of_pvgis": mean(
            abs(value) for value in yield_delta),
        "maximum_absolute_specific_yield_delta_percent_of_pvgis": max(
            abs(value) for value in yield_delta),
        "minimum_specific_yield_delta_percent_of_pvgis": min(yield_delta),
        "maximum_specific_yield_delta_percent_of_pvgis": max(yield_delta),
        "mean_monthly_mae_kwh_per_kwp": mean(monthly_mae),
        "mean_monthly_rmse_kwh_per_kwp": mean(monthly_rmse),
    }


def build_summary(sites_path: Path, system: System, coarse_step: int,
                  fine_step: float, results: list[dict],
                  failures: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "software": {"solarna": __version__},
        "sites_source": str(Path(sites_path)),
        "method": (
            "Solarna PVGIS-TMY optimization compared with the independent "
            "PVGIS 5.3 PVcalc optimized fixed-system result."
        ),
        "system": _system_payload(system),
        "search": {
            "coarse_step_deg": coarse_step,
            "fine_step_deg": fine_step,
        },
        "totals": {
            "requested": len(results) + len(failures),
            "succeeded": len(results),
            "failed": len(failures),
        },
        "aggregate": _aggregate(results),
        "sites": results,
        "failures": failures,
        "limitations": [
            "This is an independent-model comparison, not field validation.",
            "PVGIS PVcalc does not expose Solarna's DC/AC ratio or identical clipping behavior.",
            "PVGIS PVcalc uses a multi-year calculation; Solarna uses a typical meteorological year.",
            "The sites represent point locations and do not include roof shading, obstacles, soiling, or measured plant downtime.",
        ],
    }


def _retry_provider_call(operation, retries: int, delay_seconds: float):
    for attempt in range(retries + 1):
        try:
            return operation()
        except OSError:
            if attempt >= retries:
                raise
            time.sleep(delay_seconds)


def run_validation(sites, sites_path: Path, reports_dir: Path,
                   summary_path: Path, cache_dir: Path, system: System,
                   pause_seconds: float = 1.0, coarse_step: int = 10,
                   fine_step: float = 1.0, refresh_weather: bool = False,
                   refresh_benchmark: bool = False,
                   provider_retries: int = 2):
    if not math.isfinite(pause_seconds) or pause_seconds < 1:
        raise ValueError("Pause must be at least one second")
    if coarse_step not in (5, 10, 15, 30):
        raise ValueError("Coarse step must be 5, 10, 15, or 30 degrees")
    if fine_step not in (0.5, 1, 1.0):
        raise ValueError("Fine step must be 0.5 or 1 degree")
    if (isinstance(provider_retries, bool)
            or not isinstance(provider_retries, int)
            or not 0 <= provider_retries <= 5):
        raise ValueError("Provider retries must be an integer from 0 to 5")

    reports_dir = Path(reports_dir)
    results = []
    failures = []
    for index, (key, site) in enumerate(sites):
        if index:
            time.sleep(pause_seconds)
        print(f"[{index + 1}/{len(sites)}] {site.name}", flush=True)
        try:
            weather, provenance = _retry_provider_call(
                lambda: load_tmy(site, cache_dir, refresh_weather),
                provider_retries, pause_seconds)
            effective_site = replace(
                site, altitude_m=pvgis_elevation_m(provenance))
            report = build_report(
                weather, provenance, effective_site, system,
                coarse_step, fine_step)
            report["site_elevation"] = {
                "altitude_m": effective_site.altitude_m,
                "source": "PVGIS terrain model",
            }
            benchmark = _retry_provider_call(
                lambda: load_pvgis_benchmark(
                    effective_site, system, cache_dir, refresh_benchmark),
                provider_retries, pause_seconds)
            report["pvgis_benchmark"] = compare_with_report(
                report, benchmark)
            report_path = reports_dir / f"site-{key}.json"
            write_report(report, report_path)
            results.append(_site_result(
                key, effective_site, report, report_path))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            failures.append({
                "id": key,
                "name": site.name,
                "error": f"{type(exc).__name__}: {exc}",
            })
            print(f"FAILED {key}: {exc}", file=sys.stderr)

    summary = build_summary(
        sites_path, system, coarse_step, fine_step, results, failures)
    write_report(summary, summary_path)
    return failures, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", required=True, type=Path)
    parser.add_argument(
        "--reports-dir", type=Path,
        default=Path("outputs/validation/reports"))
    parser.add_argument(
        "--summary", type=Path,
        default=Path("outputs/validation/tunisia-summary.json"))
    parser.add_argument(
        "--cache-dir", type=Path, default=Path(".cache/pvgis"))
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument(
        "--coarse-step", type=int, choices=[5, 10, 15, 30], default=10)
    parser.add_argument(
        "--fine-step", type=float, choices=[0.5, 1.0], default=1.0)
    parser.add_argument("--capacity-kw", type=float, default=4.5)
    parser.add_argument("--dc-ac-ratio", type=float, default=1.125)
    parser.add_argument(
        "--gamma-pdc-percent-per-c", type=float, default=-0.4)
    parser.add_argument(
        "--inverter-efficiency-percent", type=float, default=97.2)
    parser.add_argument("--other-dc-loss-percent", type=float, default=0)
    parser.add_argument("--albedo", type=float, default=0.2)
    parser.add_argument(
        "--temperature-model", choices=SAPM_TEMPERATURE_MODELS,
        default="open_rack_glass_glass")
    parser.add_argument("--refresh-weather", action="store_true")
    parser.add_argument("--refresh-benchmark", action="store_true")
    parser.add_argument(
        "--provider-retries", type=int, choices=range(0, 6), default=2)
    args = parser.parse_args(argv)

    try:
        sites = read_sites(args.sites)
        system = System(
            dc_capacity_kw=args.capacity_kw,
            gamma_pdc_per_c=args.gamma_pdc_percent_per_c / 100,
            dc_ac_ratio=args.dc_ac_ratio,
            inverter_efficiency=args.inverter_efficiency_percent / 100,
            albedo=args.albedo,
            other_dc_loss_fraction=args.other_dc_loss_percent / 100,
            temperature_model=args.temperature_model,
        )
        failures, summary = run_validation(
            sites, args.sites, args.reports_dir, args.summary,
            args.cache_dir, system, args.pause_seconds, args.coarse_step,
            args.fine_step, args.refresh_weather, args.refresh_benchmark,
            args.provider_retries)
    except (OSError, ValueError, TypeError) as exc:
        print(f"Validation rejected: {exc}", file=sys.stderr)
        return 1

    aggregate = summary["aggregate"]
    print(
        f"Validation finished: {summary['totals']['succeeded']} succeeded, "
        f"{summary['totals']['failed']} failed.")
    if aggregate:
        print(
            "Mean absolute yield difference versus PVGIS: "
            f"{aggregate['mean_absolute_specific_yield_delta_percent_of_pvgis']:.2f}%; "
            "maximum absolute difference: "
            f"{aggregate['maximum_absolute_specific_yield_delta_percent_of_pvgis']:.2f}%.")
    print(f"Summary: {args.summary}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
