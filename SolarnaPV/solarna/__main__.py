"""Command-line entry point; network access happens only when explicitly run."""

import argparse
from pathlib import Path
import sys

from .benchmark import compare_with_report, load_pvgis_benchmark
from .engine import SAPM_TEMPERATURE_MODELS, Site, System
from .history import build_historical_range
from .reporting import (
    build_report,
    normalize_existing_orientation,
    write_report,
)
from .weather import load_hourly_history, load_tmy


def main(argv=None):
    parser = argparse.ArgumentParser(description="Optimize fixed PV orientation using PVGIS weather (default: Sfax).")
    parser.add_argument("--latitude", type=float, default=34.7406)
    parser.add_argument("--longitude", type=float, default=10.7603)
    parser.add_argument("--name", default=None, help="Optional site label")
    parser.add_argument("--altitude-m", type=float, default=0, help="Site altitude; default 0 m is a placeholder")
    parser.add_argument("--capacity-kw", type=float, default=1)
    parser.add_argument("--albedo", type=float, default=0.2)
    parser.add_argument("--dc-ac-ratio", type=float, default=1.2)
    parser.add_argument("--gamma-pdc-percent-per-c", type=float, default=-0.4,
                        help="Module power temperature coefficient in percent per degree C")
    parser.add_argument("--inverter-efficiency-percent", type=float, default=96)
    parser.add_argument("--temperature-model", choices=SAPM_TEMPERATURE_MODELS,
                        default="open_rack_glass_glass",
                        help="SAPM module construction and mounting thermal preset")
    parser.add_argument("--other-dc-loss-fraction", type=float, default=0)
    parser.add_argument("--coarse-step", type=int, choices=[5, 10, 15, 30], default=5)
    parser.add_argument("--fine-step", type=float, choices=[0.5, 1.0], default=1)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/pvgis"))
    parser.add_argument("--refresh-weather", action="store_true")
    parser.add_argument("--timing-sensitivity", action="store_true",
                        help="Also optimize with zero offset on the same weather; not independent validation")
    parser.add_argument(
        "--period-analysis", choices=["winter", "summer"], default=None,
        help="Also optimize winter (Nov-Mar) or summer (Jun-Aug) electrical energy")
    parser.add_argument("--pvgis-benchmark", action="store_true",
                        help="Compare with PVGIS's independent optimized PV calculation")
    parser.add_argument(
        "--historical-range", action="store_true",
        help="Evaluate selected orientations across PVGIS historical years 2005-2023")
    parser.add_argument(
        "--existing-tilt", type=float, default=None,
        help="Optional installed-array tilt from horizontal in degrees")
    parser.add_argument(
        "--existing-azimuth", type=float, default=None,
        help="Optional installed-array azimuth clockwise from true north")
    parser.add_argument("--refresh-benchmark", action="store_true",
                        help="Refresh the optional PVGIS PVcalc benchmark cache")
    parser.add_argument("--refresh-history", action="store_true",
                        help="Refresh the optional PVGIS historical-series cache")
    parser.add_argument("--output", type=Path, default=Path("outputs/sfax.json"))
    args = parser.parse_args(argv)
    is_sfax = (args.latitude, args.longitude) == (34.7406, 10.7603)
    name = args.name or ("Sfax (approximate city centre)" if is_sfax else "Custom site")
    try:
        site = Site(args.latitude, args.longitude, args.altitude_m, name)
        system = System(
            dc_capacity_kw=args.capacity_kw,
            gamma_pdc_per_c=args.gamma_pdc_percent_per_c / 100,
            albedo=args.albedo,
            dc_ac_ratio=args.dc_ac_ratio,
            inverter_efficiency=args.inverter_efficiency_percent / 100,
            other_dc_loss_fraction=args.other_dc_loss_fraction,
            temperature_model=args.temperature_model,
        )
        if (args.existing_tilt is None) != (args.existing_azimuth is None):
            raise ValueError(
                "--existing-tilt and --existing-azimuth must be used together")
        existing_orientation = normalize_existing_orientation(
            None if args.existing_tilt is None
            else (args.existing_tilt, args.existing_azimuth))
        print(f"Acquiring PVGIS typical-year weather for {site.name}...", flush=True)
        weather, provenance = load_tmy(site, args.cache_dir, args.refresh_weather)
        print("Searching fixed orientations; this may take a few minutes...", flush=True)
        report = build_report(weather, provenance, site, system, args.coarse_step,
                              args.fine_step, args.timing_sensitivity,
                              args.period_analysis,
                              existing_orientation=existing_orientation)
        if args.historical_range:
            print(
                "Evaluating selected orientations across PVGIS historical years...",
                flush=True,
            )
            try:
                historical_weather, historical_provenance = load_hourly_history(
                    site, args.cache_dir, args.refresh_history)
                report["historical_range"] = build_historical_range(
                    historical_weather,
                    historical_provenance,
                    site,
                    system,
                    report,
                    existing_orientation,
                )
            except (OSError, ValueError, KeyError, TypeError) as exc:
                report["historical_range"] = {
                    "status": "unavailable",
                    "source": (
                        "European Commission JRC PVGIS historical hourly "
                        "radiation series"),
                    "error": f"{type(exc).__name__}: {exc}",
                    "note": "The core optimization completed, but the requested "
                            "historical range could not be calculated.",
                }
                print(
                    f"Historical range unavailable: {exc}. "
                    "The core report will still be saved.",
                    file=sys.stderr,
                )
        if args.pvgis_benchmark:
            print("Requesting independent PVGIS PVcalc benchmark...", flush=True)
            try:
                benchmark = load_pvgis_benchmark(
                    site, system, args.cache_dir, args.refresh_benchmark)
                report["pvgis_benchmark"] = compare_with_report(
                    report, benchmark)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                report["pvgis_benchmark"] = {
                    "status": "unavailable",
                    "source": "European Commission JRC PVGIS 5.3 PVcalc",
                    "error": f"{type(exc).__name__}: {exc}",
                    "note": "The Solarna optimization completed, but the requested "
                            "independent benchmark could not be retrieved or validated.",
                }
                print(
                    f"PVGIS benchmark unavailable: {exc}. "
                    "The core report will still be saved.",
                    file=sys.stderr,
                )
        write_report(report, args.output)
        print(f"Applied irradiance offset: {report['timing']['irradiance_time_offset_hours']:g} hours.")
        if args.timing_sensitivity:
            old = report['timing_sensitivity']['zero_offset_best']
            print(f"Same-weather zero-offset optimum: {old['tilt_deg']:g} tilt, "
                  f"{old['azimuth_deg']:g} azimuth, {old['annual_ac_kwh']:.1f} kWh. "
                  "Timing sensitivity only, not an independent benchmark.")
        if args.period_analysis:
            period = report["period_analysis"]
            best_period = period["best"]
            print(
                f"{period['label']} optimum: "
                f"{best_period['tilt_deg']:g} tilt, "
                f"{best_period['azimuth_deg']:g} azimuth, "
                f"{best_period['period_ac_kwh']:.1f} kWh in selected months.")
            print(
                "Gain during selected months versus the annual-optimum orientation: "
                f"{period['gain_over_annual_optimum_during_period_percent']:.2f}%; "
                f"annual-energy tradeoff {period['annual_energy_tradeoff_kwh']:+.1f} kWh.")
        if (args.pvgis_benchmark
                and report["pvgis_benchmark"]["status"] == "available"):
            comparison = report["pvgis_benchmark"]["comparison"]
            print(
                "PVGIS PVcalc optimum: "
                f"{comparison['pvgis_tilt_deg']:g} tilt, "
                f"{comparison['pvgis_azimuth_deg_true_north']:g} azimuth; "
                f"{comparison['pvgis_specific_yield_kwh_per_kwp']:.1f} kWh/kWp.")
            print(
                "Solarna minus PVGIS: "
                f"{comparison['tilt_delta_deg']:+g} degrees tilt, "
                f"{comparison['azimuth_delta_deg']:+g} degrees azimuth, "
                f"{comparison['specific_yield_delta_percent_of_pvgis']:+.2f}% yield. "
                "Independent-model comparison, not field validation.")
        if (args.historical_range
                and report["historical_range"]["status"] == "available"):
            history = report["historical_range"]
            optimum = history["orientations"]["tmy_optimum"]
            comparison = history["comparisons"][
                "tmy_optimum_minus_30_degrees_south"]
            print(
                f"Historical {history['start_year']}-{history['end_year']} "
                "modeled yield at the TMY optimum: "
                f"median {optimum['median_specific_yield_kwh_per_kwp']:.1f} "
                "kWh/kWp; "
                f"P10-P90 {optimum['p10_specific_yield_kwh_per_kwp']:.1f}-"
                f"{optimum['p90_specific_yield_kwh_per_kwp']:.1f} kWh/kWp.")
            print(
                "Median historical gain over 30 degrees south: "
                f"{comparison['median_gain_percent']:.3f}%. "
                "Historical model spread, not a confidence interval.")
        if "existing_orientation" in report:
            existing = report["existing_orientation"]
            print(
                "Existing orientation comparison: "
                f"{existing['tilt_deg']:g} tilt, "
                f"{existing['azimuth_deg']:g} azimuth, "
                f"{existing['annual_ac_kwh']:.1f} kWh/year; "
                f"modeled optimum gain {existing['gain_of_best_kwh']:.1f} kWh/year.")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Unable to produce a report: {exc}", file=sys.stderr)
        return 1
    best = report["best"]
    print(f"Best sampled orientation: tilt {best['tilt_deg']:.1f} degrees, "
          f"azimuth {best['azimuth_deg']:.1f} degrees (true north convention).")
    print(f"Modeled annual AC yield: {best['annual_ac_kwh']:.1f} kWh "
          f"for {system.dc_capacity_kw:g} kWp DC.")
    gain = report["baselines"]["30_degrees_south"]["gain_of_best_percent"]
    print("Gain versus 30 degrees south: " + (f"{gain:.2f}%" if gain is not None else "undefined (zero baseline)"))
    print(f"Report: {args.output}. Model estimate, not a field-validated installation recommendation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
