# Scaling Path: Pilot Cities → Full India Coverage

## Phase 1 (Current): 4 Pilot Cities / Sub-Regions

| City / Region | OSM Extract Source | Size Estimate | Primary Focus |
|---|---|---|---|
| **Bengaluru** | `karnataka-latest.osm.pbf` | ~120 MB | Tech corridor, dense ring roads |
| **Delhi NCR** | `delhi-latest.osm.pbf` | ~80 MB | Complex multi-tier flyovers, expressways |
| **Mumbai** | `maharashtra-latest.osm.pbf` | ~200 MB | Linear coastal topology, sea links |
| **West Bengal (Kolkata)** | `west-bengal-latest.osm.pbf` | ~150 MB | Arterial trunk roads (SH1/BT Road), river crossings |

Stack per pilot:
- Local/Containerized OSRM graph per city per profile (`foot`, `car`, `bike`) with expanded snapping radius (`radiuses=1000;1000`).
- Self-hosted Nominatim indexed from sub-region PBF.
- PMTiles archive clipped to city bounding box.
- Topological gap repair heuristic with `synthetic: true` edge tagging.

---

## Architectural Evaluation: Routing Engine Selection

For Indian urban and semi-urban road networks, choosing the right graph routing algorithm is a foundational architectural decision:

| Feature | OSRM (Contraction Hierarchies - CH) | OSRM (Multi-Level Dijkstra - MLD) | Valhalla (Tile-based Multi-Modal) |
|---|---|---|---|
| **Query Latency** | **< 1ms** (Ultra fast) | 5–15ms (Fast) | 10–25ms (Fast) |
| **Preprocessing Time** | High (Rigid contraction) | Medium (Partitioning) | Fast (Hierarchical tiling) |
| **Dynamic Costing / Penalties** | ❌ No (Requires graph re-compilation) | ⚠️ Partial (Live speed updates via CSV) | ✅ **Full** (Dynamic edge/turn costing per query) |
| **Snapping / Off-road Tolerance** | Strict radius requirement | Flexible snapping | **Highest** (Multi-tier projection) |
| **Topological Island Resilience** | Low (Breaks on disconnected nodes) | Medium | **High** (Graceful fallback snapping) |
| **Memory Footprint (per city)** | ~150–300 MB RAM | ~250–500 MB RAM | ~200–400 MB RAM |
| **Marg Recommendation** | **Phase 1 Pilot Engine** (Low latency, predictable) | **Phase 2 Traffic Engine** (Dynamic weights) | **Target Production Architecture** (Dynamic costing for Indian conditions) |

---

## Topological Gap Repair & Audit Escape Hatch

In Indian regional OSM extracts, localized topological gaps can occur where residential lanes visually approach but are not connected at the node level to main arterials:

1. **Synthetic Edge Bridging**: `RoadGraph.bridge_dead_ends(max_gap_m=30)` identifies dead-end nodes within 30m of navigable edges and creates synthetic transition links.
2. **Auditability**: All heuristic edges are explicitly marked `is_synthetic = True` and penalised with a 1.8x traversal cost multiplier to ensure ground-truth OSM ways are always chosen when available.
3. **Runtime Escape Hatch**: Can be globally disabled via `MARG_ENABLE_SYNTHETIC_BRIDGING=false` if auditing shows unwanted shortcuts across walls or compound barriers.

---

## Phase 2: Full India Coverage (Deferred until Pilots are Solid)

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
