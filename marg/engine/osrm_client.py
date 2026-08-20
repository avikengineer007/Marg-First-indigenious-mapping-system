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
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.warning("OSRM HTTP error %s for profile '%s': %s", exc.response.status_code, self.profile, url)
            return None
        except httpx.RequestError as exc:
            log.warning("OSRM request error for profile '%s': %s", self.profile, exc)
            return None

        data: dict[str, Any] = resp.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            log.debug("OSRM returned code=%s for profile '%s'", data.get("code"), self.profile)
            return None

        osrm_route = data["routes"][0]
        geometry = osrm_route.get("geometry", {})

        route_steps = []
        if steps:
            for leg in osrm_route.get("legs", []):
                for step in leg.get("steps", []):
                    maneuver = step.get("maneuver", {})
                    route_steps.append({
                        "instruction": _format_instruction(maneuver, step),
                        "distance_m": step.get("distance", 0),
                        "duration_s": step.get("duration", 0),
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
            "distance_m": osrm_route.get("distance", 0),
            "duration_s": osrm_route.get("duration", 0),
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
