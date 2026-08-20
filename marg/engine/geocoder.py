"""
Hybrid geocoder adapter.

Dispatch order:
  1. Self-hosted Nominatim (if MARG_NOMINATIM_URL is set)
  2. Local SQLite FTS5 index (./data/geocode.db) as fallback

All results are strictly bounded to India (country_codes=in for Nominatim).
The local FTS5 index is built by `marg data build --region <region>`.
"""

from __future__ import annotations

import logging
import math
import sqlite3
from pathlib import Path
from typing import Any

import httpx

from marg.config import settings

log = logging.getLogger(__name__)


class Geocoder:
    """Hybrid forward/reverse geocoder for India."""

    def __init__(self) -> None:
        self._nominatim_url = settings.nominatim_url.rstrip("/") if settings.nominatim_url else ""
        self._db_path = Path(settings.geocode_db_path)

    # ── Forward geocoding ──────────────────────────────────────────────────

    async def forward(self, q: str, limit: int = 5) -> list[dict]:
        """Convert a text query to a list of geocoding results."""
        if self._nominatim_url:
            results = await self._nominatim_search(q=q, limit=limit)
            if results:
                return results

        # Local FTS5 fallback
        return self._local_search(q=q, limit=limit)

    async def search(
        self,
        q: str,
        category: str | None = None,
        category_value: str | None = None,
        near: tuple[float, float] | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """POI/place search with optional category filter and proximity bias."""
        if self._nominatim_url:
            results = await self._nominatim_search(
                q=q,
                limit=limit,
                category=category,
                category_value=category_value,
            )
            if results:
                if near:
                    results = _sort_by_distance(results, near)
                return results[:limit]

        results = self._local_search(q=q, limit=limit * 2, category=category)
        if near:
            results = _sort_by_distance(results, near)
        return results[:limit]

    async def reverse(self, lat: float, lon: float) -> dict | None:
        """Convert coordinates to the nearest address."""
        if self._nominatim_url:
            result = await self._nominatim_reverse(lat=lat, lon=lon)
            if result:
                return result

        return self._local_reverse(lat=lat, lon=lon)

    # ── Nominatim backend ──────────────────────────────────────────────────

    async def _nominatim_search(
        self,
        q: str,
        limit: int = 5,
        category: str | None = None,
        category_value: str | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {
            "q": q,
            "format": "json",
            "addressdetails": 1,
            "limit": limit,
            "countrycodes": "in",   # India-only
        }
        if category and category_value:
            # Nominatim structured query
            params[category] = category_value

        try:
            async with httpx.AsyncClient(
                timeout=8.0,
                headers={"User-Agent": settings.nominatim_user_agent},
            ) as client:
                resp = await client.get(f"{self._nominatim_url}/search", params=params)
                resp.raise_for_status()
                data: list[dict] = resp.json()
        except Exception as exc:
            log.warning("Nominatim search failed: %s", exc)
            return []

        return [_nominatim_to_result(item) for item in data]

    async def _nominatim_reverse(self, lat: float, lon: float) -> dict | None:
        params = {
            "lat": lat,
            "lon": lon,
            "format": "json",
            "addressdetails": 1,
            "zoom": 18,
        }
        try:
            async with httpx.AsyncClient(
                timeout=8.0,
                headers={"User-Agent": settings.nominatim_user_agent},
            ) as client:
                resp = await client.get(f"{self._nominatim_url}/reverse", params=params)
                resp.raise_for_status()
                data: dict = resp.json()
                if "error" in data:
                    return None
                return {
                    "status": "ok",
                    "display_name": data.get("display_name", ""),
                    "lat": float(data.get("lat", lat)),
                    "lon": float(data.get("lon", lon)),
                    "address": data.get("address", {}),
                }
        except Exception as exc:
            log.warning("Nominatim reverse failed: %s", exc)
            return None

    # ── Local SQLite FTS5 fallback ─────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection | None:
        if not self._db_path.exists():
            log.debug("Local geocode DB not found at %s", self._db_path)
            return None
        return sqlite3.connect(str(self._db_path))

    def _local_search(
        self, q: str, limit: int = 10, category: str | None = None
    ) -> list[dict]:
        conn = self._get_conn()
        if conn is None:
            return []
        try:
            # Expect table: places(id, name, display_name, lat, lon, category, type)
            # with FTS5 virtual table: places_fts
            sql = """
                SELECT p.name, p.display_name, p.lat, p.lon, p.category, p.type
                FROM places p
                JOIN places_fts f ON p.rowid = f.rowid
                WHERE places_fts MATCH ?
            """
            params: list[Any] = [f"{q}*"]
            if category:
                sql += " AND p.category = ?"
                params.append(category)
            sql += " LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "name": r[0],
                    "display_name": r[1],
                    "lat": r[2],
                    "lon": r[3],
                    "category": r[4],
                    "type": r[5],
                }
                for r in rows
            ]
        except Exception as exc:
            log.warning("Local FTS5 search error: %s", exc)
            return []
        finally:
            conn.close()

    def _local_reverse(self, lat: float, lon: float) -> dict | None:
        conn = self._get_conn()
        if conn is None:
            return None
        try:
            # Nearest place by Euclidean approximation (good enough for < 10km)
            rows = conn.execute(
                "SELECT name, display_name, lat, lon, category, type FROM places"
            ).fetchall()
            if not rows:
                return None
            nearest = min(
                rows,
                key=lambda r: (r[2] - lat) ** 2 + (r[3] - lon) ** 2,
            )
            return {
                "status": "ok",
                "display_name": nearest[1] or nearest[0],
                "lat": nearest[2],
                "lon": nearest[3],
                "address": {"name": nearest[0], "type": nearest[5]},
            }
        except Exception as exc:
            log.warning("Local reverse geocode error: %s", exc)
            return None
        finally:
            conn.close()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _nominatim_to_result(item: dict) -> dict:
    bbox = item.get("boundingbox")
    return {
        "name": item.get("name", ""),
        "display_name": item.get("display_name", ""),
        "lat": float(item.get("lat", 0)),
        "lon": float(item.get("lon", 0)),
        "bbox": [float(b) for b in bbox] if bbox else None,
        "place_id": str(item.get("place_id", "")),
        "place_type": item.get("type"),
        "address": item.get("address"),
        "category": item.get("category"),
    }


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _sort_by_distance(results: list[dict], near: tuple[float, float]) -> list[dict]:
    near_lat, near_lon = near
    for r in results:
        r["distance_m"] = round(_haversine_m(r["lat"], r["lon"], near_lat, near_lon), 1)
    return sorted(results, key=lambda r: r.get("distance_m", float("inf")))
