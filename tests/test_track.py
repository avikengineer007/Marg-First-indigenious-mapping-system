"""
Tests for POST /route/track live position tracking and deterministic off-route recalculation.

Privacy & DPDP invariants verified:
  - In-memory processing only (zero database / disk persistence)
  - No raw stack trace or internal leakage on malformed requests
  - Fail-closed bounding box validation for India
"""

import pytest
from httpx import AsyncClient


class TestTrackEndpoint:
    """Test suite for live tracking and off-route detection."""

    SAMPLE_ROUTE_GEOMETRY = {
        "type": "LineString",
        "coordinates": [
            [77.6245, 12.9352],
            [77.6100, 12.9500],
            [77.5946, 12.9716],
        ],
    }

    async def test_track_on_route(self, client: AsyncClient):
        """Position directly on the polyline should report off_route=False."""
        payload = {
            "lat": 12.9352,
            "lon": 77.6245,
            "destination": "12.9716,77.5946",
            "profile": "car",
            "route_geometry": self.SAMPLE_ROUTE_GEOMETRY,
            "off_route_threshold_m": 50.0,
        }
        resp = await client.post("/route/track", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["off_route"] is False
        assert data["distance_to_route_m"] < 5.0
        assert data["reroute"] is None
        assert "On track" in data["message"]

    async def test_track_off_route_triggers_reroute(self, client: AsyncClient):
        """Position far away (> 50m) should report off_route=True and return reroute."""
        # 12.9000, 77.6000 is ~4km away from the polyline
        payload = {
            "lat": 12.9000,
            "lon": 77.6000,
            "destination": "12.9716,77.5946",
            "profile": "car",
            "route_geometry": self.SAMPLE_ROUTE_GEOMETRY,
            "off_route_threshold_m": 50.0,
        }
        resp = await client.post("/route/track", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "no_route")
        assert data["off_route"] is True
        assert data["distance_to_route_m"] > 50.0
        if data.get("reroute"):
            assert "geometry" in data["reroute"]
            assert data["reroute"]["geometry"]["type"] == "LineString"

    async def test_track_off_route_with_mocked_route(self, client: AsyncClient, monkeypatch):
        """Test off-route recalculation with a mocked successful route response."""
        from marg.engine.graph_router import GraphRouter

        fake_route = {
            "status": "ok",
            "profile": "car",
            "distance_m": 3500.0,
            "duration_s": 500.0,
            "geometry": {
                "type": "LineString",
                "coordinates": [[77.6000, 12.9000], [77.5946, 12.9716]],
            },
            "steps": [],
            "waypoints": [],
        }

        async def mock_route(self, *args, **kwargs):
            return fake_route

        from marg.engine.osrm_client import OsrmClient
        monkeypatch.setattr(OsrmClient, "route", mock_route)
        monkeypatch.setattr(GraphRouter, "route", mock_route)

        payload = {
            "lat": 12.9000,
            "lon": 77.6000,
            "destination": "12.9716,77.5946",
            "profile": "car",
            "route_geometry": self.SAMPLE_ROUTE_GEOMETRY,
            "off_route_threshold_m": 50.0,
        }
        resp = await client.post("/route/track", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["off_route"] is True
        assert data["reroute"] is not None
        assert data["reroute"]["distance_m"] == 3500.0

    async def test_track_out_of_india_lat_rejected(self, client: AsyncClient):
        """Coordinates outside India latitude must fail with 400 Bad Request."""
        payload = {
            "lat": 51.5074,  # London
            "lon": 77.6245,
            "destination": "12.9716,77.5946",
            "profile": "car",
            "route_geometry": self.SAMPLE_ROUTE_GEOMETRY,
        }
        resp = await client.post("/route/track", json=payload)
        assert resp.status_code == 400
        assert "outside India" in resp.json().get("detail", "")

    async def test_track_out_of_india_lon_rejected(self, client: AsyncClient):
        """Coordinates outside India longitude must fail with 400 Bad Request."""
        payload = {
            "lat": 12.9352,
            "lon": -0.1278,  # London lon
            "destination": "12.9716,77.5946",
            "profile": "car",
            "route_geometry": self.SAMPLE_ROUTE_GEOMETRY,
        }
        resp = await client.post("/route/track", json=payload)
        assert resp.status_code == 400
        assert "outside India" in resp.json().get("detail", "")

    async def test_track_out_of_india_destination_rejected(self, client: AsyncClient):
        """Destination outside India must fail with 400 Bad Request."""
        payload = {
            "lat": 12.9352,
            "lon": 77.6245,
            "destination": "40.7128,-74.0060",  # New York
            "profile": "car",
            "route_geometry": self.SAMPLE_ROUTE_GEOMETRY,
        }
        resp = await client.post("/route/track", json=payload)
        assert resp.status_code == 400
        assert "outside India" in resp.json().get("detail", "")

    async def test_track_invalid_profile_rejected(self, client: AsyncClient):
        """Invalid routing profiles must return 400."""
        payload = {
            "lat": 12.9352,
            "lon": 77.6245,
            "destination": "12.9716,77.5946",
            "profile": "rocket",
            "route_geometry": self.SAMPLE_ROUTE_GEOMETRY,
        }
        resp = await client.post("/route/track", json=payload)
        assert resp.status_code == 400
        assert "Invalid profile" in resp.json().get("detail", "")

    async def test_track_no_geometry_initial_route(self, client: AsyncClient):
        """When no initial geometry is passed, calculate route directly."""
        payload = {
            "lat": 12.9352,
            "lon": 77.6245,
            "destination": "12.9716,77.5946",
            "profile": "car",
        }
        resp = await client.post("/route/track", json=payload)
        assert resp.status_code in (200, 400)
        if resp.status_code == 200:
            data = resp.json()
            assert data["status"] in ("ok", "no_route")

    async def test_track_no_stacktrace_on_malformed_input(self, client: AsyncClient):
        """Malformed tracking payload must not leak traceback or file paths."""
        resp = await client.post("/route/track", json={"lat": "invalid", "lon": 77.6245})
        assert resp.status_code in (400, 422)
        body = resp.text
        assert "Traceback" not in body
        assert "File \"" not in body

    async def test_track_does_not_write_to_telemetry_db(self, client: AsyncClient, monkeypatch):
        """Verify that /route/track is in-memory only and never touches the telemetry database."""
        from marg.api.routes import telemetry

        # Spy on telemetry database accessor function
        db_called = False

        def fake_ensure_db():
            nonlocal db_called
            db_called = True
            raise RuntimeError("Telemetry DB should not be accessed during /route/track")

        monkeypatch.setattr(telemetry, "_ensure_db", fake_ensure_db)

        payload = {
            "lat": 12.9352,
            "lon": 77.6245,
            "destination": "12.9716,77.5946",
            "profile": "car",
            "route_geometry": self.SAMPLE_ROUTE_GEOMETRY,
        }
        resp = await client.post("/route/track", json=payload)
        assert resp.status_code == 200
        # Telemetry DB must NOT have been accessed
        assert db_called is False
