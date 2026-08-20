# Marg API Documentation

Base URL: `http://localhost:8000`

Interactive docs (Swagger UI): `http://localhost:8000/docs`

---

## Geographic Scope

All coordinates must fall within India's bounding box:
- **Latitude**: 6.0° – 37.5° N
- **Longitude**: 68.0° – 97.5° E

Requests with coordinates outside this box return `400 Bad Request`.

---

## Common Response Envelope

Success responses always include a `status: "ok"` field.
Error responses from validation return structured JSON — never raw stack traces.

```json
{ "detail": "Descriptive error message" }
```

---

## `GET /route`

Calculate a route between two coordinates.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `start` | string | ✓ | Start coordinate as `lat,lon` (e.g. `12.9352,77.6245`) |
| `end` | string | ✓ | End coordinate as `lat,lon` |
| `profile` | string | ✓ | `foot` / `car` / `bike` |
| `steps` | boolean | | Include turn-by-turn steps (default: `true`) |
| `overview` | string | | Geometry detail: `full` / `simplified` / `false` (default: `full`) |

### Response (200 OK)

```json
{
  "status": "ok",
  "profile": "car",
  "distance_m": 4230.5,
  "duration_s": 720.0,
  "geometry": {
    "type": "LineString",
    "coordinates": [[77.6245, 12.9352], [77.5946, 12.9716]]
  },
  "steps": [
    {
      "instruction": "Head north on Hosur Road",
      "distance_m": 210.0,
      "duration_s": 45.0,
      "maneuver": "depart"
    }
  ],
  "waypoints": [
    { "name": "Start", "lat": 12.9352, "lon": 77.6245 },
    { "name": "End", "lat": 12.9716, "lon": 77.5946 }
  ]
}
```

### No Route (200 OK)

```json
{ "status": "no_route", "detail": "No route found..." }
```

---

## `POST /route/track`

Real-time position tracking and deterministic off-route recalculation for active navigation sessions.

> **Privacy & DPDP Guarantee:** Position updates sent to `/route/track` are processed **strictly in-memory per request** and are **never persisted, stored in databases, or logged as raw GPS coordinates**. This is a functional navigation loop distinct from Phase 2 aggregated telemetry.

### Request Body

```json
{
  "lat": 12.9360,
  "lon": 77.6250,
  "destination": "12.9716,77.5946",
  "profile": "car",
  "route_geometry": {
    "type": "LineString",
    "coordinates": [[77.6245, 12.9352], [77.5946, 12.9716]]
  },
  "off_route_threshold_m": 50.0,
  "steps": true,
  "overview": "full"
}
```

### Parameters

| Field | Type | Required | Description |
|---|---|---|---|
| `lat` | float | ✓ | Current device latitude (India-scoped) |
| `lon` | float | ✓ | Current device longitude (India-scoped) |
| `destination` | string | ✓ | Trip destination as `lat,lon` |
| `profile` | string | | Routing profile: `foot` / `car` / `bike` (default: `car`) |
| `route_geometry` | object | | Active GeoJSON `LineString` route geometry |
| `off_route_threshold_m` | float | | Deviation threshold in meters (default: `50.0`) |
| `steps` | boolean | | Include steps in reroute (default: `true`) |
| `overview` | string | | Geometry detail: `full` / `simplified` / `false` |

### Response: On Track (`off_route: false`)

```json
{
  "status": "ok",
  "off_route": false,
  "distance_to_route_m": 8.4,
  "message": "On track.",
  "reroute": null
}
```

### Response: Off Route (`off_route: true` with automatic re-route)

```json
{
  "status": "ok",
  "off_route": true,
  "distance_to_route_m": 85.2,
  "message": "Off-route detected. New route calculated.",
  "reroute": {
    "status": "ok",
    "profile": "car",
    "distance_m": 4120.0,
    "duration_s": 690.0,
    "geometry": {
      "type": "LineString",
      "coordinates": [[77.6250, 12.9360], [77.5946, 12.9716]]
    },
    "steps": [ ... ],
    "waypoints": [ ... ]
  }
}
```

---

## External Geolocation Service

For device position estimation (IP, WiFi BSSID/SSID multilateration, Cell Tower triangulation), see the standalone contract:
- [`docs/geolocation_contract.md`](./geolocation_contract.md)

---

## `GET /geocode`

Forward geocoding: address or place name → coordinates.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `q` | string | ✓ | Place name or address (max 256 chars) |
| `limit` | integer | | Max results, 1–10 (default: 5) |

### Response

```json
{
  "status": "ok",
  "results": [
    {
      "display_name": "Koramangala, Bengaluru, Karnataka, India",
      "lat": 12.9352,
      "lon": 77.6245,
      "bbox": [12.9100, 12.9600, 77.6000, 77.6500],
      "place_type": "suburb"
    }
  ]
}
```

---

## `GET /geocode/reverse`

Reverse geocoding: coordinates → address.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `lat` | float | ✓ | Latitude (within India bounds) |
| `lon` | float | ✓ | Longitude (within India bounds) |

### Response

```json
{
  "status": "ok",
  "display_name": "Koramangala, Bengaluru, Karnataka 560034, India",
  "lat": 12.9352,
  "lon": 77.6245,
  "address": {
    "suburb": "Koramangala",
    "city": "Bengaluru",
    "state": "Karnataka",
    "postcode": "560034",
    "country": "India"
  }
}
```

---

## `GET /search`

POI and place keyword search within India.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `q` | string | ✓ | Search keyword |
| `category` | string | | OSM tag key (e.g. `amenity`, `shop`) |
| `category_value` | string | | OSM tag value (e.g. `hospital`, `supermarket`) |
| `near_lat` | float | | Proximity bias latitude |
| `near_lon` | float | | Proximity bias longitude |
| `limit` | integer | | Max results, 1–20 (default: 10) |

### Response

```json
{
  "status": "ok",
  "query": "hospital",
  "results": [
    {
      "name": "Manipal Hospital",
      "display_name": "Manipal Hospital, Old Airport Road, Bengaluru",
      "lat": 12.9589,
      "lon": 77.6486,
      "category": "amenity",
      "type": "hospital",
      "distance_m": 340.5
    }
  ]
}
```

---

## `GET /tiles/style.json`

MapLibre GL style JSON for the Marg tile layer.

---

## `GET /tiles/{z}/{x}/{y}.{ext}`

Map tile serving. Supported extensions: `pbf`, `mvt`, `png`, `jpg`, `webp`.

Returns `204 No Content` if the tile is not available (standard slippy-map behaviour — not an error).

---

## `GET /health`

System health check.

### Response

```json
{
  "status": "degraded",
  "version": "0.1.0",
  "uptime_s": 342.1,
  "backends": [
    { "name": "osrm-foot", "status": "ok", "latency_ms": 12.3 },
    { "name": "osrm-car", "status": "ok", "latency_ms": 11.1 },
    { "name": "osrm-bike", "status": "ok", "latency_ms": 13.2 },
    { "name": "nominatim", "status": "unavailable", "note": "not configured" },
    { "name": "geocode-db", "status": "ok" },
    { "name": "tiles", "status": "unavailable", "note": "file missing or empty" }
  ]
}
```

`status` values: `ok` | `degraded` | `unavailable`

---

## `POST /telemetry/ping`

**Phase 2 only — disabled by default** (`MARG_TELEMETRY_ENABLED=false`).

DPDP 2023-compliant anonymized location ping ingestion.

### Required header

```
X-Marg-Consent: 1
```

Must only be set after obtaining explicit user consent. Absent or wrong value → `403 Forbidden`.

### Request body

```json
{
  "session_id": "ephemeral-session-abc123",
  "lat": 12.9352,
  "lon": 77.6245,
  "speed_kmh": 30.0,
  "heading_deg": 180.0,
  "timestamp_ms": 1700000000000
}
```

- `session_id`: Never stored raw — pseudonymized with 24h rolling salt before persistence
- `speed_kmh`: Must be 0–250; rejected otherwise
- `lat`/`lon`: Must be within India bounds

### Response (202 Accepted)

```json
{ "status": "accepted" }
```

---

## Error Codes

| HTTP Code | Meaning |
|---|---|
| 400 | Validation error (malformed coordinates, invalid profile, injection attempt) |
| 403 | Consent missing (telemetry endpoint only) |
| 404 | Resource not found |
| 422 | Request body schema error |
| 429 | Rate limit exceeded |
| 500 | Internal error (generic — no internal detail exposed) |
| 503 | Feature disabled (e.g. telemetry endpoint with master switch off) |
