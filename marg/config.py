"""
Marg centralised configuration.

All values are loaded from environment variables (or a .env file via
pydantic-settings). No defaults contain secrets. See .env.example for
the full list of configurable fields.
"""

from __future__ import annotations

from pydantic import field_validator, model_validator
# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore


class MargSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MARG_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Server ──────────────────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False
    log_level: str = "info"

    # ── India geographic bounding box (non-negotiable) ───────────────────────
    # Lat: 6.0°N – 37.5°N   Lon: 68.0°E – 97.5°E
    INDIA_MIN_LAT: float = 6.0
    INDIA_MAX_LAT: float = 37.5
    INDIA_MIN_LON: float = 68.0
    INDIA_MAX_LON: float = 97.5

    # ── Rate limiting ────────────────────────────────────────────────────────
    rate_limit_rpm: int = 60       # requests per minute per client
    rate_limit_burst: int = 20     # burst above steady rate

    # ── Routing backends (OSRM) ──────────────────────────────────────────────
    osrm_foot_url: str = ""
    osrm_car_url: str = ""
    osrm_bike_url: str = ""

    # ── Geocoding backend (Nominatim) ────────────────────────────────────────
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = "marg-engine/0.1.0 (India Mapping Engine)"

    # ── Local geocoding index ────────────────────────────────────────────────
    geocode_db_path: str = "./data/geocode.db"

    # ── Tile serving ─────────────────────────────────────────────────────────
    tiles_path: str = "./data/tiles/india-pilot.pmtiles"
    # ── Routing engine configuration ─────────────────────────────────────────
    enable_synthetic_bridging: bool = True  # Heuristic topological gap repair toggle

    # ── Phase 2 telemetry (disabled by default) ──────────────────────────────
    telemetry_enabled: bool = False
    telemetry_db_path: str = "./data/telemetry.db"
    telemetry_salt_rotation_hours: int = 24

    # ── Data directories ─────────────────────────────────────────────────────
    data_dir: str = "./data"
    osm_extract_dir: str = "./data/osm"

    # ── Security ─────────────────────────────────────────────────────────────
    api_key: str = ""          # empty = key auth disabled
    cors_origins: str = "*"

    # ── Pilot regions ────────────────────────────────────────────────────────
    # Mapping: region slug → Geofabrik sub-region download URL
    PILOT_REGIONS: dict[str, dict] = {
        "bengaluru": {
            "name": "Bengaluru",
            "geofabrik_url": (
                "https://download.geofabrik.de/asia/india/"
                "karnataka-latest.osm.pbf"
            ),
            "bbox": {
                "min_lat": 12.7342,
                "max_lat": 13.1736,
                "min_lon": 77.3791,
                "max_lon": 77.8244,
            },
        },
        "delhi": {
            "name": "Delhi NCR",
            "geofabrik_url": (
                "https://download.geofabrik.de/asia/india/"
                "delhi-latest.osm.pbf"
            ),
            "bbox": {
                "min_lat": 28.3048,
                "max_lat": 28.8831,
                "min_lon": 76.8376,
                "max_lon": 77.3491,
            },
        },
        "mumbai": {
            "name": "Mumbai",
            "geofabrik_url": (
                "https://download.geofabrik.de/asia/india/"
                "maharashtra-latest.osm.pbf"
            ),
            "bbox": {
                "min_lat": 18.8928,
                "max_lat": 19.2704,
                "min_lon": 72.7757,
                "max_lon": 73.0609,
            },
        },
        "kolkata": {
            "name": "Kolkata / West Bengal",
            "geofabrik_url": (
                "https://download.geofabrik.de/asia/india/"
                "west-bengal-latest.osm.pbf"
            ),
            "bbox": {
                "min_lat": 21.5,
                "max_lat": 27.5,
                "min_lon": 85.8,
                "max_lon": 89.9,
            },
        },
        "west-bengal": {
            "name": "West Bengal",
            "geofabrik_url": (
                "https://download.geofabrik.de/asia/india/"
                "west-bengal-latest.osm.pbf"
            ),
            "bbox": {
                "min_lat": 21.5,
                "max_lat": 27.5,
                "min_lon": 85.8,
                "max_lon": 89.9,
            },
        },
    }

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"debug", "info", "warning", "error", "critical"}
        if v.lower() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v.lower()

    @model_validator(mode="after")
    def validate_bbox_integrity(self) -> "MargSettings":
        assert self.INDIA_MIN_LAT < self.INDIA_MAX_LAT, (
            "INDIA_MIN_LAT must be less than INDIA_MAX_LAT"
        )
        assert self.INDIA_MIN_LON < self.INDIA_MAX_LON, (
            "INDIA_MIN_LON must be less than INDIA_MAX_LON"
        )
        return self

    def osrm_url_for_profile(self, profile: str) -> str:
        """Return the OSRM base URL for a given routing profile."""
        mapping = {
            "foot": self.osrm_foot_url,
            "car": self.osrm_car_url,
            "bike": self.osrm_bike_url,
        }
        return mapping.get(profile, "")

    def cors_origins_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


# Singleton — import this throughout the codebase
settings = MargSettings()
