"""
Marg FastAPI application — main entry point.

Security posture:
  - Global exception handler suppresses all internal detail from API responses.
  - Rate limiting enforced globally via SlowAPI.
  - CORS configured from MARG_CORS_ORIGINS.
  - No stack traces, internal paths, or raw DB errors exposed to clients.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

# pyrefly: ignore [missing-import]
from fastapi import FastAPI, Request  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from fastapi.responses import FileResponse, JSONResponse  # type: ignore
from slowapi import Limiter, _rate_limit_exceeded_handler  # type: ignore
from slowapi.errors import RateLimitExceeded  # type: ignore
from slowapi.util import get_remote_address  # type: ignore

from marg import __version__
from marg.config import settings
from marg.api.routes import route, geocode, search, tiles, telemetry, health

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger(__name__)

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_rpm}/minute"],
)

# ── App lifecycle ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Marg %s starting — India-scoped mapping engine", __version__)
    log.info(
        "India bbox: lat %.1f–%.1f°N, lon %.1f–%.1f°E",
        settings.INDIA_MIN_LAT,
        settings.INDIA_MAX_LAT,
        settings.INDIA_MIN_LON,
        settings.INDIA_MAX_LON,
    )
    if settings.telemetry_enabled:
        log.info("Phase 2 telemetry ingestion: ENABLED")
    else:
        log.info("Phase 2 telemetry ingestion: disabled (set MARG_TELEMETRY_ENABLED=true to enable)")
    yield
    log.info("Marg shutting down.")


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Marg — India Mapping & Routing Engine",
    description=(
        "Self-hosted, India-scoped mapping and routing API. "
        "Exposes deterministic routing (/route), geocoding (/geocode), "
        "place search (/search), and tile serving (/tiles). "
        "All coordinates are validated against India's geographic bounding box."
    ),
    version=__version__,
    lifespan=lifespan,
    # Suppress server version header from docs UI
    openapi_tags=[
        {"name": "Routing", "description": "Point-to-point route calculation with profile support."},
        {"name": "Geocoding", "description": "Forward and reverse geocoding, India-scoped."},
        {"name": "Search", "description": "POI and place keyword search."},
        {"name": "Tiles", "description": "Vector/raster map tile serving."},
        {"name": "Telemetry (Phase 2)", "description": "DPDP-compliant anonymized ping ingestion."},
        {"name": "Health", "description": "Backend health and readiness."},
    ],
)

# ── Rate limiting state & handler ─────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["X-Marg-Consent", "Content-Type"],
)

# ── Global error suppression (no internal detail leakage) ─────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log full detail server-side, return generic message to client."""
    log.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again later."},
    )

# ── Security headers middleware ────────────────────────────────────────────────

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Remove server identification header if present
    if "server" in response.headers:
        del response.headers["server"]
    return response

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(route.router)
app.include_router(geocode.router)
app.include_router(search.router)
app.include_router(tiles.router)
app.include_router(telemetry.router)
app.include_router(health.router)

# ── Static web visualiser ─────────────────────────────────────────────────────
_WEB_DIR = Path(__file__).parent.parent / "web"

if _WEB_DIR.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/static", StaticFiles(directory=str(_WEB_DIR)), name="static")

@app.get("/", include_in_schema=False)
async def serve_index():
    index = _WEB_DIR / "index.html"
    if index.exists():
        from fastapi.responses import FileResponse
        return FileResponse(str(index))
    return JSONResponse({"name": "Marg", "version": __version__, "docs": "/docs"})
