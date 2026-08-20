"""
/search endpoint — POI and place keyword search within India.

Supports optional proximity bias via near_lat/near_lon and
category filtering via OSM tag keys (amenity, shop, highway…).
"""

from __future__ import annotations

import logging
from typing import Annotated

# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Query  # type: ignore
from pydantic import BaseModel

from marg.api.validators import (
    sanitize_text_query,
    validate_india_coordinate,
)
from marg.engine.geocoder import Geocoder

log = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["Search"])


# ── Response models ──────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    name: str
    display_name: str
    lat: float
    lon: float
    category: str | None = None    # e.g. "amenity", "shop"
    type: str | None = None        # e.g. "hospital", "supermarket"
    distance_m: float | None = None  # populated when near_lat/near_lon given


class SearchResponse(BaseModel):
    status: str = "ok"
    query: str
    results: list[SearchResult]


# ── Handler ───────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=SearchResponse,
    summary="POI / place keyword search within India",
    description=(
        "Search for points of interest or places by name/keyword. "
        "Optionally filter by OSM category and bias results by proximity."
    ),
)
async def search_places(
    q: Annotated[str, Query(description="Search keyword or POI name (e.g. 'hospital near MG Road')")],
    category: Annotated[
        str | None,
        Query(description="OSM tag key to filter by (e.g. amenity, shop, tourism)"),
    ] = None,
    category_value: Annotated[
        str | None,
        Query(description="OSM tag value to filter by (e.g. hospital, supermarket)"),
    ] = None,
    near_lat: Annotated[
        float | None,
        Query(description="Proximity bias latitude — results sorted closer to this point"),
    ] = None,
    near_lon: Annotated[
        float | None,
        Query(description="Proximity bias longitude"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=20, description="Maximum number of results")] = 10,
) -> SearchResponse:
    q = sanitize_text_query(q, "q")

    # If proximity bias provided, validate it's within India
    if near_lat is not None and near_lon is not None:
        validate_india_coordinate(near_lat, near_lon, "near")

    if category is not None:
        category = sanitize_text_query(category, "category")
    if category_value is not None:
        category_value = sanitize_text_query(category_value, "category_value")

    geocoder = Geocoder()
    results = await geocoder.search(
        q=q,
        category=category,
        category_value=category_value,
        near=(near_lat, near_lon) if near_lat is not None and near_lon is not None else None,
        limit=limit,
    )
    return SearchResponse(query=q, results=results)
