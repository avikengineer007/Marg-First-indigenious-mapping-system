"""
OSRM HTTP client adapter.

Wraps OSRM's HTTP API (v5) for route, nearest, and table requests.
Each routing profile (foot, car, bike) runs as a separate OSRM instance
behind a different base URL.

See: http://project-osrm.org/docs/v5.24.0/api/
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import httpx

log = logging.getLogger(__name__)

# OSRM profile → OSRM service profile string
_PROFILE_MAP = {
    "foot": "foot",
    "car": "driving",
    "bike": "cycling",
}


class OsrmClient:
    """Async HTTP client for an OSRM backend instance."""

    def __init__(self, base_url: str, profile: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.profile = profile
        self._osrm_profile = _PROFILE_MAP.get(profile, profile)
        self.timeout = timeout

    def _coord_str(self, lat: float, lon: float) -> str:
        # OSRM expects lon,lat order
        return f"{lon},{lat}"

    async def route(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        steps: bool = True,
        overview: Literal["full", "simplified", "false"] = "full",
        radiuses: str = "1000;1000",
    ) -> dict | None:
        """
        Fetch a route from OSRM.

        Returns a dict matching RouteResponse structure, or None if no route found.
        """
        coords = ";".join([
            self._coord_str(*start),
            self._coord_str(*end),
        ])
        url = (
            f"{self.base_url}/route/v1/{self._osrm_profile}/{coords}"
            f"?steps={'true' if steps else 'false'}"
            f"&overview={overview}"
            f"&geometries=geojson"
            f"&annotations=false"
            f"&radiuses={radiuses}"
        )

        resp = None
        # 1. Try configured local backend if specified
        if self.base_url:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    r = await client.get(url)
                    if r.status_code == 200:
                        resp = r
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                log.debug("Local OSRM unreachable at %s (%s); trying upstream OSM routing.", self.base_url, exc)

        # 2. Fallback to upstream OpenStreetMap routing servers (profile-specific)
        if resp is None:
            if self.profile == "foot":
                upstream_urls = [
                    f"https://routing.openstreetmap.de/routed-foot/route/v1/driving/{coords}?steps={'true' if steps else 'false'}&overview={overview}&geometries=geojson&annotations=false&radiuses={radiuses}"
                ]
            elif self.profile == "bike":
                upstream_urls = [
                    f"https://routing.openstreetmap.de/routed-bike/route/v1/driving/{coords}?steps={'true' if steps else 'false'}&overview={overview}&geometries=geojson&annotations=false&radiuses={radiuses}"
                ]
            else:
                upstream_urls = [
                    f"https://router.project-osrm.org/route/v1/driving/{coords}?steps={'true' if steps else 'false'}&overview={overview}&geometries=geojson&annotations=false&radiuses={radiuses}",
                    f"https://routing.openstreetmap.de/routed-car/route/v1/driving/{coords}?steps={'true' if steps else 'false'}&overview={overview}&geometries=geojson&annotations=false&radiuses={radiuses}",
                ]

            for u in upstream_urls:
                try:
                    async with httpx.AsyncClient(timeout=12.0) as client:
                        r = await client.get(u, headers={"User-Agent": "marg-mapping-engine/0.1.0"})
                        if r.status_code == 200:
                            resp = r
                            break
                except Exception as exc:
                    log.debug("Upstream routing attempt failed for %s: %s", u, exc)

        if resp is None:
            log.warning("No OSRM service available for profile '%s'", self.profile)
            return None

        data: dict[str, Any] = resp.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            log.debug("OSRM returned code=%s for profile '%s'", data.get("code"), self.profile)
            return None

        osrm_route = data["routes"][0]
        geometry = osrm_route.get("geometry", {})

        distance_m = osrm_route.get("distance", 0)
        raw_duration_s = osrm_route.get("duration", 0)

        # Ensure duration reflects physical profile speeds:
        # Foot: 5.0 km/h (~1.39 m/s) -> ~12 min/km
        # Bike: 15.0 km/h (~4.17 m/s) -> ~4 min/km
        # Car: OSM driving speeds
        if self.profile == "foot":
            calculated_duration_s = distance_m / (5.0 / 3.6)
            duration_s = calculated_duration_s if raw_duration_s < (distance_m / (8.0 / 3.6)) else raw_duration_s
        elif self.profile == "bike":
            calculated_duration_s = distance_m / (15.0 / 3.6)
            duration_s = calculated_duration_s if raw_duration_s < (distance_m / (25.0 / 3.6)) else raw_duration_s
        else:
            duration_s = raw_duration_s

        route_steps = []
        if steps:
            for leg in osrm_route.get("legs", []):
                for step in leg.get("steps", []):
                    maneuver = step.get("maneuver", {})
                    step_dist = step.get("distance", 0)
                    step_dur = step.get("duration", 0)
                    if self.profile == "foot" and (step_dur < step_dist / (8.0 / 3.6)):
                        step_dur = step_dist / (5.0 / 3.6)
                    elif self.profile == "bike" and (step_dur < step_dist / (25.0 / 3.6)):
                        step_dur = step_dist / (15.0 / 3.6)

                    route_steps.append({
                        "instruction": _format_instruction(maneuver, step),
                        "distance_m": round(step_dist, 1),
                        "duration_s": round(step_dur, 1),
                        "maneuver": maneuver.get("type", ""),
                        "geometry": step.get("geometry"),
                    })

        waypoints = [
            {
                "name": wp.get("name", ""),
                "lat": wp["location"][1],
                "lon": wp["location"][0],
            }
            for wp in data.get("waypoints", [])
        ]

        return {
            "status": "ok",
            "profile": self.profile,
            "distance_m": round(distance_m, 1),
            "duration_s": round(duration_s, 1),
            "geometry": geometry,
            "steps": route_steps,
            "waypoints": waypoints,
        }

    async def nearest(
        self, lat: float, lon: float, number: int = 1
    ) -> list[dict] | None:
        """Snap a coordinate to the nearest road segment."""
        url = (
            f"{self.base_url}/nearest/v1/{self._osrm_profile}/"
            f"{self._coord_str(lat, lon)}?number={number}"
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") != "Ok":
                    return None
                return [
                    {
                        "name": wp.get("name", ""),
                        "lat": wp["location"][1],
                        "lon": wp["location"][0],
                        "distance_m": wp.get("distance", 0),
                    }
                    for wp in data.get("waypoints", [])
                ]
        except Exception as exc:
            log.warning("OSRM nearest error: %s", exc)
            return None


def _format_instruction(maneuver: dict, step: dict) -> str:
    """
    Build a human-readable instruction string from an OSRM maneuver.
    """
    maneuver_type = maneuver.get("type", "")
    modifier = maneuver.get("modifier", "")
    road_name = step.get("name", "")

    phrases = {
        "depart": f"Head {modifier} on {road_name}" if road_name else f"Head {modifier}",
        "arrive": "You have arrived at your destination",
        "turn": f"Turn {modifier}" + (f" onto {road_name}" if road_name else ""),
        "new name": f"Continue onto {road_name}" if road_name else "Continue",
        "merge": f"Merge {modifier}" + (f" onto {road_name}" if road_name else ""),
        "roundabout": f"Enter the roundabout",
        "exit roundabout": f"Exit the roundabout" + (f" onto {road_name}" if road_name else ""),
        "fork": f"Keep {modifier}" + (f" onto {road_name}" if road_name else ""),
        "continue": f"Continue {modifier}" + (f" on {road_name}" if road_name else ""),
    }
    return phrases.get(maneuver_type, maneuver_type.replace("-", " ").capitalize())
