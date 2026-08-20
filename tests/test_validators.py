"""
Tests for marg.api.validators — India bounding box, coordinate parsing,
profile validation, text sanitization.
"""

import pytest
from fastapi import HTTPException

from marg.api.validators import (
    parse_coordinate_pair,
    sanitize_text_query,
    validate_india_coordinate,
    validate_profile,
    validate_tile_coords,
    validate_telemetry_speed,
)


# ── India coordinate bounds ───────────────────────────────────────────────────

class TestIndiaCoordinateBounds:
    """validate_india_coordinate must accept all valid India points and reject others."""

    # Valid India coordinates (corners + centroid)
    @pytest.mark.parametrize("lat,lon", [
        (12.9352, 77.6245),   # Bengaluru
        (28.6139, 77.2090),   # Delhi
        (19.0760, 72.8777),   # Mumbai
        (6.0, 68.0),          # SW corner
        (37.5, 97.5),         # NE corner
        (20.5937, 78.9629),   # Geographic centroid
    ])
    def test_valid_india_coords_accepted(self, lat, lon):
        validate_india_coordinate(lat, lon)  # must not raise

    # Out-of-country coordinates
    @pytest.mark.parametrize("lat,lon,label", [
        (51.5074, -0.1278, "London"),
        (40.7128, -74.0060, "New York"),
        (-33.8688, 151.2093, "Sydney"),
        (35.6762, 139.6503, "Tokyo"),
        (5.9, 68.0, "below India lat"),
        (37.6, 78.0, "above India lat"),
        (6.0, 67.9, "west of India lon"),
        (6.0, 97.6, "east of India lon"),
    ])
    def test_out_of_india_coords_rejected(self, lat, lon, label):
        with pytest.raises(HTTPException) as exc_info:
            validate_india_coordinate(lat, lon)
        assert exc_info.value.status_code == 400, f"Expected 400 for {label}"

    def test_error_message_does_not_expose_internals(self):
        """Error detail must not contain stack trace markers or internal paths."""
        with pytest.raises(HTTPException) as exc_info:
            validate_india_coordinate(51.5, -0.1)
        detail = exc_info.value.detail
        assert "traceback" not in detail.lower()
        assert "/marg/" not in detail
        assert "site-packages" not in detail


# ── Coordinate pair parsing ───────────────────────────────────────────────────

class TestParseCoordinatePair:
    def test_valid_pair(self):
        lat, lon = parse_coordinate_pair("12.9352,77.6245")
        assert abs(lat - 12.9352) < 1e-4
        assert abs(lon - 77.6245) < 1e-4

    def test_whitespace_stripped(self):
        lat, lon = parse_coordinate_pair("  12.9352 , 77.6245  ")
        assert abs(lat - 12.9352) < 1e-4

    @pytest.mark.parametrize("bad_input", [
        "12.9352",            # only one value
        "12.9352,77.6245,0",  # three values
        "abc,xyz",            # non-numeric
        "",                   # empty
        "12.9352;77.6245",    # wrong separator
    ])
    def test_malformed_inputs_rejected(self, bad_input):
        with pytest.raises(HTTPException) as exc_info:
            parse_coordinate_pair(bad_input)
        assert exc_info.value.status_code == 400

    def test_out_of_india_rejected_in_parse(self):
        with pytest.raises(HTTPException):
            parse_coordinate_pair("51.5,0.1")  # London


# ── Profile validation ────────────────────────────────────────────────────────

class TestProfileValidation:
    @pytest.mark.parametrize("profile", ["foot", "car", "bike"])
    def test_valid_profiles(self, profile):
        assert validate_profile(profile) == profile

    @pytest.mark.parametrize("bad_profile", [
        "walk", "driving", "cycling", "auto", "", "FOOT", "Car", "BIKE",
        "foot; DROP TABLE users--",
    ])
    def test_invalid_profiles_rejected(self, bad_profile):
        with pytest.raises(HTTPException) as exc_info:
            validate_profile(bad_profile)
        assert exc_info.value.status_code == 400


# ── Text query sanitization ───────────────────────────────────────────────────

class TestSanitizeTextQuery:
    @pytest.mark.parametrize("q", [
        "Koramangala Bengaluru",
        "MG Road, Delhi",
        "मुंबई",   # Devanagari
        "hospital near Connaught Place",
        "Anna Nagar, Chennai 600040",
    ])
    def test_valid_queries_accepted(self, q):
        result = sanitize_text_query(q)
        assert result  # non-empty string returned

    def test_empty_query_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            sanitize_text_query("")
        assert exc_info.value.status_code == 400

    def test_over_length_rejected(self):
        with pytest.raises(HTTPException):
            sanitize_text_query("a" * 300)

    @pytest.mark.parametrize("injection", [
        "<script>alert(1)</script>",
        "'; DROP TABLE places; --",
        '{"$where": "1==1"}',
        "[OR 1=1]",
        "test`whoami`",
    ])
    def test_injection_patterns_rejected(self, injection):
        with pytest.raises(HTTPException) as exc_info:
            sanitize_text_query(injection)
        assert exc_info.value.status_code == 400


# ── Tile coordinate validation ────────────────────────────────────────────────

class TestTileCoords:
    @pytest.mark.parametrize("z,x,y", [
        (0, 0, 0),
        (14, 11312, 6744),  # Bengaluru area
        (22, 0, 0),
    ])
    def test_valid_tile_coords(self, z, x, y):
        validate_tile_coords(z, x, y)  # must not raise

    @pytest.mark.parametrize("z,x,y", [
        (23, 0, 0),    # z too high
        (-1, 0, 0),    # z negative
        (5, 999, 0),   # x out of range for zoom 5
        (5, 0, -1),    # y negative
    ])
    def test_invalid_tile_coords_rejected(self, z, x, y):
        with pytest.raises(HTTPException):
            validate_tile_coords(z, x, y)


# ── Speed validation ──────────────────────────────────────────────────────────

class TestTelemetrySpeed:
    @pytest.mark.parametrize("speed", [0.0, 30.0, 120.0, 250.0])
    def test_valid_speeds(self, speed):
        validate_telemetry_speed(speed)

    @pytest.mark.parametrize("speed", [-1.0, 251.0, 999.9])
    def test_implausible_speeds_rejected(self, speed):
        with pytest.raises(HTTPException):
            validate_telemetry_speed(speed)
