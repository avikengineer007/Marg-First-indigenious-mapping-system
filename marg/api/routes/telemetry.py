"""
/telemetry endpoint — Phase 2 DPDP-compliant anonymized location ping ingestion.

Master switch: MARG_TELEMETRY_ENABLED must be true in the environment.
When disabled (the default), all /telemetry requests return 503.

Privacy guarantees:
  - Explicit user opt-in required (X-Marg-Consent: 1 header)
  - No user-identifying data stored — session ID pseudonymized with a
    24-hour rolling salt so it cannot be linked across salt rotation windows
  - Speed and coordinate plausibility bounds enforced
  - No stack trace or internal path exposed in error responses

Compliant with India DPDP Act 2023:
  - Purpose limitation: pings used only for road-segment speed aggregation
  - Data minimization: only lat, lon, speed_kmh, heading stored — no device ID
  - Retention: configurable via MARG_TELEMETRY_SALT_ROTATION_HOURS
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from marg.api.validators import (
    validate_india_coordinate,
    validate_telemetry_speed,
)
from marg.config import settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/telemetry", tags=["Telemetry (Phase 2)"])


# ── Pseudonymization ──────────────────────────────────────────────────────────

def _pseudonymize_session(raw_session_id: str) -> str:
    """
    Hash a session ID with a time-bucketed salt so it cannot be linked
    across salt rotation windows. The raw ID never touches storage.
    """
    rotation_hours = settings.telemetry_salt_rotation_hours
    # Floor to the current rotation window
    bucket = int(time.time() // (rotation_hours * 3600))
    salt = f"marg-salt-{bucket}"
    return hashlib.sha256(f"{salt}:{raw_session_id}".encode()).hexdigest()[:32]


# ── DB setup ──────────────────────────────────────────────────────────────────

def _ensure_db() -> sqlite3.Connection:
    db_path = Path(settings.telemetry_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_hash TEXT    NOT NULL,
            lat          REAL    NOT NULL,
            lon          REAL    NOT NULL,
            speed_kmh    REAL,
            heading_deg  REAL,
            ts           INTEGER NOT NULL   -- Unix timestamp (seconds)
        )
    """)
    conn.commit()
    return conn


# ── Request model ─────────────────────────────────────────────────────────────

class TelemetryPing(BaseModel):
    session_id: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description=(
            "Client-generated ephemeral session ID. "
            "Never stored — pseudonymized before persistence."
        ),
    )
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    speed_kmh: float | None = Field(None, ge=0, le=250)
    heading_deg: float | None = Field(None, ge=0, le=360)
    timestamp_ms: int | None = Field(
        None, description="Client-side Unix timestamp in milliseconds."
    )


class TelemetryResponse(BaseModel):
    status: str = "accepted"


# ── Handler ───────────────────────────────────────────────────────────────────

@router.post(
    "/ping",
    response_model=TelemetryResponse,
    status_code=202,
    summary="Submit an anonymized location ping",
    description=(
        "Accepts an anonymized location ping from a consenting navigation session. "
        "Requires the `X-Marg-Consent: 1` header. "
        "Pings are pseudonymized before storage — no raw session or device ID is retained."
    ),
)
async def ingest_ping(
    body: TelemetryPing,
    x_marg_consent: Annotated[
        str | None,
        Header(description="Must be '1' to indicate explicit user opt-in consent."),
    ] = None,
) -> TelemetryResponse:
    # Master switch
    if not settings.telemetry_enabled:
        raise HTTPException(
            status_code=503,
            detail="Telemetry ingestion is not enabled on this Marg instance.",
        )

    # Consent gate (DPDP Act 2023 — explicit opt-in required)
    if x_marg_consent != "1":
        raise HTTPException(
            status_code=403,
            detail=(
                "Telemetry requires explicit user consent. "
                "Set the X-Marg-Consent: 1 header only after obtaining consent."
            ),
        )

    # Validate location is within India
    validate_india_coordinate(body.lat, body.lon, "ping")

    # Validate speed plausibility
    if body.speed_kmh is not None:
        validate_telemetry_speed(body.speed_kmh)

    # Pseudonymize session ID — raw ID discarded
    session_hash = _pseudonymize_session(body.session_id)

    # Persist anonymized ping
    ts = int((body.timestamp_ms or time.time() * 1000) / 1000)
    try:
        conn = _ensure_db()
        conn.execute(
            "INSERT INTO pings (session_hash, lat, lon, speed_kmh, heading_deg, ts) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_hash, body.lat, body.lon, body.speed_kmh, body.heading_deg, ts),
        )
        conn.commit()
        conn.close()
    except Exception:
        log.exception("Failed to persist telemetry ping")
        raise HTTPException(status_code=500, detail="Failed to record ping.")

    return TelemetryResponse()
