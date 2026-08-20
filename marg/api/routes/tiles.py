"""
/tiles endpoint — vector/raster tile serving.

Serves tiles from a local PMTiles or MBTiles archive.
Falls back to an upstream tile URL (e.g. MapTiler free tier) if configured
and the local archive is not yet populated.

Also provides:
  GET /tiles/style.json  — MapLibre GL style specification
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException, Request  # type: ignore
from fastapi.responses import Response  # type: ignore

from marg.api.validators import validate_tile_coords
from marg.config import settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/tiles", tags=["Tiles"])

# Tile content types
_CONTENT_TYPES = {
    "pbf": "application/x-protobuf",
    "mvt": "application/vnd.mapbox-vector-tile",
    "png": "image/png",
    "jpg": "image/jpeg",
    "webp": "image/webp",
}


def _local_tiles_available() -> bool:
    path = Path(settings.tiles_path)
    return path.exists() and path.stat().st_size > 0


@router.get(
    "/style.json",
    summary="MapLibre GL Style JSON",
    description="Returns the MapLibre GL style JSON for the Marg tile layer.",
)
async def get_style(request: Request) -> dict:
    base = str(request.base_url).rstrip("/")
    return {
        "version": 8,
        "name": "Marg",
        "sources": {
            "marg": {
                "type": "vector",
                "tiles": [f"{base}/tiles/{{z}}/{{x}}/{{y}}.pbf"],
                "minzoom": 0,
                "maxzoom": 14,
            }
        },
        "layers": [
            {
                "id": "background",
                "type": "background",
                "paint": {"background-color": "#f8f4f0"},
            },
            {
                "id": "roads",
                "type": "line",
                "source": "marg",
                "source-layer": "transportation",
                "paint": {
                    "line-color": "#c8a97e",
                    "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.5, 14, 3],
                },
            },
            {
                "id": "buildings",
                "type": "fill",
                "source": "marg",
                "source-layer": "building",
                "paint": {"fill-color": "#e8e0d8", "fill-opacity": 0.8},
            },
            {
                "id": "water",
                "type": "fill",
                "source": "marg",
                "source-layer": "water",
                "paint": {"fill-color": "#a0c8e8"},
            },
        ],
        "glyphs": "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf",
    }


@router.get(
    "/{z}/{x}/{y}.{ext}",
    summary="Map tile",
    description="Returns a vector (pbf/mvt) or raster (png/jpg/webp) map tile.",
    response_class=Response,
)
async def get_tile(z: int, x: int, y: int, ext: str) -> Response:
    validate_tile_coords(z, x, y)

    if ext not in _CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported tile extension '{ext}'. Supported: {list(_CONTENT_TYPES)}.",
        )

    content_type = _CONTENT_TYPES[ext]

    # Try local PMTiles / MBTiles archive first
    if _local_tiles_available():
        tile_data = _read_local_tile(z, x, y)
        if tile_data:
            headers = {
                "Content-Type": content_type,
                "Cache-Control": "public, max-age=3600",
                "Content-Encoding": "gzip",
            }
            return Response(content=tile_data, headers=headers, media_type=content_type)

    # Fallback to upstream tile URL if configured
    if settings.tile_upstream_url:
        import httpx
        upstream = settings.tile_upstream_url.format(z=z, x=x, y=y)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(upstream)
                resp.raise_for_status()
                return Response(
                    content=resp.content,
                    media_type=content_type,
                    headers={"Cache-Control": "public, max-age=3600"},
                )
        except httpx.HTTPError as exc:
            log.warning("Upstream tile fetch failed for %d/%d/%d: %s", z, x, y, exc)

    # No tile available — return 204 No Content (standard slippy-map behaviour)
    return Response(status_code=204)


def _read_local_tile(z: int, x: int, y: int) -> bytes | None:
    """
    Placeholder for PMTiles/MBTiles reader.
    Replace with a proper PMTiles reader (e.g. pmtiles-python) when the
    tile archive is populated.
    """
    # TODO: Implement PMTiles range-request reader
    return None
