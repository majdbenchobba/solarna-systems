"""Independent PVGIS PVcalc benchmark with a provenance-bearing local cache."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .engine import Site, System


PVGIS_PVCALC_URL = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
RADIATION_DATABASE = "PVGIS-SARAH3"
PV_TECHNOLOGY = "crystSi"
MOUNTING_PLACE = "free"


def _number(value, label: str, minimum: float | None = None) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or (minimum is not None and value < minimum)):
        raise ValueError(f"PVGIS benchmark returned an invalid {label}")
    return float(value)


def _provider_optional_number(value, label: str) -> float:
    """Normalize optional PVGIS diagnostics that may be JSON numbers or strings."""
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError as exc:
            raise ValueError(
                f"PVGIS benchmark returned an invalid {label}") from exc
    return _number(value, label)


def pvgis_aspect_to_true_north(aspect_deg: float) -> float:
    """Convert PVGIS aspect (south=0, west positive) to north-clockwise azimuth."""
    aspect = _number(aspect_deg, "aspect")
    if not -180 <= aspect <= 180:
        raise ValueError("PVGIS benchmark aspect must be between -180 and 180 degrees")
    return (180.0 + aspect) % 360


def signed_angle_delta(first_deg: float, second_deg: float) -> float:
    """Return first - second wrapped to [-180, 180)."""
    return (float(first_deg) - float(second_deg) + 180) % 360 - 180


def approximate_pvgis_system_loss_percent(system: System) -> float:
    """Map Solarna's inverter and lumped DC loss to PVGIS's one loss input."""
    retained = system.inverter_efficiency * (1 - system.other_dc_loss_fraction)
    return 100 * (1 - retained)


def _identity(site: Site, system: System) -> dict:
    return {
        "schema_version": 1,
        "endpoint": PVGIS_PVCALC_URL,
        "latitude": site.latitude,
        "longitude": site.longitude,
        "peak_power_kwp": 1.0,
        "system_loss_percent": approximate_pvgis_system_loss_percent(system),
        "pv_technology": PV_TECHNOLOGY,
        "mounting_place": MOUNTING_PLACE,
        "radiation_database": RADIATION_DATABASE,
        "use_horizon": True,
        "optimize_inclination_and_orientation": True,
    }


def _request_url(identity: dict) -> str:
    parameters = {
        "lat": identity["latitude"],
        "lon": identity["longitude"],
        "peakpower": identity["peak_power_kwp"],
        "loss": round(identity["system_loss_percent"], 8),
        "pvtechchoice": identity["pv_technology"],
        "mountingplace": identity["mounting_place"],
        "raddatabase": identity["radiation_database"],
        "usehorizon": 1,
        "optimalangles": 1,
        "outputformat": "json",
    }
    return f"{identity['endpoint']}?{urlencode(parameters)}"


def _parse_payload(payload: dict, identity: dict, retrieved_at_utc: str,
                   cache_hit: bool) -> dict:
    try:
        fixed_input = payload["inputs"]["mounting_system"]["fixed"]
        fixed_total = payload["outputs"]["totals"]["fixed"]
        monthly_rows = payload["outputs"]["monthly"]["fixed"]
    except (KeyError, TypeError) as exc:
        raise ValueError("PVGIS benchmark response is missing required PVcalc fields") from exc

    try:
        tilt = _number(fixed_input["slope"]["value"], "optimal inclination")
        aspect = _number(fixed_input["azimuth"]["value"], "optimal aspect")
        annual_yield = _number(fixed_total["E_y"], "annual energy", 0)
        annual_poa = _number(
            fixed_total["H(i)_y"], "annual plane-of-array irradiation", 0)
        interannual_sd = _number(
            fixed_total["SD_y"], "interannual standard deviation", 0)
    except (KeyError, TypeError) as exc:
        raise ValueError("PVGIS benchmark response is missing numeric PVcalc fields") from exc
    if not 0 <= tilt <= 90:
        raise ValueError("PVGIS benchmark inclination is outside 0..90 degrees")
    azimuth = pvgis_aspect_to_true_north(aspect)
    if annual_yield <= 0 or annual_poa <= 0:
        raise ValueError("PVGIS benchmark returned no annual production")

    monthly = {}
    if not isinstance(monthly_rows, list):
        raise ValueError("PVGIS benchmark monthly output is not a list")
    for row in monthly_rows:
        try:
            month = int(row["month"])
            energy = _number(row["E_m"], f"month {month} energy", 0)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("PVGIS benchmark contains invalid monthly output") from exc
        if month in monthly or not 1 <= month <= 12:
            raise ValueError("PVGIS benchmark months must be unique values from 1 to 12")
        monthly[month] = energy
    if set(monthly) != set(range(1, 13)):
        raise ValueError("PVGIS benchmark must contain all 12 months")

    location = payload.get("inputs", {}).get("location", {})
    meteo = payload.get("inputs", {}).get("meteo_data", {})
    losses = {
        key: _provider_optional_number(value, key)
        for key, value in fixed_total.items()
        if isinstance(key, str) and key.startswith("l_")
    }
    return {
        "status": "available",
        "source": "European Commission JRC PVGIS 5.3 PVcalc",
        "method": "Independent PVGIS multi-year grid-connected PV calculation with optimized fixed angles",
        "retrieved_at_utc": retrieved_at_utc,
        "cache_hit": cache_hit,
        "request": {
            "endpoint": identity["endpoint"],
            "peak_power_kwp": identity["peak_power_kwp"],
            "system_loss_percent": identity["system_loss_percent"],
            "system_loss_mapping": "100 × [1 − inverter efficiency × (1 − other DC loss)]",
            "pv_technology": identity["pv_technology"],
            "mounting_place": identity["mounting_place"],
            "radiation_database": identity["radiation_database"],
            "use_horizon": identity["use_horizon"],
            "optimalangles": identity["optimize_inclination_and_orientation"],
        },
        "provider_context": {
            "elevation_m": location.get("elevation"),
            "radiation_database": meteo.get("radiation_db"),
            "start_year": meteo.get("year_min"),
            "end_year": meteo.get("year_max"),
        },
        "pvgis_result": {
            "tilt_deg": tilt,
            "aspect_deg_south_convention": aspect,
            "azimuth_deg_true_north": azimuth,
            "annual_ac_kwh_per_kwp": annual_yield,
            "annual_poa_kwh_m2": annual_poa,
            "interannual_sd_kwh_per_kwp": interannual_sd,
            "interannual_sd_percent": 100 * interannual_sd / annual_yield,
            "monthly_ac_kwh_per_kwp": {
                str(month): monthly[month] for month in sorted(monthly)
            },
            "provider_loss_breakdown_percent": losses,
        },
        "limitations": [
            "This is an independent model benchmark, not field validation.",
            "Solarna uses a PVGIS TMY assembled from representative months; PVcalc uses a multi-year calculation.",
            "PVGIS PVcalc does not expose Solarna's DC/AC ratio or identical inverter clipping behavior.",
            "The single PVGIS system-loss input only approximates Solarna's inverter and additional DC losses.",
            "PVGIS selects its own grid elevation; Solarna uses the user-entered altitude.",
            "PVGIS and Solarna use different transposition, optical, thermal, low-light, and electrical implementations.",
        ],
    }


def load_pvgis_benchmark(site: Site, system: System, cache_dir: Path,
                         refresh: bool = False, timeout: float = 60) -> dict:
    """Fetch or load a normalized 1 kWp PVGIS PVcalc optimum and production result."""
    identity = _identity(site, system)
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    path = Path(cache_dir) / f"pvcalc-{digest}.json"
    if path.exists() and not refresh:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("identity") != identity:
            raise ValueError("PVGIS benchmark cache provenance does not match the request")
        return _parse_payload(
            cached["response"], identity, cached["retrieved_at_utc"], True)

    request = Request(
        _request_url(identity),
        headers={"User-Agent": "SolarnaPV/0.2 local-research-application"},
    )
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise OSError(f"PVGIS benchmark returned HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    retrieved_at = datetime.now(timezone.utc).isoformat()
    parsed = _parse_payload(payload, identity, retrieved_at, False)
    cache_payload = {
        "identity": identity,
        "retrieved_at_utc": retrieved_at,
        "response": payload,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(cache_payload, allow_nan=False), encoding="utf-8")
    temporary.replace(path)
    return parsed


def compare_with_report(report: dict, benchmark: dict) -> dict:
    """Attach angle, annual-yield, and monthly-error comparisons to a benchmark."""
    if benchmark.get("status") != "available":
        raise ValueError("Only an available PVGIS benchmark can be compared")
    try:
        best = report["best"]
        capacity = _number(report["system"]["dc_capacity_kw"], "report capacity", 0)
        pvgis = benchmark["pvgis_result"]
        pvgis_yield = _number(
            pvgis["annual_ac_kwh_per_kwp"], "PVGIS annual energy", 0)
        solarna_yield = _number(
            best["specific_yield_kwh_per_kwp"], "Solarna specific yield", 0)
        solarna_monthly = best["monthly_ac_kwh"]
        pvgis_monthly = pvgis["monthly_ac_kwh_per_kwp"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Report or benchmark is missing comparison fields") from exc
    if capacity <= 0 or pvgis_yield <= 0:
        raise ValueError("Comparison yields and capacity must be positive")

    monthly_errors = []
    for month in range(1, 13):
        try:
            modeled = _number(
                solarna_monthly[str(month)], f"Solarna month {month}", 0) / capacity
            reference = _number(
                pvgis_monthly[str(month)], f"PVGIS month {month}", 0)
        except KeyError as exc:
            raise ValueError("Comparison requires all 12 monthly values") from exc
        monthly_errors.append(modeled - reference)

    mae = sum(abs(error) for error in monthly_errors) / 12
    rmse = math.sqrt(sum(error ** 2 for error in monthly_errors) / 12)
    comparison = {
        "solarna_tilt_deg": float(best["tilt_deg"]),
        "pvgis_tilt_deg": float(pvgis["tilt_deg"]),
        "tilt_delta_deg": float(best["tilt_deg"]) - float(pvgis["tilt_deg"]),
        "solarna_azimuth_deg_true_north": float(best["azimuth_deg"]),
        "pvgis_azimuth_deg_true_north": float(pvgis["azimuth_deg_true_north"]),
        "azimuth_delta_deg": signed_angle_delta(
            best["azimuth_deg"], pvgis["azimuth_deg_true_north"]),
        "solarna_specific_yield_kwh_per_kwp": solarna_yield,
        "pvgis_specific_yield_kwh_per_kwp": pvgis_yield,
        "specific_yield_delta_kwh_per_kwp": solarna_yield - pvgis_yield,
        "specific_yield_delta_percent_of_pvgis": 100 * (solarna_yield / pvgis_yield - 1),
        "monthly_mae_kwh_per_kwp": mae,
        "monthly_rmse_kwh_per_kwp": rmse,
    }
    return {**benchmark, "comparison": comparison}
