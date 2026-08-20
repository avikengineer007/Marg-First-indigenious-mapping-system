# Scaling Path: Pilot Cities → Full India Coverage

## Phase 1 (Current): 2–3 Pilot Cities

| City | OSM Source | Size Estimate |
|---|---|---|
| Bengaluru | `karnataka-latest.osm.pbf` | ~120 MB |
| Delhi NCR | `delhi-latest.osm.pbf` | ~80 MB |
| Mumbai | `maharashtra-latest.osm.pbf` | ~200 MB |

Stack per pilot:
- OSRM pre-processed graph per city, per profile (3 profiles × 3 cities = 9 graph instances, or 3 OSRM servers with multi-profile)
- Nominatim indexed from sub-region PBF
- PMTiles archive clipped to city bbox via `pmtiles extract`

---

## Phase 2: Full India Coverage

### Data source
```
https://download.geofabrik.de/asia/india-latest.osm.pbf
```
Size: ~800 MB–1.5 GB compressed PBF.

### OSRM scaling
- Replace per-city graph files with full India `india-latest.osrm`
- OSRM MLD algorithm scales well to country-level; expect 8–16 GB RAM per profile instance
- Recommended: 3 OSRM containers (foot/car/bike), each with 16 GB RAM assigned

### Nominatim scaling
- Nominatim full India import: ~24–48 hours first import, ~50 GB PostgreSQL storage
- Use `mediagis/nominatim` Docker image with `IMPORT_STYLE=extratags` for full POI coverage
- Incremental updates via Geofabrik replication URL

### Tile scaling
- Generate full India PMTiles archive using `planetiler` (Java) or `tilemaker` (C++)
- Clip zoom levels 0–14 for vector tiles: ~2–5 GB for India
- Host using the existing `/tiles` endpoint — no API changes needed

### Resource estimate (full India)

| Component | RAM | Disk |
|---|---|---|
| OSRM foot | 8–12 GB | 4 GB |
| OSRM car | 8–12 GB | 4 GB |
| OSRM bike | 8–12 GB | 4 GB |
| Nominatim + Postgres | 8 GB | 60 GB |
| Tiles PMTiles archive | — | 5 GB |
| Marg API | 512 MB | — |
| **Total** | **~45 GB RAM** | **~77 GB disk** |

---

## Phase 3: Regional Updates

Use the `marg data download` + `marg data build` CLI commands to refresh data for a region without full redeployment:

```powershell
# Refresh Bengaluru data
marg data download --region bengaluru
marg data build --region bengaluru
# Restart only the OSRM foot/car/bike containers for Bengaluru
docker compose restart marg-osrm-car marg-osrm-foot marg-osrm-bike
```

For Nominatim, use Geofabrik replication to apply incremental OSM changesets:
```bash
docker exec marg-nominatim nominatim replication --once
```

---

## Phase 4: Traffic-Aware Routing (Phase 2 of Project Roadmap)

Once telemetry data is collected from consenting users:

1. Aggregate anonymized pings into road-segment speed observations per time-of-day bucket
2. Export as a speed profile CSV for OSRM's traffic extension (`osrm-traffic`)
3. Apply speed profiles to OSRM graph without full re-extraction:
   ```bash
   osrm-contract --segment-speed-file speed_profiles.csv region.osrm
   ```
4. Reload OSRM containers — no API changes required

This provides Waze-style traffic-aware routing without requiring real-time data in the critical path.
