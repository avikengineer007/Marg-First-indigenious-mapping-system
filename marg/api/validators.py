"""
Input validation for all Marg API endpoints.

All validators are fail-closed: if a value cannot be confidently validated,
a clear 422/400 is raised rather than passing ambiguous input downstream.
"""

from __future__ import annotations

import re
from typing import Literal

# pyrefly: ignore [missing-import]
from fastapi import HTTPException  # type: ignore

from marg.config import settings

# ── Constants ────────────────────────────────────────────────────────────────

VALID_PROFILES: frozenset[str] = frozenset({"foot", "car", "bike"})

# Characters not expected in place-name search queries
_SEARCH_INJECTION_RE = re.compile(r"[<>{}\[\]\\;`'\"$()]")


# Maximum length for free-text query fields
_MAX_QUERY_LEN = 256

# ── Coordinate validation ─────────────────────────────────────────────────────


def validate_india_coordinate(lat: float, lon: float, field_name: str = "coordinate") -> None:
    """
    Raise HTTP 400 if (lat, lon) falls outside India's geographic bounding box.

    India bbox: lat 6.0–37.5°N, lon 68.0–97.5°E
    """
    if not (settings.INDIA_MIN_LAT <= lat <= settings.INDIA_MAX_LAT):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{field_name} latitude {lat} is outside India "
                f"({settings.INDIA_MIN_LAT}–{settings.INDIA_MAX_LAT}°N)."
            ),
        )
    if not (settings.INDIA_MIN_LON <= lon <= settings.INDIA_MAX_LON):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{field_name} longitude {lon} is outside India "
                f"({settings.INDIA_MIN_LON}–{settings.INDIA_MAX_LON}°E)."
            ),
        )


def parse_coordinate_pair(raw: str, field_name: str = "coordinate") -> tuple[float, float]:
    """
    Parse a 'lat,lon' string and return (lat, lon) floats.

    Raises HTTP 400 on any parse failure.
    """
    parts = raw.strip().split(",")
    if len(parts) != 2:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be in 'lat,lon' format (e.g. '12.9352,77.6245').",
        )
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} contains non-numeric values.",
        )
    # Range check (world bounds before India check)
    if not (-90 <= lat <= 90):
        raise HTTPException(status_code=400, detail=f"{field_name} latitude {lat} is out of range [-90, 90].")
    if not (-180 <= lon <= 180):
        raise HTTPException(status_code=400, detail=f"{field_name} longitude {lon} is out of range [-180, 180].")
    validate_india_coordinate(lat, lon, field_name)
    return lat, lon


# ── Profile validation ────────────────────────────────────────────────────────


def validate_profile(profile: str) -> Literal["foot", "car", "bike"]:
    """Raise HTTP 400 if profile is not one of foot/car/bike."""
    if profile not in VALID_PROFILES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid profile '{profile}'. Must be one of: {sorted(VALID_PROFILES)}.",
        )
    return profile  # type: ignore[return-value]


# ── Text query sanitization ───────────────────────────────────────────────────


def sanitize_text_query(q: str, field_name: str = "q") -> str:
    """
    Reject injection patterns and excessive-length strings in free-text fields.

    Does NOT normalise the string beyond stripping leading/trailing whitespace —
    normalisation is the geocoder's responsibility.
    """
    q = q.strip()
    if not q:
        raise HTTPException(status_code=400, detail=f"'{field_name}' must not be empty.")
    if len(q) > _MAX_QUERY_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"'{field_name}' exceeds maximum length of {_MAX_QUERY_LEN} characters.",
        )
    if _SEARCH_INJECTION_RE.search(q):
        raise HTTPException(
            status_code=400,
            detail=f"'{field_name}' contains disallowed characters.",
        )
    return q


# ── Tile coordinate validation ────────────────────────────────────────────────


def validate_tile_coords(z: int, x: int, y: int) -> None:
    """Validate standard slippy-map tile coordinates."""
    if not (0 <= z <= 22):
        raise HTTPException(status_code=400, detail=f"Zoom level {z} is out of range [0, 22].")
    max_tile = 2**z
    if not (0 <= x < max_tile):
        raise HTTPException(status_code=400, detail=f"Tile x={x} is out of range for zoom {z}.")
    if not (0 <= y < max_tile):
        raise HTTPException(status_code=400, detail=f"Tile y={y} is out of range for zoom {z}.")


# ── Telemetry payload validation ──────────────────────────────────────────────


def validate_telemetry_speed(speed_kmh: float) -> None:
    """Reject physically implausible speed values."""
    if not (0.0 <= speed_kmh <= 250.0):
        raise HTTPException(
            status_code=400,
            detail=f"Speed {speed_kmh} km/h is outside plausible range [0, 250].",
        )
