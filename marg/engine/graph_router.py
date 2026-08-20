"""
Local graph router — deterministic fallback routing engine.

Used when OSRM is not configured (development, offline, early pilot setup).
Implements a Haversine-based A* over a simple road graph loaded from
a lightweight local data format (GeoJSON edge list or OSM-derived SQLite).

For production routing use OSRM containers (see docker-compose.yml).
This router exists to make the API functional immediately without Docker.

Profile-specific speed limits (km/h):
  car:  motorway=110, trunk=85, primary=60, secondary=50, residential=30
  foot: all passable ways at 5 km/h; motorway/trunk excluded
  bike: all cycleable ways at 15 km/h; motorway excluded
"""

from __future__ import annotations

import heapq
import logging
import math
from typing import Literal

log = logging.getLogger(__name__)

# ── Profile speed tables (km/h) ───────────────────────────────────────────────

_SPEEDS: dict[str, dict[str, float]] = {
    "car": {
        "motorway": 110.0,
        "trunk": 85.0,
        "primary": 60.0,
        "secondary": 50.0,
        "tertiary": 40.0,
        "residential": 30.0,
        "living_street": 15.0,
        "service": 20.0,
        "unclassified": 30.0,
    },
    "foot": {
        "primary": 5.0,
        "secondary": 5.0,
        "tertiary": 5.0,
        "residential": 5.0,
        "living_street": 5.0,
        "service": 5.0,
        "unclassified": 5.0,
        "footway": 5.0,
        "path": 4.0,
        "steps": 2.0,
        "pedestrian": 5.0,
    },
    "bike": {
        "primary": 20.0,
        "secondary": 18.0,
        "tertiary": 16.0,
        "residential": 15.0,
        "living_street": 10.0,
        "service": 12.0,
        "cycleway": 20.0,
        "path": 12.0,
        "unclassified": 14.0,
    },
}

_DEFAULT_SPEED: dict[str, float] = {"car": 30.0, "foot": 5.0, "bike": 15.0}


# ── Haversine distance ────────────────────────────────────────────────────────

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two lat/lon points."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ── Graph data structure ──────────────────────────────────────────────────────

class RoadGraph:
    """
    Minimalist directed graph representation for local routing.

    Nodes: indexed by integer ID, with (lat, lon) coordinates.
    Edges: (from_node, to_node, distance_m, highway_tag)
    """

    def __init__(self) -> None:
        self.nodes: dict[int, tuple[float, float]] = {}   # id -> (lat, lon)
        self.adjacency: dict[int, list[tuple[int, float, float]]] = {}
        # adjacency[from_id] = [(to_id, distance_m, speed_kmh)]

    def add_node(self, node_id: int, lat: float, lon: float) -> None:
        self.nodes[node_id] = (lat, lon)
        if node_id not in self.adjacency:
            self.adjacency[node_id] = []

    def add_edge(
        self,
        from_id: int,
        to_id: int,
        highway: str = "unclassified",
        profile: str = "car",
        bidirectional: bool = True,
    ) -> None:
        if from_id not in self.nodes or to_id not in self.nodes:
            return
        lat1, lon1 = self.nodes[from_id]
        lat2, lon2 = self.nodes[to_id]
        dist = _haversine_m(lat1, lon1, lat2, lon2)
        speed = _SPEEDS.get(profile, {}).get(highway, _DEFAULT_SPEED.get(profile, 30.0))
        self.adjacency.setdefault(from_id, []).append((to_id, dist, speed))
        if bidirectional:
            self.adjacency.setdefault(to_id, []).append((from_id, dist, speed))

    def nearest_node(self, lat: float, lon: float) -> int | None:
        """Return the node closest to (lat, lon)."""
        if not self.nodes:
            return None
        return min(
            self.nodes,
            key=lambda nid: _haversine_m(lat, lon, self.nodes[nid][0], self.nodes[nid][1]),
        )

    def astar(
        self, start_id: int, end_id: int
    ) -> tuple[list[int], float, float] | None:
        """
        A* shortest path from start_id to end_id.

        Returns (path_node_ids, total_distance_m, total_duration_s) or None.
        """
        if start_id not in self.nodes or end_id not in self.nodes:
            return None

        end_lat, end_lon = self.nodes[end_id]

        def heuristic(nid: int) -> float:
            lat, lon = self.nodes[nid]
            # Optimistic travel time at 130 km/h as heuristic upper bound
            return _haversine_m(lat, lon, end_lat, end_lon) / (130 / 3.6)

        # Priority queue: (f_score, node_id)
        heap: list[tuple[float, int]] = [(heuristic(start_id), start_id)]
        g_score: dict[int, float] = {start_id: 0.0}
        came_from: dict[int, int] = {}

        while heap:
            _, current = heapq.heappop(heap)
            if current == end_id:
                # Reconstruct path
                path = []
                node = end_id
                while node in came_from:
                    path.append(node)
                    node = came_from[node]
                path.append(start_id)
                path.reverse()

                total_dist = g_score[end_id]
                # Estimate duration from total distance at profile default speed
                # (a rough approximation — per-edge durations would be more accurate)
                total_dur = total_dist / (_DEFAULT_SPEED.get("car", 30) / 3.6)
                return path, total_dist, total_dur

            for neighbor, dist_m, speed_kmh in self.adjacency.get(current, []):
                duration_s = dist_m / (speed_kmh / 3.6)
                tentative_g = g_score[current] + duration_s
                if tentative_g < g_score.get(neighbor, float("inf")):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f = tentative_g + heuristic(neighbor)
                    heapq.heappush(heap, (f, neighbor))

        return None  # No path found


# ── High-level router interface ───────────────────────────────────────────────

class GraphRouter:
    """
    Local graph-based routing engine.

    On first route request, attempts to load a pre-built graph from
    data/graphs/{profile}.pkl. If not found, returns None (no-route).
    Use `marg data build --region <region>` to generate graph files.
    """

    def __init__(self, profile: str) -> None:
        self.profile = profile
        self._graph: RoadGraph | None = None

    def _load_graph(self) -> RoadGraph | None:
        import pickle
        from pathlib import Path

        graph_path = Path(f"./data/graphs/{self.profile}.pkl")
        if not graph_path.exists():
            log.warning(
                "Local routing graph not found at %s. "
                "Run `marg data build --region <region>` to generate it.",
                graph_path,
            )
            return None
        try:
            with open(graph_path, "rb") as f:
                return pickle.load(f)
        except Exception as exc:
            log.warning("Failed to load graph at %s: %s", graph_path, exc)
            return None

    async def route(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        steps: bool = True,
    ) -> dict | None:
        if self._graph is None:
            self._graph = self._load_graph()
        if self._graph is None:
            return None

        start_node = self._graph.nearest_node(*start)
        end_node = self._graph.nearest_node(*end)
        if start_node is None or end_node is None:
            return None

        result = self._graph.astar(start_node, end_node)
        if result is None:
            return None

        path_ids, dist_m, dur_s = result

        # Build GeoJSON LineString geometry from path nodes
        coordinates = [
            [self._graph.nodes[nid][1], self._graph.nodes[nid][0]]  # [lon, lat]
            for nid in path_ids
        ]
        geometry = {"type": "LineString", "coordinates": coordinates}

        route_steps: list[dict] = []
        if steps and len(path_ids) > 1:
            # Simple step generation: one step per consecutive pair
            for i in range(len(path_ids) - 1):
                n0, n1 = path_ids[i], path_ids[i + 1]
                lat0, lon0 = self._graph.nodes[n0]
                lat1, lon1 = self._graph.nodes[n1]
                d = _haversine_m(lat0, lon0, lat1, lon1)
                route_steps.append({
                    "instruction": "Continue",
                    "distance_m": round(d, 1),
                    "duration_s": round(d / (_DEFAULT_SPEED[self.profile] / 3.6), 1),
                    "maneuver": "continue",
                    "geometry": None,
                })

        return {
            "status": "ok",
            "profile": self.profile,
            "distance_m": round(dist_m, 1),
            "duration_s": round(dur_s, 1),
            "geometry": geometry,
            "steps": route_steps if steps else [],
            "waypoints": [
                {"name": "Start", "lat": start[0], "lon": start[1]},
                {"name": "End", "lat": end[0], "lon": end[1]},
            ],
        }
