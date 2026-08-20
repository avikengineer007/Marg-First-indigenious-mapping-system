# मार्ग Marg — India-Scoped Self-Hosted Mapping & Routing Engine

> **Marg** (Sanskrit/Hindi: *path, route*) is a standalone, self-hosted mapping and routing backend scoped exclusively to India. It exposes a clean generic REST API — routing, geocoding, place search, and tile serving — designed to be consumed by any application the same way one would call a third-party maps API. Built with rate limiting, fail-closed validation, and CI-enforced dependency and secrets scanning.

[![CI](https://github.com/avikengineer007/Marg-First-indigenious-mapping-system/actions/workflows/ci.yml/badge.svg)](https://github.com/avikengineer007/Marg-First-indigenious-mapping-system/actions)
[![Security](https://github.com/avikengineer007/Marg-First-indigenious-mapping-system/actions/workflows/security.yml/badge.svg)](https://github.com/avikengineer007/Marg-First-indigenious-mapping-system/actions)

---

## Architecture

```
Client / App
     │
     ▼
Marg Gateway (FastAPI)
├── Rate Limiting (SlowAPI)
├── India Bounding Box Validator (lat 6–37.5°N, lon 68–97.5°E)
├── Fail-Closed Error Handlers
│
├─ /route   ──► OSRM (foot/car/bike profiles) or Local Graph Router
├─ /geocode ──► Nominatim (self-hosted) or Local SQLite FTS5
├─ /search  ──► Nominatim POI search or Local FTS5
├─ /tiles   ──► Local PMTiles archive or upstream fallback
└─ /health  ──► Component health probes
```

## Pilot Cities (Phase 1)

| City | OSM Extract | Bbox |
|---|---|---|
| Bengaluru | Karnataka extract (Geofabrik) | 12.73–13.17°N, 77.38–77.82°E |
| Delhi NCR | Delhi extract (Geofabrik) | 28.30–28.88°N, 76.84–77.35°E |
| Mumbai | Maharashtra extract (Geofabrik) | 18.89–19.27°N, 72.78–73.06°E |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose (for production stack)

### 1. Clone and install

```powershell
git clone https://github.com/avikengineer007/Marg-First-indigenious-mapping-system.git
cd Marg-First-indigenious-mapping-system
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

### 2. Configure environment

```powershell
Copy-Item .env.example .env
# Edit .env as needed — no hardcoded secrets
```

### 3. Install pre-commit hooks (required)

```powershell
pre-commit install
```

### 4. Run the API (development mode — no Docker required)

```powershell
marg serve --reload
# → http://localhost:8000
# → http://localhost:8000/docs  (interactive API docs)
```

### 5. Download and build pilot data

```powershell
marg data download --region bengaluru
marg data build --region bengaluru
```

### 6. Production stack (Docker Compose)

See [docker/README.md](docker/README.md) for OSRM pre-processing steps.

```powershell
docker compose up -d
```

---

## CLI Reference

```
marg serve          Start the API server
marg health         Check all backend components
marg data download  Download OSM PBF for a pilot region
marg data build     Build routing graph and geocode index
marg test-route     Run a sample route in the terminal
marg audit          Dependency vulnerability scan (pip-audit)
```

---

## API Endpoints

See full API documentation in [docs/api.md](docs/api.md).

| Endpoint | Method | Description |
|---|---|---|
| `/route` | GET | Point-to-point routing with `profile` (foot/car/bike) |
| `/geocode` | GET | Forward geocoding: address → coordinates |
| `/geocode/reverse` | GET | Reverse geocoding: coordinates → address |
| `/search` | GET | POI/place keyword search |
| `/tiles/style.json` | GET | MapLibre GL style specification |
| `/tiles/{z}/{x}/{y}.pbf` | GET | Vector map tiles |
| `/health` | GET | System health check |
| `/telemetry/ping` | POST | Phase 2: DPDP-compliant location ping (disabled by default) |

---

## Security

- **Rate limiting**: All endpoints rate-limited (configurable via `MARG_RATE_LIMIT_RPM`)
- **India bounding box**: All coordinates validated against India's geographic bounds before routing or geocoding
- **Input sanitization**: Injection patterns rejected before reaching any backend
- **Fail-closed**: No route = structured `no_route` response, not a guess
- **No stack trace leakage**: Generic error messages exposed to clients; full detail logged server-side only
- **Secrets**: All credentials via environment variables; `detect-secrets` pre-commit hook + CI scan guards against accidental commits
- **Dependency scanning**: `pip-audit` runs on every push/PR and weekly via GitHub Actions

---

## Testing

```powershell
# Run full test suite
pytest -v

# Run with coverage
pytest --cov=marg --cov-report=term-missing

# Security scans
pip-audit --strict
detect-secrets scan --baseline .secrets.baseline
```

---

## Scaling Path: Pilot → Full India

See [docs/scaling.md](docs/scaling.md) for the detailed extension path.

**Summary**:
1. **Phase 1 (Now)**: Bengaluru + Delhi + Mumbai pilot extracts
2. **Phase 2**: Download full `india-latest.osm.pbf` from Geofabrik, rebuild OSRM graphs and Nominatim index for all of India
3. **Phase 3**: Tile server upgrade to full India PMTiles archive
4. **Phase 4 (DPDP-compliant)**: Enable telemetry ingestion to bootstrap traffic dataset from user base

---

## Phase 2: Live Telemetry (DPDP Act 2023)

The `/telemetry/ping` endpoint is **disabled by default** (`MARG_TELEMETRY_ENABLED=false`).

When enabled:
- Requires explicit user opt-in (`X-Marg-Consent: 1` header — only set after obtaining consent)
- Session IDs pseudonymized with 24-hour rolling salt before storage
- No device ID, no user ID ever stored
- Speed and coordinate plausibility bounds enforced
- Compliant with India DPDP Act 2023: purpose limitation, data minimization, consent, retention policy

---

## License

MIT
>>>>>>> 27dd6f3 (feat: initial release of Marg — India-scoped self-hosted mapping and routing engine)
