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

from marg.api.validators import parse_coordinate_pair, validate_profile, validate_india_coordinate
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


class TrackRequest(BaseModel):
    lat: float
    lon: float
    destination: str
    profile: str = "car"
    timestamp_ms: int | None = None
    route_geometry: dict | None = None
    off_route_threshold_m: float = 50.0
    snapping_radius_m: float = 1000.0
    steps: bool = True
    overview: Literal["full", "simplified", "false"] = "full"


class TrackResponse(BaseModel):
    status: Literal["ok", "no_route", "error"] = "ok"
    off_route: bool
    distance_to_route_m: float
    message: str
    reroute: RouteResponse | None = None


# ── Geometry helpers ─────────────────────────────────────────────────────────

def _point_to_segment_distance_m(
    plat: float, plon: float, lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Compute distance in meters from point P to line segment (P1, P2) using planar equirectangular projection."""
    import math
    mean_lat_rad = math.radians((lat1 + lat2 + plat) / 3.0)
    kx = math.cos(mean_lat_rad) * 111319.5
    ky = 111319.5

    x1, y1 = lon1 * kx, lat1 * ky
    x2, y2 = lon2 * kx, lat2 * ky
    px, py = plon * kx, plat * ky

    dx = x2 - x1
    dy = y2 - y1
    seg_len_sq = dx * dx + dy * dy

    if seg_len_sq == 0.0:
        return math.sqrt((px - x1) ** 2 + (py - y1) ** 2)

    # Projection factor t clamped to [0, 1]
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy

    return math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)


def point_to_linestring_distance_m(lat: float, lon: float, coordinates: list[list[float]]) -> float:
    """
    Compute the minimum orthogonal distance in meters between (lat, lon)
    and a GeoJSON coordinates array of [[lon, lat], ...].
    """
    if not coordinates:
        return 0.0
    if len(coordinates) == 1:
        c_lon, c_lat = coordinates[0]
        from marg.engine.graph_router import _haversine_m
        return _haversine_m(lat, lon, c_lat, c_lon)

    min_dist = float("inf")
    for i in range(len(coordinates) - 1):
        lon1, lat1 = coordinates[i]
        lon2, lat2 = coordinates[i + 1]
        dist = _point_to_segment_distance_m(lat, lon, lat1, lon1, lat2, lon2)
        if dist < min_dist:
            min_dist = dist
            if min_dist == 0.0:
                break
    return min_dist


# ── Route handlers ────────────────────────────────────────────────────────────

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
    radius_m: Annotated[
        float,
        Query(description="Maximum coordinate snapping radius in meters"),
    ] = 1000.0,
) -> RouteResponse | RouteErrorResponse:
    # Validate inputs
    profile = validate_profile(profile)
    start_lat, start_lon = parse_coordinate_pair(start, "start")
    end_lat, end_lon = parse_coordinate_pair(end, "end")

    # Select backend
    result = None
    osrm_url = settings.osrm_url_for_profile(profile)
    client = OsrmClient(base_url=osrm_url or "", profile=profile)
    snapping_radiuses = f"{int(radius_m)};{int(radius_m)}"
    result = await client.route(
        start=(start_lat, start_lon),
        end=(end_lat, end_lon),
        steps=steps,
        overview=overview,
        radiuses=snapping_radiuses,
    )

    if result is None:
        log.debug("OSRM backend unavailable or no route for profile '%s'; using local graph router.", profile)
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

    return RouteResponse(**result)


@router.post(
    "/track",
    response_model=TrackResponse | RouteErrorResponse,
    summary="Real-time live position tracking and off-route recalculation",
    description=(
        "Accepts current device position (lat, lon) against an active trip. "
        "Deterministically checks deviation against the active route polyline. "
        "If deviation exceeds `off_route_threshold_m`, triggers a re-route calculation "
        "to the destination.\n\n"
        "**Privacy Guarantee:** Position data is processed strictly in-memory per request "
        "and is never stored, logged as raw coordinates, or persisted to any database."
    ),
)
async def track_route(payload: TrackRequest) -> TrackResponse | RouteErrorResponse:
    # 1. Fail-closed validation for coordinates & parameters
    validate_india_coordinate(payload.lat, payload.lon, "current position")
    dest_lat, dest_lon = parse_coordinate_pair(payload.destination, "destination")
    profile = validate_profile(payload.profile)

    # 2. Check if active polyline is provided
    coords: list[list[float]] = []
    if payload.route_geometry and isinstance(payload.route_geometry, dict):
        coords = payload.route_geometry.get("coordinates", [])

    is_off_route = False
    distance_to_route = 0.0

    if coords and len(coords) >= 2:
        distance_to_route = point_to_linestring_distance_m(payload.lat, payload.lon, coords)
        if distance_to_route > payload.off_route_threshold_m:
            is_off_route = True
    elif not coords:
        # If no active route geometry was provided, compute initial route from current pos to destination
        is_off_route = True

    reroute_res: RouteResponse | None = None

    if is_off_route:
        # Log generic event without leaking raw GPS coordinates
        log.debug("Off-route detected (deviation=%.1fm, profile=%s). Recalculating route.", distance_to_route, profile)

        raw_route = None
        osrm_url = settings.osrm_url_for_profile(profile)
        client = OsrmClient(base_url=osrm_url or "", profile=profile)
        snapping_radiuses = f"{int(payload.snapping_radius_m)};{int(payload.snapping_radius_m)}"
        raw_route = await client.route(
            start=(payload.lat, payload.lon),
            end=(dest_lat, dest_lon),
            steps=payload.steps,
            overview=payload.overview,
            radiuses=snapping_radiuses,
        )

        if raw_route is None:
            router_engine = GraphRouter(profile=profile)
            raw_route = await router_engine.route(
                start=(payload.lat, payload.lon),
                end=(dest_lat, dest_lon),
                steps=payload.steps,
            )

        if raw_route is not None:
            reroute_res = RouteResponse(**raw_route)
            return TrackResponse(
                status="ok",
                off_route=True,
                distance_to_route_m=round(distance_to_route, 1),
                message="Off-route detected. New route calculated.",
                reroute=reroute_res,
            )
        else:
            return TrackResponse(
                status="no_route",
                off_route=True,
                distance_to_route_m=round(distance_to_route, 1),
                message="Off-route detected, but no route found between coordinates.",
                reroute=None,
            )

    return TrackResponse(
        status="ok",
        off_route=False,
        distance_to_route_m=round(distance_to_route, 1),
        message="On track.",
        reroute=None,
    )

