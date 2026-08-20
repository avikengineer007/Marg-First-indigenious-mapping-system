"""
Integration tests for API route endpoints:
  /route, /geocode, /geocode/reverse, /search, /health
"""

import pytest
from httpx import AsyncClient


class TestRouteEndpoint:
    """GET /route"""

    async def test_invalid_profile_returns_400(self, client: AsyncClient):
        resp = await client.get("/route", params={
            "start": "12.9352,77.6245",
            "end": "12.9716,77.5946",
            "profile": "walking",  # invalid
        })
        assert resp.status_code == 400

    async def test_out_of_india_start_returns_400(self, client: AsyncClient):
        resp = await client.get("/route", params={
            "start": "51.5074,-0.1278",  # London
            "end": "12.9716,77.5946",
            "profile": "car",
        })
        assert resp.status_code == 400

    async def test_out_of_india_end_returns_400(self, client: AsyncClient):
        resp = await client.get("/route", params={
            "start": "12.9352,77.6245",
            "end": "40.7128,-74.0060",  # New York
            "profile": "foot",
        })
        assert resp.status_code == 400

    async def test_malformed_coordinate_returns_400(self, client: AsyncClient):
        resp = await client.get("/route", params={
            "start": "not_a_coord",
            "end": "12.9716,77.5946",
            "profile": "car",
        })
        assert resp.status_code == 400

    async def test_valid_in_india_no_osrm_returns_no_route_or_ok(self, client: AsyncClient):
        """Without OSRM and without a local graph, expect no_route (not an HTTP error)."""
        resp = await client.get("/route", params={
            "start": "12.9352,77.6245",
            "end": "12.9716,77.5946",
            "profile": "car",
        })
        # Must be 200 regardless of whether a route was found
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "no_route")

    async def test_error_response_no_stacktrace(self, client: AsyncClient):
        """Error responses must not contain traceback or internal path information."""
        resp = await client.get("/route", params={
            "start": "51.5074,-0.1278",
            "end": "12.9716,77.5946",
            "profile": "car",
        })
        body = resp.text
        assert "traceback" not in body.lower()
        assert "site-packages" not in body
        assert "/marg/" not in body

    async def test_all_profiles_accepted(self, client: AsyncClient):
        for profile in ("foot", "car", "bike"):
            resp = await client.get("/route", params={
                "start": "12.9352,77.6245",
                "end": "12.9716,77.5946",
                "profile": profile,
            })
            assert resp.status_code == 200, f"Profile '{profile}' should return 200"


class TestGeocodeEndpoint:
    """GET /geocode  and  GET /geocode/reverse"""

    async def test_empty_query_returns_400(self, client: AsyncClient):
        resp = await client.get("/geocode", params={"q": ""})
        assert resp.status_code == 400

    async def test_injection_query_returns_400(self, client: AsyncClient):
        resp = await client.get("/geocode", params={"q": "<script>alert(1)</script>"})
        assert resp.status_code == 400

    async def test_valid_query_returns_200(self, client: AsyncClient):
        resp = await client.get("/geocode", params={"q": "Connaught Place Delhi"})
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    async def test_reverse_out_of_india_returns_400(self, client: AsyncClient):
        resp = await client.get("/geocode/reverse", params={"lat": 51.5, "lon": -0.1})
        assert resp.status_code == 400

    async def test_reverse_valid_coord_returns_200(self, client: AsyncClient):
        resp = await client.get("/geocode/reverse", params={"lat": 12.9352, "lon": 77.6245})
        # With no Nominatim and no local DB, may 404 — but must be 200 or 404, never 500
        assert resp.status_code in (200, 404)


class TestSearchEndpoint:
    """GET /search"""

    async def test_empty_query_returns_400(self, client: AsyncClient):
        resp = await client.get("/search", params={"q": ""})
        assert resp.status_code == 400

    async def test_injection_in_category_returns_400(self, client: AsyncClient):
        resp = await client.get("/search", params={"q": "hospital", "category": "<evil>"})
        assert resp.status_code == 400

    async def test_near_out_of_india_returns_400(self, client: AsyncClient):
        resp = await client.get("/search", params={
            "q": "hospital",
            "near_lat": "51.5",
            "near_lon": "-0.1",
        })
        assert resp.status_code == 400

    async def test_valid_search_returns_200(self, client: AsyncClient):
        resp = await client.get("/search", params={"q": "hospital"})
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "query" in data


class TestHealthEndpoint:
    """GET /health"""

    async def test_health_returns_200(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_health_schema(self, client: AsyncClient):
        resp = await client.get("/health")
        data = resp.json()
        assert "status" in data
        assert "version" in data
        assert "backends" in data
        assert isinstance(data["backends"], list)

    async def test_health_status_is_valid_value(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.json()["status"] in ("ok", "degraded", "unavailable")

    async def test_health_does_not_expose_internals(self, client: AsyncClient):
        resp = await client.get("/health")
        body = resp.text
        assert "traceback" not in body.lower()
        assert "site-packages" not in body
