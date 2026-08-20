<div align="center">

# 🗺️ मार्ग (Marg)
### India's Sovereign Self-Hosted Mapping & Routing Engine

[![CI Status](https://img.shields.io/github/actions/workflow/status/avikengineer007/Marg-First-indigenious-mapping-system/ci.yml?branch=main&label=CI%20Build&logo=github)](https://github.com/avikengineer007/Marg-First-indigenious-mapping-system/actions)
[![Security Checks](https://img.shields.io/github/actions/workflow/status/avikengineer007/Marg-First-indigenious-mapping-system/security.yml?branch=main&label=Security%20Checks&logo=github)](https://github.com/avikengineer007/Marg-First-indigenious-mapping-system/actions)
[![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.14-blue?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![OpenStreetMap](https://img.shields.io/badge/OpenStreetMap-India%20Extracts-7EBC6F?logo=openstreetmap&logoColor=white)](https://www.openstreetmap.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/avikengineer007/Marg-First-indigenious-mapping-system)

<p align="center">
  <b>A production-ready, self-hosted mapping backend built specifically for India.</b><br>
  Exposes deterministic REST APIs for turn-by-turn multi-modal routing (Foot, Car, Bike),<br>
  forward/reverse geocoding, POI search, and vector/raster map tile rendering.
</p>

[Quick Start](#-quick-start) • [Features](#-features) • [API Documentation](#-api-endpoints) • [Interactive Visualizer](#-interactive-map-visualizer) • [Scaling to Full India](#-scaling-path)

</div>

---

## 🌟 Highlights & Features

- 🇮🇳 **India Geographic Scoping**: Strict fail-closed bounding box validation (`6.0°N–37.5°N`, `68.0°E–97.5°E`) ensuring optimal memory footprint and regional precision.
- 🚗 **Multi-Modal Routing**: Profile-aware point-to-point and multi-waypoint path calculation for **Foot**, **Car**, and **Bike**.
- 📍 **Smart Forward & Reverse Geocoding**: Search places by text query across India with automatic coordinate resolution and proximity bias.
- 🗺️ **Interactive Visualizer**: Built-in MapLibre GL UI with real-time autocomplete, profile color coding, and turn-by-turn instruction panels.
- 🔒 **Enterprise-Grade Security**: Rate limiting per endpoint, automated input sanitization, zero stack trace leakage, and continuous security auditing (`pip-audit` & `detect-secrets`).
- ⚡ **Zero-Docker Standalone Fallback**: Includes a built-in Python A* routing engine and SQLite FTS5 index for instant local development without Docker.

---

## 🏗️ Architecture

```
                    ┌───────────────────────────────────┐
                    │      Client App / Frontend        │
                    └─────────────────┬─────────────────┘
                                      │ REST API / JSON
                                      ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        Marg Gateway (FastAPI)                          │
│  ├── SlowAPI Token Bucket Rate Limiting                                │
│  ├── India Bounding Box Validator (6.0–37.5°N, 68.0–97.5°E)            │
│  └── Fail-Closed Error Handlers & Sanitized Envelopes                  │
└──────┬─────────────────┬──────────────────┬─────────────────┬──────────┘
       │                 │                  │                 │
       ▼                 ▼                  ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   /route     │  │   /geocode   │  │   /search    │  │   /tiles     │
│ 3× OSRM      │  │ Self-Hosted  │  │ Nominatim    │  │ Local PMTiles│
│ (Foot/Car/   │  │ Nominatim or │  │ POI Search   │  │ or Upstream  │
│  Bike) or A* │  │ SQLite FTS5  │  │ or FTS5      │  │ Tile Cache   │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
```

---

## 🚀 Quick Start

### 1. Clone & Setup Environment

```powershell
git clone https://github.com/avikengineer007/Marg-First-indigenious-mapping-system.git
cd Marg-First-indigenious-mapping-system

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies in editable mode
pip install -e ".[dev]"
```

### 2. Configure Environment

```powershell
# Copy the template environment configuration
Copy-Item .env.example .env
```

### 3. Download Pilot Region Data

Download open OSM data for your desired pilot city (Bengaluru, Delhi NCR, or Mumbai):

```powershell
marg data download --region bengaluru
marg data build --region bengaluru
```

### 4. Run Marg API Server

```powershell
marg serve --reload
```

Once running, access:
- 🌐 **Interactive Map Visualizer**: [http://localhost:8000](http://localhost:8000)
- 📖 **Interactive API Docs (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- 🩺 **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 🖥️ Interactive Map Visualizer

Open **[http://localhost:8000](http://localhost:8000)** in your browser:
1. Type a place name in **Start** (e.g. `Ishapore` or `Koramangala`) and **End** (e.g. `Barrackpore` or `Indiranagar`).
2. Select from the real-time **Autocomplete dropdown** or click anywhere on the map to drop pins.
3. Switch routing profiles (**🚗 Car**, **🚲 Bike**, **🚶 Foot**) and click **Calculate Route** to render turn-by-turn routes with distance and duration metrics.

---

## 🛠️ CLI Tooling (`marg`)

Marg comes with a rich terminal command-line tool:

```powershell
marg serve          # Start the FastAPI engine (supports --host, --port, --reload)
marg health         # Probe status and response latencies of all engine backends
marg data download  # Download OSM regional PBF extracts (bengaluru, delhi, mumbai)
marg data build     # Parse OSM PBF and compile routing graphs + geocode indices
marg test-route     # Compute and display a route directly in your terminal
marg audit          # Run an instant dependency vulnerability scan via pip-audit
```

---

## 📡 API Endpoints

See the full [API Specification](docs/api.md) for detailed schemas and parameter tables.

| Method | Endpoint | Description | Example Query |
|---|---|---|---|
| `GET` | `/route` | Turn-by-turn routing (Foot, Car, Bike) | `?start=12.9352,77.6245&end=12.9716,77.5946&profile=car` |
| `GET` | `/geocode` | Forward geocoding: Place Name ➔ Coordinates | `?q=Connaught+Place+Delhi&limit=5` |
| `GET` | `/geocode/reverse` | Reverse geocoding: Coordinates ➔ Address | `?lat=12.9352&lon=77.6245` |
| `GET` | `/search` | POI & place keyword search with proximity bias | `?q=hospital&near_lat=12.93&near_lon=77.62` |
| `GET` | `/tiles/{z}/{x}/{y}.pbf` | Vector map tile service | `/tiles/12/2855/1912.pbf` |
| `GET` | `/health` | Health and readiness status for all backends | `/health` |
| `POST` | `/telemetry/ping` | Phase 2: DPDP 2023-compliant anonymized pings | *(Disabled by default)* |

---

## 🐳 Production Deployment (Docker Compose)

For high-throughput production environments with containerized OSRM and Nominatim:

```powershell
# Start all microservices: Marg Gateway, 3x OSRM engines, and Nominatim
docker compose up -d

# Verify system health
marg health
```

---

## 🧪 Testing & Validation

```powershell
# Run the complete test suite (110+ tests)
pytest -v

# Run with test coverage report
pytest --cov=marg --cov-report=term-missing
```

---

## 📈 Scaling Path

| Phase | Milestone | Scope & Dataset |
|---|---|---|
| **Phase 1 (Current)** | Pilot City Deployments | Bengaluru, Delhi NCR, Mumbai sub-region extracts |
| **Phase 2** | Full India Coverage | Full `india-latest.osm.pbf` Geofabrik import (~1.2 GB) |
| **Phase 3** | National Vector Tiles | Country-wide PMTiles archive generation (Zoom 0–14) |
| **Phase 4** | Traffic-Aware Routing | Telemetry speed profile aggregation for dynamic OSRM routing |

*Read the complete [Scaling Architecture Guide](docs/scaling.md).*

---

## 👤 Publisher & Author

**Avik Ghosh**  
- **GitHub**: [@avikengineer007](https://github.com/avikengineer007)  
- **Repository**: [Marg-First-indigenious-mapping-system](https://github.com/avikengineer007/Marg-First-indigenious-mapping-system)

---

## 📄 Copyright & Rights

Copyright © 2026 **Avik Ghosh**. All Rights Reserved.
