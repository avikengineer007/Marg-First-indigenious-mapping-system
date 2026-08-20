"""
/route endpoint — point-to-point and multi-waypoint routing.

Accepts a 'profile' parameter (foot | car | bike).
Dispatches to OSRM if configured, otherwise falls back to the
built-in local graph router.

Fail-closed: returns a structured error if no route can be found.
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Query  # type: ignore
from pydantic import BaseModel

from marg.api.validators import parse_coordinate_pair, validate_profile
from marg.engine.osrm_client import OsrmClient
from marg.engine.graph_router import GraphRouter
from marg.config import settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/route", tags=["Routing"])


# ── Response models ──────────────────────────────────────────────────────────

class RouteStep(BaseModel):
    instruction: str
    distance_m: float
    duration_s: float
    maneuver: str
    geometry: dict | None = None  # GeoJSON LineString for this step


class RouteResponse(BaseModel):
    status: Literal["ok", "no_route"] = "ok"
    profile: str
    distance_m: float
    duration_s: float
    geometry: dict   # GeoJSON LineString of full route
    steps: list[RouteStep] = []
    waypoints: list[dict] = []


class RouteErrorResponse(BaseModel):
    status: Literal["no_route", "error"]
    detail: str


# ── Route handler ─────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=RouteResponse | RouteErrorResponse,
    summary="Calculate a route between two coordinates",
    description=(
        "Returns the optimal route between `start` and `end` for the given "
        "`profile`. Both coordinates must fall within India's bounding box. "
        "Returns `status: no_route` (not an HTTP error) if no path exists."
    ),
)
async def get_route(
    start: Annotated[
        str,
        Query(description="Start coordinate as 'lat,lon' (e.g. 12.9352,77.6245)"),
    ],
    end: Annotated[
        str,
        Query(description="End coordinate as 'lat,lon' (e.g. 12.9716,77.5946)"),
    ],
    profile: Annotated[
        str,
        Query(description="Routing profile: foot | car | bike"),
    ] = "car",
    steps: Annotated[
        bool,
        Query(description="Include turn-by-turn navigation steps"),
    ] = True,
    overview: Annotated[
        Literal["full", "simplified", "false"],
        Query(description="Geometry overview detail level"),
    ] = "full",
) -> RouteResponse | RouteErrorResponse:
    # Validate inputs
    profile = validate_profile(profile)
    start_lat, start_lon = parse_coordinate_pair(start, "start")
    end_lat, end_lon = parse_coordinate_pair(end, "end")

    # Select backend
    osrm_url = settings.osrm_url_for_profile(profile)
    if osrm_url:
        client = OsrmClient(base_url=osrm_url, profile=profile)
        result = await client.route(
            start=(start_lat, start_lon),
            end=(end_lat, end_lon),
            steps=steps,
            overview=overview,
        )
    else:
        log.debug("No OSRM URL configured for profile '%s'; using local graph router.", profile)
        router_engine = GraphRouter(profile=profile)
        result = await router_engine.route(
            start=(start_lat, start_lon),
            end=(end_lat, end_lon),
            steps=steps,
        )

    if result is None:
        return RouteErrorResponse(
            status="no_route",
            detail="No route found between the specified coordinates for this profile.",
        )

    return result
