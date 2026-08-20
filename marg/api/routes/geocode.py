"""
/geocode endpoint — forward and reverse geocoding, India-scoped.

Forward:  GET /geocode?q=Koramangala+Bengaluru
Reverse:  GET /geocode/reverse?lat=12.9352&lon=77.6245

Dispatches to self-hosted Nominatim if MARG_NOMINATIM_URL is configured;
falls back to the local SQLite FTS5 index otherwise.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Query  # type: ignore
from pydantic import BaseModel

from marg.api.validators import (
    sanitize_text_query,
    validate_india_coordinate,
)
from marg.engine.geocoder import Geocoder

log = logging.getLogger(__name__)
router = APIRouter(prefix="/geocode", tags=["Geocoding"])


# ── Response models ──────────────────────────────────────────────────────────

class GeocodeResult(BaseModel):
    display_name: str
    lat: float
    lon: float
    bbox: list[float] | None = None   # [min_lat, max_lat, min_lon, max_lon]
    place_id: str | None = None
    place_type: str | None = None
    address: dict | None = None


class GeocodeResponse(BaseModel):
    status: str = "ok"
    results: list[GeocodeResult]


class ReverseGeocodeResponse(BaseModel):
    status: str = "ok"
    display_name: str
    lat: float
    lon: float
    address: dict


# ── Forward geocode ───────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=GeocodeResponse,
    summary="Forward geocoding: address / place name → coordinates",
    description=(
        "Converts a free-text address or place name to one or more coordinates. "
        "Results are strictly scoped to India."
    ),
)
async def forward_geocode(
    q: Annotated[str, Query(description="Place name or address (e.g. 'Koramangala, Bengaluru')")],
    limit: Annotated[int, Query(ge=1, le=10, description="Maximum number of results")] = 5,
) -> GeocodeResponse:
    q = sanitize_text_query(q, "q")
    geocoder = Geocoder()
    results = await geocoder.forward(q=q, limit=limit)
    return GeocodeResponse(results=results)


# ── Reverse geocode ───────────────────────────────────────────────────────────

@router.get(
    "/reverse",
    response_model=ReverseGeocodeResponse,
    summary="Reverse geocoding: coordinates → address",
    description=(
        "Converts a (lat, lon) coordinate to its nearest address. "
        "Coordinates must fall within India's bounding box."
    ),
)
async def reverse_geocode(
    lat: Annotated[float, Query(description="Latitude (e.g. 12.9352)")],
    lon: Annotated[float, Query(description="Longitude (e.g. 77.6245)")],
) -> ReverseGeocodeResponse:
    validate_india_coordinate(lat, lon, "coordinate")
    geocoder = Geocoder()
    result = await geocoder.reverse(lat=lat, lon=lon)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No address found for this location.")
    return result
