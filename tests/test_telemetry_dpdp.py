"""
Tests for the /telemetry/ping endpoint — DPDP Act 2023 compliance.

All tests verify opt-in consent enforcement, pseudonymization side-effects,
and data minimization behaviour.
"""

import pytest
from unittest.mock import patch
from httpx import AsyncClient


# ── Helper: DPDP-compliant valid payload ─────────────────────────────────────

VALID_PING = {
    "session_id": "test-session-abc123-xyz",
    "lat": 12.9352,
    "lon": 77.6245,
    "speed_kmh": 30.0,
    "heading_deg": 180.0,
    "timestamp_ms": 1_700_000_000_000,
}


class TestTelemetryDisabledByDefault:
    """Telemetry must be disabled (MARG_TELEMETRY_ENABLED=false) by default."""

    async def test_ping_disabled_returns_503(self, client: AsyncClient):
        """Without MARG_TELEMETRY_ENABLED=true, /telemetry/ping must return 503."""
        resp = await client.post(
            "/telemetry/ping",
            json=VALID_PING,
            headers={"X-Marg-Consent": "1"},
        )
        assert resp.status_code == 503


class TestTelemetryConsentEnforcement:
    """DPDP §6: Consent must be explicit. No consent = 403."""

    @pytest.fixture(autouse=True)
    def enable_telemetry(self):
        with patch("marg.api.routes.telemetry.settings") as mock_settings:
            mock_settings.telemetry_enabled = True
            mock_settings.telemetry_db_path = ":memory:"
            mock_settings.telemetry_salt_rotation_hours = 24
            mock_settings.INDIA_MIN_LAT = 6.0
            mock_settings.INDIA_MAX_LAT = 37.5
            mock_settings.INDIA_MIN_LON = 68.0
            mock_settings.INDIA_MAX_LON = 97.5
            yield

    async def test_ping_without_consent_header_rejected(self, client: AsyncClient):
        resp = await client.post("/telemetry/ping", json=VALID_PING)
        assert resp.status_code == 403

    async def test_ping_with_wrong_consent_value_rejected(self, client: AsyncClient):
        for bad_val in ["0", "yes", "true", "consent", ""]:
            resp = await client.post(
                "/telemetry/ping",
                json=VALID_PING,
                headers={"X-Marg-Consent": bad_val},
            )
            assert resp.status_code == 403, f"Expected 403 for X-Marg-Consent: '{bad_val}'"

    async def test_ping_with_consent_1_and_valid_payload_accepted(self, client: AsyncClient):
        with patch("marg.api.routes.telemetry._ensure_db") as mock_db:
            mock_conn = mock_db.return_value
            mock_conn.execute.return_value = None
            mock_conn.commit.return_value = None
            resp = await client.post(
                "/telemetry/ping",
                json=VALID_PING,
                headers={"X-Marg-Consent": "1"},
            )
            # 202 Accepted
            assert resp.status_code == 202
            assert resp.json()["status"] == "accepted"


class TestTelemetryBoundsValidation:
    """Coordinates and speed must be validated before storage."""

    @pytest.fixture(autouse=True)
    def enable_telemetry(self):
        with patch("marg.api.routes.telemetry.settings") as mock_settings:
            mock_settings.telemetry_enabled = True
            mock_settings.telemetry_db_path = ":memory:"
            mock_settings.telemetry_salt_rotation_hours = 24
            mock_settings.INDIA_MIN_LAT = 6.0
            mock_settings.INDIA_MAX_LAT = 37.5
            mock_settings.INDIA_MIN_LON = 68.0
            mock_settings.INDIA_MAX_LON = 97.5
            yield

    async def test_out_of_india_lat_rejected(self, client: AsyncClient):
        payload = {**VALID_PING, "lat": 51.5, "lon": -0.1}  # London
        resp = await client.post(
            "/telemetry/ping", json=payload, headers={"X-Marg-Consent": "1"}
        )
        assert resp.status_code == 400

    async def test_implausible_speed_rejected(self, client: AsyncClient):
        payload = {**VALID_PING, "speed_kmh": 350.0}
        resp = await client.post(
            "/telemetry/ping", json=payload, headers={"X-Marg-Consent": "1"}
        )
        # Pydantic field validator (ge=0, le=250) returns 422; our validator returns 400
        # Both indicate the value was rejected before storage
        assert resp.status_code in (400, 422)


class TestTelemetryPseudonymization:
    """Session IDs must be pseudonymized — the raw ID must never appear in storage."""

    def test_pseudonymize_session_deterministic_within_window(self):
        from marg.api.routes.telemetry import _pseudonymize_session
        h1 = _pseudonymize_session("my-session-id-123")
        h2 = _pseudonymize_session("my-session-id-123")
        assert h1 == h2, "Same session ID in the same time window must hash identically"

    def test_pseudonymize_session_different_ids_produce_different_hashes(self):
        from marg.api.routes.telemetry import _pseudonymize_session
        h1 = _pseudonymize_session("session-A")
        h2 = _pseudonymize_session("session-B")
        assert h1 != h2

    def test_pseudonymize_session_output_is_not_original_id(self):
        from marg.api.routes.telemetry import _pseudonymize_session
        raw_id = "my-raw-session-id-do-not-store"
        result = _pseudonymize_session(raw_id)
        assert raw_id not in result

    def test_pseudonymize_output_length_bounded(self):
        """Hash output must be fixed-length (≤ 64 chars) — no unbounded strings stored."""
        from marg.api.routes.telemetry import _pseudonymize_session
        for raw in ["a", "abc" * 40, "x" * 128]:
            assert len(_pseudonymize_session(raw)) <= 64


class TestTelemetryErrorLeakage:
    """Telemetry error responses must not expose internal details."""

    async def test_403_response_no_stack_trace(self, client: AsyncClient):
        resp = await client.post("/telemetry/ping", json=VALID_PING)
        body = resp.text
        assert "traceback" not in body.lower()
        assert "File " not in body

    async def test_503_response_no_internal_paths(self, client: AsyncClient):
        resp = await client.post(
            "/telemetry/ping",
            json=VALID_PING,
            headers={"X-Marg-Consent": "1"},
        )
        body = resp.text
        assert "site-packages" not in body
        assert "/marg/" not in body
