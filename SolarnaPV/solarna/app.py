"""Interactive local web application for Solarna's fixed-PV optimizer.

The HTTP server is intentionally dependency-free beyond the modeling package.
It supports local/LAN operation and authenticated HTTPS deployment behind the
included production reverse proxy. Larger public deployments should add durable
jobs, centralized storage, monitoring, and rate limits.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
import json
import math
import os
from pathlib import Path
import re
import secrets
import sys
from threading import RLock
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from . import __version__
from .benchmark import compare_with_report, load_pvgis_benchmark
from .dashboard import validate_report
from .engine import SAPM_TEMPERATURE_MODELS, Site, System, normalize_months
from .history import build_historical_range
from .reporting import (
    build_report,
    normalize_existing_orientation,
    write_report,
)
from .weather import load_hourly_history, load_tmy, pvgis_elevation_m


MAX_REQUEST_BYTES = 64 * 1024
JOB_ID = re.compile(r"^[0-9a-f]{32}$")
REPORT_NAME = re.compile(r"^job-[0-9a-f]{32}\.json$")
SUPPORTED_ORIGIN_SCHEMES = frozenset(("http", "https", "capacitor"))
NORMALIZED_CAPACITY_KW = 1.0
NORMALIZED_DC_AC_RATIO = 1.2
DEFAULT_SESSION_TTL_SECONDS = 12 * 60 * 60
DEFAULT_SUPABASE_AUTH_CACHE_SECONDS = 45
ENGINEERING_LOSS_KEYS = (
    "soiling",
    "shading",
    "mismatch",
    "wiring",
    "availability",
    "quality",
)


class JobCapacityError(RuntimeError):
    """Raised when the bounded optimization queue is full."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def finite_number(payload: dict, key: str, minimum: float, maximum: float,
                  default=None) -> float:
    value = payload.get(key, default)
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not minimum <= value <= maximum):
        raise ValueError(f"{key} must be a number between {minimum:g} and {maximum:g}")
    return float(value)


def optional_equipment_name(payload: dict, key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if (not isinstance(value, str) or value != value.strip()
            or not 1 <= len(value) <= 160
            or any(ord(character) < 32 for character in value)):
        raise ValueError(f"{key} must contain between 1 and 160 visible characters")
    return value


def normalize_engineering_losses(value) -> tuple[tuple[str, float], ...]:
    if value is None:
        return ()
    if not isinstance(value, dict) or set(value) != set(ENGINEERING_LOSS_KEYS):
        raise ValueError(
            "engineering_losses_percent must contain all supported loss categories")
    normalized = []
    for key in ENGINEERING_LOSS_KEYS:
        loss = value[key]
        if (isinstance(loss, bool) or not isinstance(loss, (int, float))
                or not math.isfinite(loss) or not 0 <= loss <= 50):
            raise ValueError(
                f"engineering loss {key} must be a number between 0 and 50")
        normalized.append((key, float(loss)))
    return tuple(normalized)


def combined_loss_percent(losses: tuple[tuple[str, float], ...]) -> float:
    retention = math.prod(1 - value / 100 for _, value in losses)
    return 100 * (1 - retention)


def normalize_origin(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Allowed origins must be non-empty URLs")
    parsed = urlsplit(value.strip())
    if (parsed.scheme not in SUPPORTED_ORIGIN_SCHEMES or not parsed.netloc
            or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError(
            "Allowed origins must contain only an http, https, or capacitor origin")
    return f"{parsed.scheme}://{parsed.netloc}"


def normalize_access_token(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or value != value.strip():
        raise ValueError("Access token must not contain leading or trailing whitespace")
    if not 16 <= len(value) <= 512 or any(ord(character) < 33 for character in value):
        raise ValueError(
            "Access token must contain 16 to 512 visible characters")
    return value


def normalize_login_email(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or value != value.strip():
        raise ValueError("Login email must not contain surrounding whitespace")
    normalized = value.lower()
    if (not 3 <= len(normalized) <= 254
            or normalized.count("@") != 1
            or any(character.isspace() for character in normalized)):
        raise ValueError("Login email is invalid")
    local, domain = normalized.split("@", 1)
    if (not local or not domain or "." not in domain
            or domain.startswith(".") or domain.endswith(".")):
        raise ValueError("Login email is invalid")
    return normalized


def normalize_login_password(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or value != value.strip():
        raise ValueError("Login password must not contain surrounding whitespace")
    if not 12 <= len(value) <= 512 or any(ord(character) < 32 for character in value):
        raise ValueError(
            "Login password must contain 12 to 512 printable characters")
    return value


def normalize_supabase_url(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or value != value.strip():
        raise ValueError("Supabase URL must not contain surrounding whitespace")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.netloc
            or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("Supabase URL must be an HTTPS origin")
    return f"https://{parsed.netloc}"


def normalize_supabase_publishable_key(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or value != value.strip():
        raise ValueError(
            "Supabase publishable key must not contain surrounding whitespace")
    if (not value.startswith("sb_publishable_")
            or not 24 <= len(value) <= 256
            or any(ord(character) < 33 for character in value)):
        raise ValueError("Supabase publishable key is invalid")
    return value


def normalize_android_apk_path(value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    path = Path(value).expanduser().resolve()
    if path.suffix.lower() != ".apk":
        raise ValueError("Android download path must end in .apk")
    return path


def normalize_ios_project_path(value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    path = Path(value).expanduser().resolve()
    if path.suffix.lower() != ".zip":
        raise ValueError("iOS project download path must end in .zip")
    return path


@dataclass(frozen=True)
class OptimizationRequest:
    site: Site
    system: System
    coarse_step: int
    fine_step: float
    timing_sensitivity: bool
    period_analysis: str | None
    period_months: tuple[int, ...] | None
    pvgis_benchmark: bool
    historical_range: bool
    existing_orientation: tuple[float, float] | None
    normalized_capacity: bool
    use_pvgis_elevation: bool
    engineering_losses: tuple[tuple[str, float], ...]
    panel_model: str | None
    inverter_model: str | None

    def public(self) -> dict:
        return {
            "name": self.site.name,
            "latitude": self.site.latitude,
            "longitude": self.site.longitude,
            "altitude_m": (
                None if self.use_pvgis_elevation else self.site.altitude_m),
            "elevation_mode": (
                "pvgis" if self.use_pvgis_elevation else "manual"),
            "capacity_kw": self.system.dc_capacity_kw,
            "dc_ac_ratio": self.system.dc_ac_ratio,
            "albedo": self.system.albedo,
            "other_dc_loss_percent": self.system.other_dc_loss_fraction * 100,
            "loss_model": (
                "engineering" if self.engineering_losses else "simple"),
            "engineering_losses_percent": (
                dict(self.engineering_losses)
                if self.engineering_losses else None),
            "gamma_pdc_percent_per_c": self.system.gamma_pdc_per_c * 100,
            "inverter_efficiency_percent": self.system.inverter_efficiency * 100,
            "temperature_model": self.system.temperature_model,
            "panel_model": self.panel_model,
            "inverter_model": self.inverter_model,
            "coarse_step": self.coarse_step,
            "fine_step": self.fine_step,
            "timing_sensitivity": self.timing_sensitivity,
            "period_analysis": self.period_analysis or "none",
            "period_months": (
                list(self.period_months)
                if self.period_months is not None else None),
            "pvgis_benchmark": self.pvgis_benchmark,
            "historical_range": self.historical_range,
            "normalized_capacity": self.normalized_capacity,
            "existing_tilt_deg": (
                self.existing_orientation[0]
                if self.existing_orientation is not None else None),
            "existing_azimuth_deg": (
                self.existing_orientation[1]
                if self.existing_orientation is not None else None),
        }


def parse_request(payload: dict) -> OptimizationRequest:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    name = payload.get("name", "")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise ValueError("name must contain between 1 and 120 characters")
    elevation_mode = payload.get("elevation_mode", "manual")
    if elevation_mode not in ("pvgis", "manual"):
        raise ValueError("elevation_mode must be pvgis or manual")
    use_pvgis_elevation = elevation_mode == "pvgis"
    altitude = (
        0.0 if use_pvgis_elevation
        else finite_number(payload, "altitude_m", -500, 9000))
    site = Site(
        latitude=finite_number(payload, "latitude", -90, 90),
        longitude=finite_number(payload, "longitude", -180, 180),
        altitude_m=altitude,
        name=name.strip(),
    )
    capacity = finite_number(payload, "capacity_kw", 0.05, 100_000)
    normalized_capacity = payload.get("normalized_capacity", False)
    if not isinstance(normalized_capacity, bool):
        raise ValueError("normalized_capacity must be true or false")
    if normalized_capacity and not math.isclose(
            capacity, NORMALIZED_CAPACITY_KW, rel_tol=0, abs_tol=1e-9):
        raise ValueError("normalized_capacity requires capacity_kw=1")
    ratio = finite_number(payload, "dc_ac_ratio", 0.5, 3)
    if normalized_capacity and not math.isclose(
            ratio, NORMALIZED_DC_AC_RATIO, rel_tol=0, abs_tol=1e-9):
        raise ValueError("normalized_capacity requires dc_ac_ratio=1.2")
    albedo = finite_number(payload, "albedo", 0, 1)
    loss_model = payload.get("loss_model", "simple")
    if loss_model not in ("simple", "engineering"):
        raise ValueError("loss_model must be simple or engineering")
    engineering_losses = normalize_engineering_losses(
        payload.get("engineering_losses_percent"))
    if loss_model == "engineering":
        if not engineering_losses:
            raise ValueError(
                "engineering_losses_percent is required for engineering loss mode")
        losses_percent = combined_loss_percent(engineering_losses)
        if losses_percent > 80:
            raise ValueError("combined engineering losses must not exceed 80 percent")
    else:
        if engineering_losses:
            raise ValueError(
                "engineering_losses_percent requires engineering loss mode")
        losses_percent = finite_number(
            payload, "other_dc_loss_percent", 0, 80)
    gamma_percent = finite_number(
        payload, "gamma_pdc_percent_per_c", -2, 0, -0.4)
    inverter_percent = finite_number(
        payload, "inverter_efficiency_percent", 80, 100, 96)
    temperature_model = payload.get(
        "temperature_model", "open_rack_glass_glass")
    if temperature_model not in SAPM_TEMPERATURE_MODELS:
        raise ValueError(
            "temperature_model must be a supported SAPM module/mounting preset")
    system = System(
        dc_capacity_kw=capacity,
        gamma_pdc_per_c=gamma_percent / 100,
        dc_ac_ratio=ratio,
        inverter_efficiency=inverter_percent / 100,
        albedo=albedo,
        other_dc_loss_fraction=losses_percent / 100,
        temperature_model=temperature_model,
    )
    coarse = payload.get("coarse_step")
    if isinstance(coarse, bool) or coarse not in (5, 10, 15, 30):
        raise ValueError("coarse_step must be 5, 10, 15, or 30")
    fine = payload.get("fine_step")
    if isinstance(fine, bool) or fine not in (0.5, 1, 1.0):
        raise ValueError("fine_step must be 0.5 or 1")
    sensitivity = payload.get("timing_sensitivity")
    if not isinstance(sensitivity, bool):
        raise ValueError("timing_sensitivity must be true or false")
    period = payload.get("period_analysis", "none")
    if period not in (
            "none", "winter", "summer", "spring", "autumn", "custom"):
        raise ValueError(
            "period_analysis must be none, winter, summer, spring, autumn, or custom")
    period_months = (
        normalize_months(payload.get("period_months"))
        if period == "custom" else None)
    period = None if period == "none" else period
    benchmark = payload.get("pvgis_benchmark", False)
    if not isinstance(benchmark, bool):
        raise ValueError("pvgis_benchmark must be true or false")
    historical_range = payload.get("historical_range", False)
    if not isinstance(historical_range, bool):
        raise ValueError("historical_range must be true or false")
    existing_tilt = payload.get("existing_tilt_deg")
    existing_azimuth = payload.get("existing_azimuth_deg")
    if (existing_tilt is None) != (existing_azimuth is None):
        raise ValueError(
            "existing_tilt_deg and existing_azimuth_deg must be provided together")
    existing_orientation = normalize_existing_orientation(
        None if existing_tilt is None
        else (existing_tilt, existing_azimuth))
    panel_model = optional_equipment_name(payload, "panel_model")
    inverter_model = optional_equipment_name(payload, "inverter_model")
    return OptimizationRequest(
        site, system, int(coarse), float(fine), sensitivity, period,
        period_months, benchmark, historical_range, existing_orientation,
        normalized_capacity, use_pvgis_elevation, engineering_losses,
        panel_model, inverter_model)


class SolarnaApplication:
    """In-memory job coordinator with atomic report persistence."""

    def __init__(self, cache_dir: Path, output_dir: Path,
                 sample_report: Path | None = None, max_workers: int = 1,
                 max_pending_jobs: int = 4,
                 allowed_origins=(), access_token: str | None = None,
                 login_email: str | None = None,
                 login_password: str | None = None,
                 session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
                 supabase_url: str | None = None,
                 supabase_publishable_key: str | None = None,
                 supabase_authorized_emails=(),
                 supabase_auth_cache_seconds: int =
                 DEFAULT_SUPABASE_AUTH_CACHE_SECONDS,
                 android_apk_path: str | Path | None = None,
                 ios_project_path: str | Path | None = None):
        if (isinstance(max_workers, bool) or not isinstance(max_workers, int)
                or max_workers < 1):
            raise ValueError("max_workers must be a positive integer")
        if (isinstance(max_pending_jobs, bool)
                or not isinstance(max_pending_jobs, int)
                or max_pending_jobs < max_workers):
            raise ValueError(
                "max_pending_jobs must be an integer at least as large as max_workers")
        self.cache_dir = Path(cache_dir)
        self.output_dir = Path(output_dir)
        self.sample_report = Path(sample_report) if sample_report else None
        self.allowed_origins = frozenset(
            normalize_origin(origin) for origin in allowed_origins)
        self.access_token = normalize_access_token(access_token)
        self.login_email = normalize_login_email(login_email)
        self.login_password = normalize_login_password(login_password)
        if (self.login_email is None) != (self.login_password is None):
            raise ValueError(
                "Login email and login password must be configured together")
        self.supabase_url = normalize_supabase_url(supabase_url)
        self.supabase_publishable_key = normalize_supabase_publishable_key(
            supabase_publishable_key)
        if ((self.supabase_url is None)
                != (self.supabase_publishable_key is None)):
            raise ValueError(
                "Supabase URL and publishable key must be configured together")
        self.supabase_authorized_emails = frozenset(
            normalize_login_email(email)
            for email in supabase_authorized_emails)
        if (isinstance(session_ttl_seconds, bool)
                or not isinstance(session_ttl_seconds, int)
                or not 60 <= session_ttl_seconds <= 7 * 24 * 60 * 60):
            raise ValueError(
                "session_ttl_seconds must be between 60 and 604800")
        if (isinstance(supabase_auth_cache_seconds, bool)
                or not isinstance(supabase_auth_cache_seconds, int)
                or not 0 <= supabase_auth_cache_seconds <= 300):
            raise ValueError(
                "supabase_auth_cache_seconds must be between 0 and 300")
        self.session_ttl_seconds = session_ttl_seconds
        self.supabase_auth_cache_seconds = supabase_auth_cache_seconds
        self.max_pending_jobs = max_pending_jobs
        self.android_apk_path = normalize_android_apk_path(android_apk_path)
        self.ios_project_path = normalize_ios_project_path(ios_project_path)
        self._jobs: dict[str, dict] = {}
        self._futures = {}
        self._sessions: dict[str, datetime] = {}
        self._supabase_auth_cache: dict[str, datetime] = {}
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="solarna-optimizer")

    def close(self):
        self._executor.shutdown(wait=False, cancel_futures=False)

    @property
    def authentication_required(self) -> bool:
        return (
            self.supabase_url is not None
            or self.login_email is not None
            or self.access_token is not None
        )

    @property
    def authentication_mode(self) -> str:
        if self.supabase_url is not None:
            return "supabase"
        if self.login_email is not None:
            return "login"
        if self.access_token is not None:
            return "token"
        return "none"

    def login(self, email, password) -> dict | None:
        if self.login_email is None or self.login_password is None:
            raise RuntimeError("Email login is not configured")
        supplied_email = (
            email.strip().lower()
            if isinstance(email, str) and len(email) <= 254 else "")
        supplied_password = (
            password
            if isinstance(password, str) and len(password) <= 512 else "")
        email_matches = hmac.compare_digest(supplied_email, self.login_email)
        password_matches = hmac.compare_digest(
            supplied_password, self.login_password)
        if not (email_matches and password_matches):
            return None
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self.session_ttl_seconds)
        with self._lock:
            self._remove_expired_sessions(now)
            self._sessions[token] = expires_at
        return {
            "token": token,
            "token_type": "Bearer",
            "expires_in_seconds": self.session_ttl_seconds,
            "expires_at_utc": expires_at.isoformat(),
        }

    def _remove_expired_sessions(self, now: datetime):
        expired = [
            token for token, expires_at in self._sessions.items()
            if expires_at <= now
        ]
        for token in expired:
            del self._sessions[token]

    def authorize_bearer(self, token: str) -> bool:
        if (self.access_token is not None
                and hmac.compare_digest(token, self.access_token)):
            return True
        now = datetime.now(timezone.utc)
        with self._lock:
            self._remove_expired_sessions(now)
            if token in self._sessions:
                return True
        if self.supabase_url is None:
            return False
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._lock:
            cached_until = self._supabase_auth_cache.get(token_hash)
            if cached_until is not None and cached_until > now:
                return True
            expired = [
                key for key, expiry in self._supabase_auth_cache.items()
                if expiry <= now
            ]
            for key in expired:
                del self._supabase_auth_cache[key]
        request = Request(
            f"{self.supabase_url}/auth/v1/user",
            headers={
                "Accept": "application/json",
                "apikey": self.supabase_publishable_key,
                "Authorization": f"Bearer {token}",
            },
        )
        try:
            with urlopen(request, timeout=6) as response:
                user = json.load(response)
        except HTTPError as exc:
            if exc.code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                return False
            return False
        except (OSError, URLError, ValueError, json.JSONDecodeError):
            return False
        if not isinstance(user, dict) or not isinstance(user.get("id"), str):
            return False
        if self.supabase_authorized_emails:
            email = user.get("email")
            if (not isinstance(email, str)
                    or email.strip().lower()
                    not in self.supabase_authorized_emails):
                return False
        if self.supabase_auth_cache_seconds:
            with self._lock:
                self._supabase_auth_cache[token_hash] = (
                    now + timedelta(seconds=self.supabase_auth_cache_seconds))
        return True

    def logout(self, token: str):
        with self._lock:
            self._sessions.pop(token, None)

    def submit(self, payload: dict) -> dict:
        request = parse_request(payload)
        with self._lock:
            active_jobs = sum(
                job["status"] in ("queued", "running")
                for job in self._jobs.values())
            if active_jobs >= self.max_pending_jobs:
                raise JobCapacityError(
                    "The calculation queue is full. Try again shortly.")
            job_id = uuid4().hex
            job = {
                "id": job_id,
                "status": "queued",
                "phase": "queued",
                "progress": 0.0,
                "message": "Waiting for the optimizer",
                "request": request.public(),
                "created_at_utc": utc_now(),
                "started_at_utc": None,
                "finished_at_utc": None,
                "report_path": None,
                "error": None,
                "_report": None,
            }
            self._jobs[job_id] = job
            self._futures[job_id] = self._executor.submit(
                self._execute, job_id, request)
        return self.job(job_id)

    def queue_status(self) -> dict:
        with self._lock:
            active_jobs = sum(
                job["status"] in ("queued", "running")
                for job in self._jobs.values())
        return {
            "active_jobs": active_jobs,
            "max_pending_jobs": self.max_pending_jobs,
            "accepting_jobs": active_jobs < self.max_pending_jobs,
        }

    def wait(self, job_id: str, timeout: float | None = None):
        with self._lock:
            future = self._futures.get(job_id)
        if future is None:
            raise KeyError("Unknown job")
        future.result(timeout=timeout)
        return self.job(job_id)

    def _update(self, job_id: str, **changes):
        with self._lock:
            self._jobs[job_id].update(changes)

    @staticmethod
    def _search_fraction(phase: str, done: int, total: int) -> float:
        ratio = done / total if total else 0
        if phase == "coarse_search":
            return 0.78 * ratio
        if phase == "fine_search":
            return 0.78 + 0.19 * ratio
        return 0.97 + 0.03 * ratio

    def _execute(self, job_id: str, request: OptimizationRequest):
        try:
            self._update(
                job_id, status="running", phase="weather", progress=0.03,
                message="Loading PVGIS typical-year weather",
                started_at_utc=utc_now())
            weather, provenance = load_tmy(request.site, self.cache_dir)
            effective_site = request.site
            elevation_source = "user"
            if request.use_pvgis_elevation:
                effective_site = replace(
                    request.site,
                    altitude_m=pvgis_elevation_m(provenance))
                elevation_source = "PVGIS terrain model"
            source = "cached PVGIS weather" if provenance.get("cache_hit") else "downloaded PVGIS weather"
            self._update(
                job_id, phase="optimization", progress=0.16,
                message=f"Searching orientations using {source}")

            last_progress = 0.16
            search_order = ["corrected_timing"]
            if request.timing_sensitivity:
                search_order.append("zero_offset_comparison")
            if request.period_analysis:
                search_order.append("period_analysis")
            search_labels = {
                "corrected_timing": "Optimizing with corrected PVGIS timing",
                "zero_offset_comparison": "Comparing against zero-offset timing",
                "period_analysis": "Optimizing the selected seasonal period",
            }
            optimization_end = 0.83 if request.historical_range else 0.95

            def progress(search: str, phase: str, done: int, total: int):
                nonlocal last_progress
                fraction = self._search_fraction(phase, done, total)
                stage = search_order.index(search)
                span = (optimization_end - 0.16) / len(search_order)
                value = 0.16 + span * (stage + fraction)
                label = search_labels[search]
                value = min(optimization_end, value)
                if value >= last_progress + 0.005 or done == total:
                    last_progress = value
                    self._update(
                        job_id, phase=phase, progress=value,
                        message=f"{label}: {done}/{total} samples")

            report = build_report(
                weather, provenance, effective_site, request.system,
                request.coarse_step, request.fine_step,
                request.timing_sensitivity, request.period_analysis,
                progress_callback=progress,
                existing_orientation=request.existing_orientation,
                period_months=request.period_months)
            report["site_elevation"] = {
                "altitude_m": effective_site.altitude_m,
                "source": elevation_source,
            }
            if request.normalized_capacity:
                report["assumptions_and_limitations"].insert(
                    0,
                    "System size is normalized to 1 kWp with a 1.2 DC/AC "
                    "reference ratio; total installation energy is not estimated.")
            if request.historical_range:
                self._update(
                    job_id, phase="historical_weather", progress=0.84,
                    message="Loading PVGIS historical weather")
                try:
                    history_weather, history_provenance = load_hourly_history(
                        effective_site, self.cache_dir)
                    history_source = (
                        "cached historical weather"
                        if history_provenance.get("cache_hit")
                        else "downloaded historical weather")

                    def history_progress(done: int, total: int):
                        value = 0.86 + 0.09 * (done / total if total else 0)
                        self._update(
                            job_id,
                            phase="historical_range",
                            progress=min(0.95, value),
                            message=(
                                f"Evaluating {history_source}: {done}/{total} "
                                "orientations"),
                        )

                    report["historical_range"] = build_historical_range(
                        history_weather,
                        history_provenance,
                        effective_site,
                        request.system,
                        report,
                        request.existing_orientation,
                        history_progress,
                    )
                except (OSError, ValueError, KeyError, TypeError,
                        json.JSONDecodeError) as exc:
                    report["historical_range"] = {
                        "status": "unavailable",
                        "source": (
                            "European Commission JRC PVGIS historical hourly "
                            "radiation series"),
                        "error": f"{type(exc).__name__}: {exc}",
                        "note": "The core optimization completed, but the requested "
                                "historical range could not be calculated.",
                    }
            if request.pvgis_benchmark:
                self._update(
                    job_id, phase="benchmark", progress=0.96,
                    message="Comparing with the independent PVGIS PVcalc model")
                try:
                    benchmark = load_pvgis_benchmark(
                        effective_site, request.system, self.cache_dir)
                    report["pvgis_benchmark"] = compare_with_report(
                        report, benchmark)
                except (OSError, ValueError, KeyError, TypeError,
                        json.JSONDecodeError) as exc:
                    report["pvgis_benchmark"] = {
                        "status": "unavailable",
                        "source": "European Commission JRC PVGIS 5.3 PVcalc",
                        "error": f"{type(exc).__name__}: {exc}",
                        "note": "The Solarna optimization completed, but the requested "
                                "independent benchmark could not be retrieved or validated.",
                    }
            report["application_request"] = request.public()
            self._update(
                job_id, phase="saving", progress=0.97,
                message="Saving the reproducible report")
            report_path = self.output_dir / f"job-{job_id}.json"
            write_report(report, report_path)
            self._update(
                job_id, status="completed", phase="completed", progress=1.0,
                message="Optimization complete", finished_at_utc=utc_now(),
                report_path=str(report_path), _report=report)
        except Exception as exc:  # Job failures must become inspectable API state.
            self._update(
                job_id, status="failed", phase="failed", progress=1.0,
                message="Optimization failed", finished_at_utc=utc_now(),
                error=f"{type(exc).__name__}: {exc}")

    def job(self, job_id: str) -> dict:
        if not JOB_ID.fullmatch(job_id):
            raise KeyError("Unknown job")
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError("Unknown job")
            return {key: value for key, value in self._jobs[job_id].items()
                    if not key.startswith("_")}

    def report(self, job_id: str) -> dict:
        if not JOB_ID.fullmatch(job_id):
            raise KeyError("Unknown job")
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError("Unknown job")
            report = job.get("_report")
            status = job["status"]
        if status != "completed" or report is None:
            raise RuntimeError("Report is not ready")
        return report

    def sample(self) -> dict:
        if not self.sample_report or not self.sample_report.is_file():
            raise FileNotFoundError("No sample report is available")
        report = json.loads(self.sample_report.read_text(encoding="utf-8"))
        validate_report(report)
        return report

    def saved_report(self, name: str) -> dict:
        if not REPORT_NAME.fullmatch(name):
            raise KeyError("Unknown report")
        path = self.output_dir / name
        if not path.is_file():
            raise KeyError("Unknown report")
        report = json.loads(path.read_text(encoding="utf-8"))
        validate_report(report)
        return report

    def list_reports(self) -> list[dict]:
        if not self.output_dir.is_dir():
            return []
        summaries = []
        for path in self.output_dir.glob("job-*.json"):
            if not REPORT_NAME.fullmatch(path.name):
                continue
            try:
                report = json.loads(path.read_text(encoding="utf-8"))
                validate_report(report)
                best = report["best"]
                site = report["site"]
                system = report["system"]
                generated = report.get(
                    "generated_at_utc",
                    datetime.fromtimestamp(
                        path.stat().st_mtime, timezone.utc).isoformat(),
                )
                summaries.append({
                    "name": path.name,
                    "generated_at_utc": generated,
                    "site_name": site["name"],
                    "latitude": site["latitude"],
                    "longitude": site["longitude"],
                    "capacity_kw": system["dc_capacity_kw"],
                    "tilt_deg": best["tilt_deg"],
                    "azimuth_deg": best["azimuth_deg"],
                    "annual_ac_kwh": best["annual_ac_kwh"],
                    "has_period_analysis": "period_analysis" in report,
                    "historical_range_status": (
                        report.get("historical_range", {}).get("status")),
                    "benchmark_status": (
                        report.get("pvgis_benchmark", {}).get("status")),
                })
            except (OSError, ValueError, KeyError, TypeError,
                    json.JSONDecodeError):
                continue
        summaries.sort(
            key=lambda item: str(item["generated_at_utc"]), reverse=True)
        return summaries[:200]


def web_asset(name: str) -> bytes:
    return (resources.files("solarna") / "web" / name).read_bytes()


class SolarnaHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, handler, application: SolarnaApplication):
        self.application = application
        super().__init__(server_address, handler)


class RequestHandler(BaseHTTPRequestHandler):
    server_version = f"SolarnaLocal/{__version__}"

    @property
    def application(self) -> SolarnaApplication:
        return self.server.application

    def log_message(self, message, *args):
        sys.stderr.write(
            f"{self.log_date_time_string()} {self.client_address[0]} "
            f"{message % args}\n")

    def security_headers(self):
        connect_sources = ["'self'"]
        if self.application.supabase_url is not None:
            connect_sources.append(self.application.supabase_url)
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; connect-src "
            f"{' '.join(connect_sources)}; img-src 'self' data:; "
            "style-src 'self'; script-src 'self'; worker-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "geolocation=(self)")
        origin = self.headers.get("Origin")
        if origin in self.application.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Vary", "Origin")

    def send_bytes(self, status: int, body: bytes, content_type: str,
                   cache_control: str = "no-cache", extra_headers=()):
        self.send_response(status)
        self.security_headers()
        for name, value in extra_headers:
            self.send_header(name, value)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, status: int, payload: dict, extra_headers=()):
        body = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_bytes(
            status, body, "application/json; charset=utf-8", "no-store",
            extra_headers)

    def error_json(self, status: int, message: str):
        self.send_json(status, {"error": message})

    def send_file(self, status: int, path: Path, content_type: str,
                  download_name: str):
        if not path.is_file():
            raise FileNotFoundError("Download is not available")
        size = path.stat().st_size
        self.send_response(status)
        self.security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header(
            "Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(size))
        self.end_headers()
        if self.command == "HEAD":
            return
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                self.wfile.write(chunk)

    def authorized(self) -> bool:
        if not self.application.authentication_required:
            return True
        supplied = self.bearer_token()
        return bool(supplied) and self.application.authorize_bearer(supplied)

    def bearer_token(self) -> str:
        scheme, separator, supplied = self.headers.get(
            "Authorization", "").partition(" ")
        if (separator != " " or scheme.lower() != "bearer"
                or not supplied or len(supplied) > 4096):
            return ""
        return supplied

    def require_authorization(self) -> bool:
        if self.authorized():
            return True
        body = json.dumps(
            {"error": "Login required"}, allow_nan=False).encode("utf-8")
        self.send_bytes(
            HTTPStatus.UNAUTHORIZED,
            body,
            "application/json; charset=utf-8",
            "no-store",
            (("WWW-Authenticate", 'Bearer realm="Solarna"'),),
        )
        return False

    def do_HEAD(self):
        self.do_GET()

    def do_OPTIONS(self):
        path = urlsplit(self.path).path
        origin = self.headers.get("Origin")
        if not path.startswith("/api/") or origin not in self.application.allowed_origins:
            self.error_json(HTTPStatus.FORBIDDEN, "Origin is not allowed")
            return
        self.send_bytes(HTTPStatus.NO_CONTENT, b"", "text/plain; charset=utf-8", "no-store")

    def do_GET(self):
        path = urlsplit(self.path).path
        static = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/login.html": ("login.html", "text/html; charset=utf-8"),
            "/reset-password.html": (
                "reset-password.html", "text/html; charset=utf-8"),
            "/privacy.html": ("privacy.html", "text/html; charset=utf-8"),
            "/app.css": ("app.css", "text/css; charset=utf-8"),
            "/config.js": ("config.js", "text/javascript; charset=utf-8"),
            "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"),
            "/supabase-client.js": (
                "supabase-client.js", "text/javascript; charset=utf-8"),
            "/system-config.js": ("system-config.js", "text/javascript; charset=utf-8"),
            "/result-summary.js": ("result-summary.js", "text/javascript; charset=utf-8"),
            "/install-support.js": ("install-support.js", "text/javascript; charset=utf-8"),
            "/cloud-storage.js": ("cloud-storage.js", "text/javascript; charset=utf-8"),
            "/login.js": ("login.js", "text/javascript; charset=utf-8"),
            "/reset-password.js": (
                "reset-password.js", "text/javascript; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/solarna-mark.svg": ("solarna-mark.svg", "image/svg+xml"),
            "/favicon.svg": ("favicon.svg", "image/svg+xml"),
            "/service-worker.js": ("service-worker.js", "text/javascript; charset=utf-8"),
            "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
        }
        try:
            if path in static:
                name, content_type = static[path]
                self.send_bytes(
                    HTTPStatus.OK, web_asset(name), content_type, "no-cache")
                return
            icon_match = re.fullmatch(r"/icon-(180|192|512)\.png", path)
            if icon_match:
                size = int(icon_match.group(1))
                self.send_bytes(
                    HTTPStatus.OK, web_asset(f"icon-{size}.png"), "image/png",
                    "public, max-age=86400")
                return
            if path == "/favicon.ico":
                self.send_bytes(
                    HTTPStatus.OK, web_asset("icon-192.png"), "image/png",
                    "public, max-age=86400")
                return
            if path == "/downloads/solarna-android.apk":
                if self.application.android_apk_path is None:
                    raise FileNotFoundError("Android installer is not available")
                self.send_file(
                    HTTPStatus.OK,
                    self.application.android_apk_path,
                    "application/vnd.android.package-archive",
                    "Solarna-android.apk",
                )
                return
            if path == "/downloads/solarna-ios-project.zip":
                if self.application.ios_project_path is None:
                    raise FileNotFoundError("iOS project is not available")
                self.send_file(
                    HTTPStatus.OK,
                    self.application.ios_project_path,
                    "application/zip",
                    "Solarna-iOS-project.zip",
                )
                return
            if path == "/api/health":
                queue = self.application.queue_status()
                android_download_url = None
                if (self.application.android_apk_path is not None
                        and self.application.android_apk_path.is_file()):
                    android_download_url = "/downloads/solarna-android.apk"
                ios_project_download_url = None
                if (self.application.ios_project_path is not None
                        and self.application.ios_project_path.is_file()):
                    ios_project_download_url = (
                        "/downloads/solarna-ios-project.zip")
                self.send_json(HTTPStatus.OK, {
                    "status": "ok", "service": "solarna",
                    "version": __version__,
                    "authentication_required":
                        self.application.authentication_required,
                    "authentication_mode":
                        self.application.authentication_mode,
                    "supabase_url": self.application.supabase_url,
                    "supabase_publishable_key":
                        self.application.supabase_publishable_key,
                    "queue": queue,
                    "android_download_url": android_download_url,
                    "ios_project_download_url": ios_project_download_url,
                    "time_utc": utc_now(),
                })
                return
            if path.startswith("/api/") and not self.require_authorization():
                return
            if path == "/api/sample":
                self.send_json(HTTPStatus.OK, self.application.sample())
                return
            if path == "/api/reports":
                self.send_json(
                    HTTPStatus.OK,
                    {"reports": self.application.list_reports()})
                return
            report_match = re.fullmatch(
                r"/api/reports/(job-[0-9a-f]{32}\.json)", path)
            if report_match:
                self.send_json(
                    HTTPStatus.OK,
                    self.application.saved_report(report_match.group(1)))
                return
            match = re.fullmatch(r"/api/jobs/([0-9a-f]{32})(/report)?", path)
            if match:
                job_id, report_suffix = match.groups()
                payload = (self.application.report(job_id)
                           if report_suffix else self.application.job(job_id))
                self.send_json(HTTPStatus.OK, payload)
                return
            self.error_json(HTTPStatus.NOT_FOUND, "Not found")
        except FileNotFoundError as exc:
            self.error_json(HTTPStatus.NOT_FOUND, str(exc))
        except KeyError:
            self.error_json(HTTPStatus.NOT_FOUND, "Unknown job")
        except RuntimeError as exc:
            self.error_json(HTTPStatus.CONFLICT, str(exc))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ("/api/login", "/api/logout", "/api/jobs"):
            self.error_json(HTTPStatus.NOT_FOUND, "Not found")
            return
        if path != "/api/login" and not self.require_authorization():
            return
        try:
            if path == "/api/logout":
                self.application.logout(self.bearer_token())
                self.send_json(HTTPStatus.OK, {"status": "logged_out"})
                return
            payload = self.read_json_body()
            if path == "/api/login":
                session = self.application.login(
                    payload.get("email"), payload.get("password"))
                if session is None:
                    self.error_json(
                        HTTPStatus.UNAUTHORIZED,
                        "Email or password is incorrect")
                    return
                self.send_json(HTTPStatus.OK, session)
                return
            job = self.application.submit(payload)
            self.send_json(HTTPStatus.ACCEPTED, job)
        except JobCapacityError as exc:
            self.send_json(
                HTTPStatus.TOO_MANY_REQUESTS,
                {"error": str(exc)},
                (("Retry-After", "5"),),
            )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except RuntimeError as exc:
            self.error_json(HTTPStatus.CONFLICT, str(exc))

    def read_json_body(self) -> dict:
        if self.headers.get_content_type() != "application/json":
            raise ValueError("Content-Type must be application/json")
        length_text = self.headers.get("Content-Length")
        if length_text is None:
            raise ValueError("Content-Length is required")
        length = int(length_text)
        if not 0 < length <= MAX_REQUEST_BYTES:
            raise ValueError("Request body is empty or too large")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("JSON request body must be an object")
        return payload


def create_server(application: SolarnaApplication, host: str, port: int):
    return SolarnaHTTPServer((host, port), RequestHandler, application)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run Solarna's interactive local web application.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/pvgis"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/app"))
    parser.add_argument("--sample-report", type=Path, default=Path("outputs/sfax.json"))
    parser.add_argument(
        "--android-apk", type=Path, default=None,
        help="Optional APK exposed at /downloads/solarna-android.apk")
    parser.add_argument(
        "--ios-project", type=Path, default=None,
        help="Optional ZIP exposed at /downloads/solarna-ios-project.zip")
    parser.add_argument(
        "--allowed-origin", action="append", default=[],
        help="Exact mobile/web origin allowed to call the API; repeat as needed")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    environment_origins = [
        value.strip()
        for value in os.environ.get("SOLARNA_ALLOWED_ORIGINS", "").split(",")
        if value.strip()
    ]
    try:
        allowed_origins = tuple(dict.fromkeys(
            normalize_origin(value)
            for value in (*args.allowed_origin, *environment_origins)
        ))
    except ValueError as exc:
        parser.error(str(exc))
    try:
        access_token = normalize_access_token(
            os.environ.get("SOLARNA_ACCESS_TOKEN"))
    except ValueError as exc:
        parser.error(f"SOLARNA_ACCESS_TOKEN: {exc}")
    try:
        login_email = normalize_login_email(
            os.environ.get("SOLARNA_LOGIN_EMAIL"))
        login_password = normalize_login_password(
            os.environ.get("SOLARNA_LOGIN_PASSWORD"))
        if (login_email is None) != (login_password is None):
            raise ValueError(
                "SOLARNA_LOGIN_EMAIL and SOLARNA_LOGIN_PASSWORD "
                "must be configured together")
    except ValueError as exc:
        parser.error(str(exc))
    try:
        supabase_url = normalize_supabase_url(
            os.environ.get("SOLARNA_SUPABASE_URL"))
        supabase_publishable_key = normalize_supabase_publishable_key(
            os.environ.get("SOLARNA_SUPABASE_PUBLISHABLE_KEY"))
        if ((supabase_url is None) != (supabase_publishable_key is None)):
            raise ValueError(
                "SOLARNA_SUPABASE_URL and "
                "SOLARNA_SUPABASE_PUBLISHABLE_KEY must be configured together")
    except ValueError as exc:
        parser.error(str(exc))
    try:
        supabase_authorized_emails = tuple(
            normalize_login_email(value.strip())
            for value in os.environ.get(
                "SOLARNA_AUTHORIZED_EMAILS", "").split(",")
            if value.strip()
        )
    except ValueError as exc:
        parser.error(f"SOLARNA_AUTHORIZED_EMAILS: {exc}")
    application = SolarnaApplication(
        args.cache_dir, args.output_dir, args.sample_report,
        allowed_origins=allowed_origins, access_token=access_token,
        login_email=login_email, login_password=login_password,
        supabase_url=supabase_url,
        supabase_publishable_key=supabase_publishable_key,
        supabase_authorized_emails=supabase_authorized_emails,
        android_apk_path=args.android_apk,
        ios_project_path=args.ios_project)
    server = create_server(application, args.host, args.port)
    address, port = server.server_address[:2]
    print(f"Solarna application: http://{address}:{port}/")
    if address not in ("127.0.0.1", "::1", "localhost"):
        print("LAN mode is unencrypted. Use an HTTPS deployment before installing on iOS.")
    if supabase_url:
        print("Supabase login is enabled.")
    elif login_email:
        print("Email/password login is enabled.")
    elif access_token:
        print("Legacy API token protection is enabled.")
    if (application.android_apk_path is not None
            and application.android_apk_path.is_file()):
        print("Android installer: /downloads/solarna-android.apk")
    if (application.ios_project_path is not None
            and application.ios_project_path.is_file()):
        print("iOS project: /downloads/solarna-ios-project.zip")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping Solarna.")
    finally:
        server.server_close()
        application.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
