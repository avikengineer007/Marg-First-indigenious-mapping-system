# Geolocation Service — External Dependency Contract

**Marg** consumes device position estimation as an external dependency. The Geolocation Engine runs as a decoupled standalone service (outside Marg's codebase) providing IP-based geolocation, crowd-sourced WiFi BSSID/SSID multilateration, and Cell Tower triangulation.

---

## 1. Architectural Role & Boundary

```
+-------------------------------------------------------------+
|                  Client Application (e.g. Saheli)           |
+-------------------------------------------------------------+
               |                               |
       (1) Position Query             (2) Route / Search
               v                               v
+-------------------------------+   +-------------------------+
|  Geolocation Engine (External)|   |   Marg Engine (Local)   |
|  - IP Geolocation             |   |   - Deterministic Route |
|  - WiFi MAC Multilateration   |   |   - Geocoding & Search  |
|  - Cell Tower Triangulation   |   |   - Map Tile Serving    |
+-------------------------------+   +-------------------------+
```

1. **Client-Driven Calling**: Downstream mobile and web applications (such as pedestrian safety apps) call the Geolocation engine directly to acquire initial or fallback coordinates when hardware GPS is weak/unavailable.
2. **Marg Integration**: Marg's endpoints (`/route`, `/search`, `/route/track`) accept generic `lat,lon` coordinates. When a client needs position estimation alongside routing or search, it calls the Geolocation service first, validates the result within India's bounding box, and passes the coordinates to Marg.
3. **Decoupled Lifecycle**: The Geolocation service has its own independent database (MaxMind GeoLite2/GeoIP2, OpenCellID, MLS WiFi databases), deployment lifecycle, and rate limits.

---

## 2. API Contract Specification

Base URL: `http://localhost:8080` (or configured environment variable `GEOLOCATION_SERVICE_URL`)

### `POST /v1/geolocate`

Estimate geographic position from available network signals.

#### Request Headers
```http
Content-Type: application/json
X-Client-Id: <client_identifier>
```

#### Request Payload
```json
{
  "ip_address": "49.207.200.12",
  "wifi_access_points": [
    {
      "bssid": "00:14:22:01:23:45",
      "signal_strength_dbm": -65,
      "channel": 6,
      "ssid": "Public_WiFi"
    },
    {
      "bssid": "00:14:22:01:23:46",
      "signal_strength_dbm": -72,
      "channel": 11
    }
  ],
  "cell_towers": [
    {
      "mcc": 404,
      "mnc": 45,
      "lac": 12345,
      "cell_id": 67890,
      "signal_strength_dbm": -80
    }
  ],
  "fallbacks": {
    "ip": true,
    "lac": true
  }
}
```

#### Request Field Schema

| Field | Type | Description |
|---|---|---|
| `ip_address` | string (optional) | IPv4 or IPv6 client IP address |
| `wifi_access_points` | array of objects (optional) | Observed 802.11 BSSIDs and RSSI signals |
| `wifi[].bssid` | string (required if wifi) | Standard colon-delimited MAC address |
| `wifi[].signal_strength_dbm` | integer | RSSI in dBm (typically -100 to -30) |
| `cell_towers` | array of objects (optional) | Cellular tower identifiers (GSM/LTE/5G NR) |
| `cell[].mcc` | integer (required) | Mobile Country Code (404/405 for India) |
| `cell[].mnc` | integer (required) | Mobile Network Code |
| `cell[].lac` | integer (required) | Location Area Code / TAC |
| `cell[].cell_id` | integer (required) | Cell Identity |
| `fallbacks.ip` | boolean | Fallback to IP database if radio signals fail (default: `true`) |

---

### Response Schemas

#### 200 OK — Successful Position Estimation
```json
{
  "status": "ok",
  "location": {
    "lat": 12.93524,
    "lon": 77.62448
  },
  "accuracy_m": 45.0,
  "method": "wifi_multilateration",
  "country_code": "IN",
  "in_india_bounds": true,
  "confidence_score": 0.88,
  "timestamp_ms": 1700000000000
}
```

#### Response Fields:
- `location.lat`: Latitude float (WGS84)
- `location.lon`: Longitude float (WGS84)
- `accuracy_m`: Estimated circular 1-sigma radius in meters
- `method`: Position resolution method:
  - `wifi_multilateration` (typical accuracy: 15–50m)
  - `cell_triangulation` (typical accuracy: 200–1500m)
  - `ip_lookup` (typical accuracy: 2,000–25,000m)
- `in_india_bounds`: `true` if coordinates fall within 6.0°–37.5° N, 68.0°–97.5° E
- `confidence_score`: 0.0 to 1.0 heuristic based on signal count and beacon density

#### 400 Bad Request — Validation or Scope Error
```json
{
  "status": "error",
  "error_code": "OUT_OF_BOUNDS",
  "detail": "Resolved coordinates (lat: 51.5074, lon: -0.1278) fall outside India geographic scope."
}
```

#### 404 Not Found — No Location Signals Resolved
```json
{
  "status": "error",
  "error_code": "LOCATION_NOT_FOUND",
  "detail": "Provided BSSID/Cell signals could not be matched in database and IP fallback is disabled."
}
```

---

## 3. Fail-Closed India Scope Validation

Consistent with Marg's non-negotiable principles:
1. **India-Only Bounding Box**: The geolocation engine rejects or tags coordinates outside `[6.0, 37.5]` Lat and `[68.0, 97.5]` Lon.
2. **No Fallback Guessing**: If radio signals are ambiguous or unknown, an explicit `404` or `LOCATION_NOT_FOUND` is returned rather than defaulting to a city center or capital without basis.

---

## 4. Privacy & Compliance Boundaries

- **Zero User Identification**: Requests do not require or accept user accounts, names, or device IMEI/IMSI numbers.
- **Ephemeral Processing**: Signal queries for position resolution are processed in-memory. Radio scans are not persisted to user profiles.
- **Log Hygiene**: Signal lists and MAC addresses are omitted from server access logs.
