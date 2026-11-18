"""PVGIS typical-year acquisition with a provenance-bearing local cache."""

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib

from .engine import Site, validate_weather

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/"
COLUMNS = ["ghi", "dni", "dhi", "temp_air", "wind_speed"]
MIN_REPAIRABLE_WIND_SPEED_M_S = -1.0
HISTORICAL_START_YEAR = 2005
HISTORICAL_END_YEAR = 2023


def pvgis_elevation_m(provenance: dict) -> float:
    """Return the validated PVGIS terrain elevation for a weather response."""
    try:
        value = provenance["provider_metadata"]["inputs"]["location"]["elevation"]
    except (KeyError, TypeError) as exc:
        raise ValueError("PVGIS terrain elevation is missing") from exc
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not -500 <= value <= 9000):
        raise ValueError("PVGIS terrain elevation is invalid")
    return float(value)


def normalize_pvgis_weather(weather: pd.DataFrame):
    """Repair bounded provider interpolation artifacts and report every change."""
    normalized = weather.copy()
    negative = normalized["wind_speed"] < 0
    count = int(negative.sum())
    if not count:
        return normalized, []
    minimum = float(normalized.loc[negative, "wind_speed"].min())
    if minimum < MIN_REPAIRABLE_WIND_SPEED_M_S:
        raise ValueError(
            "PVGIS wind speed is below the bounded repair limit "
            f"({MIN_REPAIRABLE_WIND_SPEED_M_S:g} m/s)")
    normalized.loc[negative, "wind_speed"] = 0.0
    return normalized, [{
        "field": "wind_speed",
        "operation": "clip_negative_values_to_zero",
        "count": count,
        "minimum_original_m_s": minimum,
        "repair_limit_m_s": MIN_REPAIRABLE_WIND_SPEED_M_S,
        "reason": "Wind speed is a nonnegative physical magnitude.",
    }]


def load_tmy(site: Site, cache_dir: Path, refresh: bool = False):
    """Return hourly UTC weather and provenance; never fall back to synthetic data.

    PVGIS's far-horizon correction is requested once during acquisition. Nearby
    obstacles are not represented. The TMY is assigned to non-leap year 1990
    so solar geometry and hourly integration use one continuous calendar.
    """
    identity = {
        "schema_version": 2,
        "latitude": site.latitude,
        "longitude": site.longitude,
        "url": PVGIS_URL,
        "usehorizon": True,
        "coerce_year": 1990,
        "pvlib_version": pvlib.__version__,
    }
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    path = Path(cache_dir) / f"tmy-{key}.json"
    if path.exists() and not refresh:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["identity"] != identity:
            raise ValueError("Weather cache provenance does not match the requested site")
        table = payload["weather"]
        weather = pd.DataFrame(table["data"], columns=table["columns"],
                               index=pd.to_datetime(table["index"], utc=True))
        validate_weather(weather, require_year=True)
        return weather, {**payload["provenance"], "cache_hit": True}

    response = pvlib.iotools.get_pvgis_tmy(
        site.latitude, site.longitude, outputformat="json", usehorizon=True,
        map_variables=True, url=PVGIS_URL, timeout=60, coerce_year=1990,
    )
    weather = response[0][COLUMNS].copy()
    weather.index = weather.index.tz_convert("UTC")
    weather, adjustments = normalize_pvgis_weather(weather)
    validate_weather(weather, require_year=True)
    provenance = {
        **identity,
        "source": "European Commission JRC PVGIS typical meteorological year",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider_metadata": response[-1],
        "weather_adjustments": adjustments,
        "note": "Typical year, not a forecast or a measured production year. "
                "See provider metadata for source years and irradiance timestamp offsets.",
    }
    payload = {
        "identity": identity,
        "provenance": provenance,
        "weather": {
            "index": [stamp.isoformat() for stamp in weather.index],
            "columns": list(weather.columns),
            "data": weather.to_numpy().tolist(),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, default=str, allow_nan=False), encoding="utf-8")
    temporary.replace(path)
    return weather, {**provenance, "cache_hit": False}


def validate_historical_weather(
        weather: pd.DataFrame,
        start_year: int = HISTORICAL_START_YEAR,
        end_year: int = HISTORICAL_END_YEAR):
    """Require complete, contiguous UTC calendar years at one hourly minute."""
    validate_weather(weather)
    if (isinstance(start_year, bool) or isinstance(end_year, bool)
            or not isinstance(start_year, int) or not isinstance(end_year, int)
            or start_year > end_year):
        raise ValueError("Historical start/end years must be ordered integers")
    expected_years = list(range(start_year, end_year + 1))
    actual_years = sorted(int(year) for year in weather.index.year.unique())
    if actual_years != expected_years:
        raise ValueError("Historical weather does not contain the requested years")
    minute_values = weather.index.minute.unique()
    if (len(minute_values) != 1 or (weather.index.second != 0).any()
            or (weather.index.microsecond != 0).any()):
        raise ValueError(
            "Historical weather must use one consistent hourly UTC minute")
    for year in expected_years:
        yearly = weather.loc[weather.index.year == year]
        expected_hours = 8784 if pd.Timestamp(year, 1, 1).is_leap_year else 8760
        first, last = yearly.index[0], yearly.index[-1]
        if (len(yearly) != expected_hours
                or (first.month, first.day, first.hour) != (1, 1, 0)
                or (last.month, last.day, last.hour) != (12, 31, 23)):
            raise ValueError(
                f"Historical weather year {year} is not a complete calendar year")


def pvgis_hourly_to_weather(hourly: pd.DataFrame):
    """Convert a horizontal PVGIS hourly series to GHI/DNI/DHI weather."""
    required = {
        "poa_direct",
        "poa_sky_diffuse",
        "poa_ground_diffuse",
        "solar_elevation",
        "temp_air",
        "wind_speed",
    }
    if not required.issubset(hourly.columns):
        raise ValueError(
            "PVGIS historical response is missing required hourly components")
    numeric = hourly[list(required)].astype(float)
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("PVGIS historical response contains non-finite values")
    if (numeric[[
            "poa_direct", "poa_sky_diffuse", "poa_ground_diffuse"]] < 0).any().any():
        raise ValueError("PVGIS historical irradiance cannot be negative")
    if float(numeric["poa_ground_diffuse"].max()) > 1e-6:
        raise ValueError(
            "PVGIS horizontal-plane history unexpectedly contains ground reflection")

    elevation_sine = np.sin(
        np.radians(numeric["solar_elevation"].to_numpy()))
    direct_horizontal = numeric["poa_direct"].to_numpy()
    invalid_direct = (direct_horizontal > 0) & (elevation_sine <= 0)
    if invalid_direct.any():
        raise ValueError(
            "PVGIS reports direct horizontal irradiance without positive sun height")
    dni = np.divide(
        direct_horizontal,
        elevation_sine,
        out=np.zeros_like(direct_horizontal),
        where=elevation_sine > 0,
    )
    weather = pd.DataFrame({
        "ghi": (
            numeric["poa_direct"]
            + numeric["poa_sky_diffuse"]
            + numeric["poa_ground_diffuse"]
        ),
        "dni": dni,
        "dhi": numeric["poa_sky_diffuse"] + numeric["poa_ground_diffuse"],
        "temp_air": numeric["temp_air"],
        "wind_speed": numeric["wind_speed"],
    }, index=hourly.index)
    weather, adjustments = normalize_pvgis_weather(weather)
    validate_weather(weather)
    return weather, adjustments


def load_hourly_history(
        site: Site,
        cache_dir: Path,
        refresh: bool = False,
        start_year: int = HISTORICAL_START_YEAR,
        end_year: int = HISTORICAL_END_YEAR):
    """Return complete PVGIS historical hourly weather and provenance."""
    if (isinstance(start_year, bool) or isinstance(end_year, bool)
            or not isinstance(start_year, int) or not isinstance(end_year, int)
            or start_year > end_year):
        raise ValueError("Historical start/end years must be ordered integers")
    identity = {
        "schema_version": 1,
        "latitude": site.latitude,
        "longitude": site.longitude,
        "url": PVGIS_URL,
        "usehorizon": True,
        "radiation_database": "PVGIS-SARAH3",
        "start_year": start_year,
        "end_year": end_year,
        "surface_tilt_deg": 0,
        "surface_azimuth_deg_true_north": 180,
        "pvlib_version": pvlib.__version__,
    }
    key = hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    path = Path(cache_dir) / f"hourly-history-{key}.json"
    if path.exists() and not refresh:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["identity"] != identity:
            raise ValueError(
                "Historical weather cache provenance does not match the request")
        table = payload["weather"]
        weather = pd.DataFrame(
            table["data"],
            columns=table["columns"],
            index=pd.to_datetime(table["index"], utc=True),
        )
        validate_historical_weather(weather, start_year, end_year)
        return weather, {**payload["provenance"], "cache_hit": True}

    hourly, metadata = pvlib.iotools.get_pvgis_hourly(
        site.latitude,
        site.longitude,
        start=start_year,
        end=end_year,
        raddatabase="PVGIS-SARAH3",
        components=True,
        surface_tilt=0,
        surface_azimuth=180,
        outputformat="json",
        usehorizon=True,
        pvcalculation=False,
        map_variables=True,
        url=PVGIS_URL,
        timeout=60,
    )
    if "Int" not in hourly.columns:
        raise ValueError(
            "PVGIS historical response is missing reconstruction flags")
    reconstruction_flags = hourly["Int"].to_numpy(dtype=float)
    if (not np.isfinite(reconstruction_flags).all()
            or not np.isin(reconstruction_flags, (0, 1)).all()):
        raise ValueError(
            "PVGIS historical reconstruction flags must be zero or one")
    weather, adjustments = pvgis_hourly_to_weather(hourly)
    validate_historical_weather(weather, start_year, end_year)
    provenance = {
        **identity,
        "source": (
            "European Commission JRC PVGIS historical hourly radiation series"),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider_metadata": metadata,
        "weather_adjustments": adjustments,
        "reconstructed_hours": int(reconstruction_flags.sum()),
        "timestamp_minute_utc": int(weather.index[0].minute),
        "note": (
            "Historical modeled weather, not measured PV production. PVGIS "
            "historical timestamps already include the radiation dataset's UTC "
            "minute; no additional TMY irradiance offset is applied."),
    }
    payload = {
        "identity": identity,
        "provenance": provenance,
        "weather": {
            "index": [stamp.isoformat() for stamp in weather.index],
            "columns": list(weather.columns),
            "data": weather.to_numpy().tolist(),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, default=str, allow_nan=False), encoding="utf-8")
    temporary.replace(path)
    return weather, {**provenance, "cache_hit": False}


def irradiance_offset_hours(provenance: dict) -> float:
    """Read PVGIS 5.3 JSON timing metadata, including from unmodified v1 caches.

    Missing is NOT equivalent to zero. Refuse to silently recreate the old
    timing bug when an older provider response omits this field.
    See the JRC PVGIS TMY generator documentation, header update December 2024.
    """
    import math

    try:
        value = provenance["provider_metadata"]["inputs"]["location"]["irradiance_time_offset"]
    except (KeyError, TypeError) as exc:
        raise ValueError("PVGIS irradiance timing metadata is missing; refresh weather from PVGIS 5.3") from exc
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not -1 < value < 1):
        raise ValueError("PVGIS irradiance timing offset must be numeric and strictly between -1 and 1 hour")
    return float(value)
