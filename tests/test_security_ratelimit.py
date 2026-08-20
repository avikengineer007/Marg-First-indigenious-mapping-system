"""
Security and rate-limiting tests.

Rate limit tests use the SlowAPI limiter directly or patch the limit
to a low value so tests run fast without waiting minutes.
"""

import pytest
from httpx import AsyncClient
from unittest.mock import patch


class TestSecurityHeaders:
    """Marg must set defensive security headers on all responses."""

    async def test_x_content_type_options(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    async def test_x_frame_options(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.headers.get("x-frame-options") == "DENY"

    async def test_no_server_header(self, client: AsyncClient):
        """Server version must not be revealed."""
        resp = await client.get("/health")
        assert "server" not in resp.headers


class TestErrorLeakage:
    """API error responses must never expose internal implementation details."""

    async def test_not_found_no_stack_trace(self, client: AsyncClient):
        resp = await client.get("/nonexistent-endpoint-xyz")
        assert resp.status_code == 404
        body = resp.text
        assert "traceback" not in body.lower()
        assert "File " not in body
        assert "site-packages" not in body

    async def test_validation_error_is_structured(self, client: AsyncClient):
        """FastAPI 422 validation errors must be structured, not raw exception output."""
        resp = await client.get("/route", params={
            "start": "not,valid",
            "end": "12.9716,77.5946",
            "profile": "car",
        })
        assert resp.status_code in (400, 422)
        # Must be JSON
        data = resp.json()
        assert isinstance(data, dict)
        # Must not contain Python-specific error markers
        body = resp.text
        assert "Traceback" not in body
        assert "File " not in body


class TestInputValidationSecurity:
    """Fuzzing-style tests — various injection patterns must all return 4xx."""

    INJECTION_COORDS = [
        "12.9352,77.6245; DROP TABLE users--",
        "12.9352,77.6245\x00extra",
        "12.9352' OR '1'='1",
        "../../../etc/passwd",
        "%2e%2e%2fetc%2fpasswd",
    ]

    @pytest.mark.parametrize("coord", INJECTION_COORDS)
    async def test_injection_coord_rejected(self, coord, client: AsyncClient):
        resp = await client.get("/route", params={
            "start": coord,
            "end": "12.9716,77.5946",
            "profile": "car",
        })
        assert resp.status_code in (400, 422)

    INJECTION_QUERIES = [
        "<img src=x onerror=alert(1)>",
        "'; exec xp_cmdshell('dir')--",
        "${7*7}",
        "{{7*7}}",
        "$(whoami)",
    ]

    @pytest.mark.parametrize("q", INJECTION_QUERIES)
    async def test_injection_query_rejected(self, q, client: AsyncClient):
        resp = await client.get("/geocode", params={"q": q})
        assert resp.status_code in (400, 422)


class TestRateLimiting:
    """
    Verify that rate limiting infrastructure is in place.
    We do not exhaustively hit limits in unit tests (that would require
    many requests) but verify the limiter is registered on the app.
    """

    async def test_rate_limiter_state_attached(self, client: AsyncClient):
        """The SlowAPI limiter must be attached to app.state."""
        from marg.api.main import app
        assert hasattr(app.state, "limiter")

    async def test_multiple_requests_succeed_within_limit(self, client: AsyncClient):
        """A handful of requests must succeed without triggering rate limiting."""
        for _ in range(5):
            resp = await client.get("/health")
            assert resp.status_code == 200
