"""
/health endpoint — system-level health and readiness check.

Returns a summary of each backend's availability without exposing
internal paths, credentials, or stack traces.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Literal

# pyrefly: ignore [missing-import]
from fastapi import APIRouter  # type: ignore
from pydantic import BaseModel

from marg.config import settings

log = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


class BackendStatus(BaseModel):
    name: str
    status: Literal["ok", "degraded", "unavailable"]
    latency_ms: float | None = None
    note: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "unavailable"]
    version: str
    uptime_s: float
    backends: list[BackendStatus]


_START_TIME = time.monotonic()


async def _check_http(name: str, url: str) -> BackendStatus:
    if not url:
        return BackendStatus(name=name, status="unavailable", note="not configured")
    import httpx
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(url)
        latency_ms = (time.monotonic() - t0) * 1000
        if r.status_code < 500:
            return BackendStatus(name=name, status="ok", latency_ms=round(latency_ms, 1))
        return BackendStatus(name=name, status="degraded", latency_ms=round(latency_ms, 1))
    except Exception as exc:
        return BackendStatus(name=name, status="unavailable", note=type(exc).__name__)


def _check_local_file(name: str, path: str) -> BackendStatus:
    p = Path(path)
    if p.exists() and p.stat().st_size > 0:
        return BackendStatus(name=name, status="ok")
    return BackendStatus(name=name, status="unavailable", note="file missing or empty")


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System health check",
    description="Returns the health status of all Marg backend components.",
)
async def health_check() -> HealthResponse:
    from marg import __version__

    checks = await asyncio.gather(
        _check_http("osrm-foot", settings.osrm_foot_url),
        _check_http("osrm-car", settings.osrm_car_url),
        _check_http("osrm-bike", settings.osrm_bike_url),
        _check_http("nominatim", settings.nominatim_url),
    )
    backends: list[BackendStatus] = list(checks)
    backends.append(_check_local_file("geocode-db", settings.geocode_db_path))
    backends.append(_check_local_file("tiles", settings.tiles_path))

    ok_count = sum(1 for b in backends if b.status == "ok")
    total = len(backends)
    if ok_count == total:
        overall = "ok"
    elif ok_count == 0:
        overall = "unavailable"
    else:
        overall = "degraded"

    return HealthResponse(
        status=overall,
        version=__version__,
        uptime_s=round(time.monotonic() - _START_TIME, 1),
        backends=backends,
    )
