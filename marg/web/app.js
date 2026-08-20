/**
 * Marg Web UI — MapLibre GL interactive test interface
 *
 * Connects to the local Marg API (/route, /geocode, /search, /health)
 * and renders results on an interactive map.
 */

'use strict';

// ─── Config ──────────────────────────────────────────────────────────────────

const API_BASE = '';  // relative — served from the same origin as the Marg API

// India bbox for map constraints
const INDIA_BOUNDS = [[68.0, 6.0], [97.5, 37.5]];
const INDIA_CENTER = [78.9629, 20.5937];

// Pilot city centers for quick reference
const PILOT_CITIES = {
  bengaluru: { center: [77.5946, 12.9716], zoom: 12 },
  delhi:     { center: [77.2090, 28.6139], zoom: 11 },
  mumbai:    { center: [72.8777, 19.0760], zoom: 12 },
};

// Click-to-set waypoint state
let clickMode = 'start';  // 'start' | 'end'
let startMarker = null;
let endMarker = null;
let routeLayerId = null;
let poiMarkers = [];
let geocodeMarkers = [];

// ─── Map initialization ───────────────────────────────────────────────────────

const map = new maplibregl.Map({
  container: 'map',
  style: {
    version: 8,
    name: 'Marg Dark',
    sources: {
      'osm-raster': {
        type: 'raster',
        tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '© OpenStreetMap contributors',
        maxzoom: 19,
      },
    },
    layers: [
      { id: 'osm-raster', type: 'raster', source: 'osm-raster',
        paint: {
          'raster-brightness-min': 0,
          'raster-brightness-max': 0.35,
          'raster-saturation': -0.5,
          'raster-hue-rotate': 200,
          'raster-contrast': 0.2,
        }
      },
    ],
  },
  center: INDIA_CENTER,
  zoom: 4.5,
  maxBounds: [[60.0, 2.0], [105.0, 42.0]],  // loose India+neighbours
});

map.addControl(new maplibregl.NavigationControl(), 'bottom-right');
map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');

// ─── Fetch version ────────────────────────────────────────────────────────────

async function loadVersion() {
  try {
    const r = await fetch(`${API_BASE}/health`);
    if (r.ok) {
      const d = await r.json();
      document.getElementById('version-badge').textContent = `v${d.version || '—'}`;
    }
  } catch (_) {}
}
loadVersion();

// ─── Tab navigation ───────────────────────────────────────────────────────────

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    btn.setAttribute('aria-selected', 'true');
    document.getElementById(btn.dataset.tab).classList.add('active');
  });
});

// ─── Profile toggle ───────────────────────────────────────────────────────────

let selectedProfile = 'car';
document.querySelectorAll('.profile-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.profile-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    selectedProfile = btn.dataset.profile;
  });
});

// ─── Map click → waypoint setter ─────────────────────────────────────────────

map.on('click', e => {
  const { lat, lng } = e.lngLat;
  const coord = `${lat.toFixed(6)},${lng.toFixed(6)}`;

  if (clickMode === 'start') {
    document.getElementById('start-input').value = coord;
    placeMarker('start', lat, lng);
    clickMode = 'end';
    updateClickHint('end');
  } else {
    document.getElementById('end-input').value = coord;
    placeMarker('end', lat, lng);
    clickMode = 'start';
    updateClickHint('start');
  }
});

function updateClickHint(next) {
  document.getElementById('click-hint').textContent =
    `Click map to set ${next === 'start' ? 'Start' : 'End'} waypoint`;
}

function placeMarker(type, lat, lng) {
  const el = document.createElement('div');
  el.className = `map-marker-${type}`;
  el.style.cssText = `
    width: 16px; height: 16px;
    border-radius: 50%;
    border: 3px solid ${type === 'start' ? '#3fb950' : '#f85149'};
    background: ${type === 'start' ? 'rgba(63,185,80,0.5)' : 'rgba(248,81,73,0.5)'};
    box-shadow: 0 0 0 4px ${type === 'start' ? 'rgba(63,185,80,0.2)' : 'rgba(248,81,73,0.2)'};
    cursor: pointer;
  `;
  if (type === 'start') {
    if (startMarker) startMarker.remove();
    startMarker = new maplibregl.Marker({ element: el }).setLngLat([lng, lat]).addTo(map);
  } else {
    if (endMarker) endMarker.remove();
    endMarker = new maplibregl.Marker({ element: el }).setLngLat([lng, lat]).addTo(map);
  }
}

// ─── Location Resolver & Autocomplete ───────────────────────────────────────

function isCoordinateString(str) {
  const parts = str.split(',').map(s => s.trim());
  if (parts.length !== 2) return false;
  const lat = parseFloat(parts[0]);
  const lon = parseFloat(parts[1]);
  return !isNaN(lat) && !isNaN(lon) && lat >= 6.0 && lat <= 37.5 && lon >= 68.0 && lon <= 97.5;
}

async function resolveLocation(inputVal, type) {
  const trimmed = inputVal.trim();
  if (!trimmed) throw new Error(`Please provide a ${type} location.`);

  if (isCoordinateString(trimmed)) {
    const [lat, lon] = trimmed.split(',').map(s => parseFloat(s.trim()));
    placeMarker(type, lat, lon);
    return { lat, lon, formatted: `${lat.toFixed(5)},${lon.toFixed(5)}` };
  }

  // Forward geocode place name
  const r = await fetch(`${API_BASE}/geocode?q=${encodeURIComponent(trimmed)}&limit=1`);
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || `Geocoding failed for "${trimmed}"`);
  }
  const data = await r.json();
  if (!data.results || data.results.length === 0) {
    throw new Error(`Location "${trimmed}" not found. Try a nearby area or city.`);
  }

  const match = data.results[0];
  placeMarker(type, match.lat, match.lon);
  return {
    lat: match.lat,
    lon: match.lon,
    formatted: `${match.lat.toFixed(5)},${match.lon.toFixed(5)}`,
    displayName: match.display_name
  };
}

// Setup Autocomplete for Start & End inputs
function setupAutocomplete(inputId, dropdownId, type) {
  const input = document.getElementById(inputId);
  const dropdown = document.getElementById(dropdownId);
  let debounceTimer = null;

  input.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    const query = input.value.trim();
    if (query.length < 2 || isCoordinateString(query)) {
      dropdown.innerHTML = '';
      dropdown.classList.add('hidden');
      return;
    }

    debounceTimer = setTimeout(async () => {
      try {
        const r = await fetch(`${API_BASE}/geocode?q=${encodeURIComponent(query)}&limit=4`);
        if (!r.ok) return;
        const data = await r.json();
        const results = data.results || [];
        if (results.length === 0) {
          dropdown.innerHTML = '';
          dropdown.classList.add('hidden');
          return;
        }

        dropdown.innerHTML = '';
        results.forEach(res => {
          const item = document.createElement('div');
          item.className = 'suggestion-item';
          const title = res.display_name.split(',')[0] || res.name || query;
          item.innerHTML = `
            <div class="suggestion-title">${escHtml(title)}</div>
            <div class="suggestion-sub">${escHtml(res.display_name)}</div>
          `;
          item.addEventListener('click', () => {
            input.value = title;
            input.dataset.lat = res.lat;
            input.dataset.lon = res.lon;
            placeMarker(type, res.lat, res.lon);
            map.flyTo({ center: [res.lon, res.lat], zoom: 13 });
            dropdown.innerHTML = '';
            dropdown.classList.add('hidden');
          });
          dropdown.appendChild(item);
        });
        dropdown.classList.remove('hidden');
      } catch (_) {}
    }, 280);
  });

  // Hide dropdown on outside click
  document.addEventListener('click', e => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.classList.add('hidden');
    }
  });
}

setupAutocomplete('start-input', 'start-suggestions', 'start');
setupAutocomplete('end-input', 'end-suggestions', 'end');

// ─── Route ────────────────────────────────────────────────────────────────────

document.getElementById('route-btn').addEventListener('click', async () => {
  const startRaw = document.getElementById('start-input').value.trim();
  const endRaw   = document.getElementById('end-input').value.trim();
  if (!startRaw || !endRaw) { showToast('Enter start and end location names or coordinates.', 'error'); return; }

  const btn = document.getElementById('route-btn');
  btn.textContent = 'Finding route…';
  btn.classList.add('loading');

  try {
    // 1. Resolve start location (name -> coords if needed)
    showToast('Resolving start location…', 'info');
    const startLoc = await resolveLocation(startRaw, 'start');

    // 2. Resolve end location (name -> coords if needed)
    showToast('Resolving destination…', 'info');
    const endLoc = await resolveLocation(endRaw, 'end');

    showToast('Calculating optimal route…', 'info');
    const params = new URLSearchParams({
      start: startLoc.formatted,
      end: endLoc.formatted,
      profile: selectedProfile,
      steps: 'true'
    });

    const r = await fetch(`${API_BASE}/route?${params}`);
    const data = await r.json();

    if (data.status === 'no_route') {
      showToast('No route found between these points.', 'error');
      return;
    }
    if (data.status !== 'ok') {
      showToast(data.detail || 'Route request failed.', 'error');
      return;
    }

    renderRoute(data);
    renderRouteResult(data);
    showToast(`Route found: ${(data.distance_m / 1000).toFixed(1)} km`, 'success');
  } catch (e) {
    showToast(`${e.message}`, 'error');
  } finally {
    btn.textContent = 'Calculate Route';
    btn.classList.remove('loading');
  }
});

let activeRouteData = null;
let activeRouteGeometry = null;

function renderRoute(data) {
  activeRouteData = data;
  activeRouteGeometry = data.geometry;

  // Remove old route layer
  if (routeLayerId) {
    if (map.getLayer(routeLayerId)) map.removeLayer(routeLayerId);
    if (map.getSource(routeLayerId)) map.removeSource(routeLayerId);
    if (map.getLayer(`${routeLayerId}-shadow`)) map.removeLayer(`${routeLayerId}-shadow`);
  }

  const profileColors = { car: '#79c0ff', bike: '#f0883e', foot: '#56d364' };
  const color = profileColors[data.profile] || '#4f9cf9';

  routeLayerId = `route-${Date.now()}`;
  map.addSource(routeLayerId, { type: 'geojson', data: { type: 'Feature', geometry: data.geometry } });

  // Shadow
  map.addLayer({
    id: `${routeLayerId}-shadow`,
    type: 'line',
    source: routeLayerId,
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': '#000', 'line-width': 10, 'line-opacity': 0.3, 'line-blur': 4 },
  });

  // Main line
  map.addLayer({
    id: routeLayerId,
    type: 'line',
    source: routeLayerId,
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': color, 'line-width': 5, 'line-opacity': 0.95 },
  });

  // Fit map to route
  if (data.geometry?.coordinates?.length) {
    const coords = data.geometry.coordinates;
    const lngs = coords.map(c => c[0]);
    const lats = coords.map(c => c[1]);
    map.fitBounds(
      [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
      { padding: 60, maxZoom: 16 }
    );
  }
}

// ─── Live Tracking & Simulation ───────────────────────────────────────────────

let liveUserMarker = null;
let simInterval = null;
let simStepIndex = 0;
let currentSimPos = null;

const trackThresholdSlider = document.getElementById('track-threshold');
if (trackThresholdSlider) {
  trackThresholdSlider.addEventListener('input', (e) => {
    document.getElementById('threshold-val').textContent = e.target.value;
  });
}

function getLiveMarker() {
  if (!liveUserMarker) {
    const el = document.createElement('div');
    el.className = 'user-live-marker';
    liveUserMarker = new maplibregl.Marker({ element: el })
      .setLngLat(INDIA_CENTER)
      .addTo(map);
  }
  return liveUserMarker;
}

async function sendTrackingPing(lat, lon, isDrift = false) {
  const destInput = document.getElementById('track-dest-input');
  const destination = destInput?.value.trim() || (endMarker ? `${endMarker.getLngLat().lat},${endMarker.getLngLat().lng}` : '12.9716,77.5946');
  const threshold = parseFloat(trackThresholdSlider?.value || 50.0);

  const payload = {
    lat: lat,
    lon: lon,
    destination: destination,
    profile: selectedProfile,
    route_geometry: activeRouteGeometry,
    off_route_threshold_m: threshold,
    steps: true,
  };

  try {
    const r = await fetch(`${API_BASE}/route/track`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await r.json();

    const resultCard = document.getElementById('track-result');
    const badge = document.getElementById('track-status-badge');
    const devEl = document.getElementById('track-deviation');
    const msgEl = document.getElementById('track-message');
    if (resultCard) resultCard.classList.remove('hidden');

    if (data.status === 'ok') {
      devEl.textContent = `${data.distance_to_route_m} m`;
      if (data.off_route) {
        badge.textContent = 'Off Route';
        badge.style.color = 'var(--warning)';
        msgEl.textContent = '⚠️ Off-route deviation detected! Automatic recalculation triggered.';
        showToast('Off-route detected — rerouting!', 'warning');
        if (data.reroute) {
          renderRoute(data.reroute);
          activeRouteGeometry = data.reroute.geometry;
          simStepIndex = 0;
        }
      } else {
        badge.textContent = 'On Track';
        badge.style.color = 'var(--success)';
        msgEl.textContent = `Synced. Distance to path: ${data.distance_to_route_m}m.`;
      }
    } else {
      msgEl.textContent = data.detail || 'Tracking update failed.';
    }
  } catch (e) {
    showToast(`Tracking error: ${e.message}`, 'error');
  }
}

const simStartBtn = document.getElementById('sim-start-btn');
if (simStartBtn) {
  simStartBtn.addEventListener('click', async () => {
    if (simInterval) {
      clearInterval(simInterval);
      simInterval = null;
      simStartBtn.textContent = '▶ Resume Simulation';
      return;
    }

    // If no route exists, calculate sample route first
    if (!activeRouteGeometry || !activeRouteGeometry.coordinates || activeRouteGeometry.coordinates.length < 2) {
      showToast('Calculating initial route for simulation…', 'info');
      try {
        const r = await fetch(`${API_BASE}/route?start=12.9352,77.6245&end=12.9716,77.5946&profile=${selectedProfile}`);
        const data = await r.json();
        if (data.status === 'ok') {
          renderRoute(data);
          renderRouteResult(data);
        }
      } catch (_) {}
    }

    const coords = activeRouteGeometry?.coordinates || [[77.6245, 12.9352], [77.5946, 12.9716]];
    simStartBtn.textContent = '⏸ Pause Simulation';
    const marker = getLiveMarker();

    simInterval = setInterval(() => {
      if (simStepIndex >= coords.length) {
        simStepIndex = 0;
      }
      const [lon, lat] = coords[simStepIndex];
      currentSimPos = { lat, lon };
      marker.setLngLat([lon, lat]);
      sendTrackingPing(lat, lon);
      simStepIndex++;
    }, 1200);
  });
}

const simOffRouteBtn = document.getElementById('sim-offroute-btn');
if (simOffRouteBtn) {
  simOffRouteBtn.addEventListener('click', () => {
    if (!currentSimPos) {
      currentSimPos = { lat: 12.9352, lon: 77.6245 };
    }
    // Inject deviation: ~350m offset
    currentSimPos.lat += 0.003;
    currentSimPos.lon += 0.003;
    const marker = getLiveMarker();
    marker.setLngLat([currentSimPos.lon, currentSimPos.lat]);
    map.flyTo({ center: [currentSimPos.lon, currentSimPos.lat], zoom: 15 });
    sendTrackingPing(currentSimPos.lat, currentSimPos.lon, true);
  });
}

function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '0 min';
  const totalMin = Math.round(seconds / 60);
  if (totalMin < 60) return `${totalMin} min`;
  const hrs = Math.floor(totalMin / 60);
  const mins = totalMin % 60;
  return mins > 0 ? `${hrs} hr ${mins} min` : `${hrs} hr`;
}

function renderRouteResult(data) {
  const el = document.getElementById('route-result');
  el.classList.remove('hidden');

  document.getElementById('route-distance').textContent = `${(data.distance_m / 1000).toFixed(2)} km`;
  document.getElementById('route-duration').textContent = formatDuration(data.duration_s);
  document.getElementById('route-profile-badge').textContent = data.profile;

  const stepsEl = document.getElementById('steps-list');
  stepsEl.innerHTML = '';
  (data.steps || []).forEach((step, i) => {
    const item = document.createElement('div');
    item.className = 'step-item';
    item.innerHTML = `
      <div class="step-num">${i + 1}</div>
      <div class="step-text">${escHtml(step.instruction)}</div>
      <div class="step-meta">${(step.distance_m || 0).toFixed(0)} m</div>
    `;
    stepsEl.appendChild(item);
  });
}

// ─── Geocode ──────────────────────────────────────────────────────────────────

document.getElementById('geocode-btn').addEventListener('click', async () => {
  const q = document.getElementById('geocode-input').value.trim();
  if (!q) { showToast('Enter a place name or address.', 'error'); return; }
  clearGeoMarkers();

  try {
    const r = await fetch(`${API_BASE}/geocode?q=${encodeURIComponent(q)}&limit=5`);
    const data = await r.json();
    renderGeocodeResults(data.results || [], document.getElementById('geocode-results'));
  } catch (e) {
    showToast(`Geocode error: ${e.message}`, 'error');
  }
});

document.getElementById('reverse-btn').addEventListener('click', async () => {
  const lat = document.getElementById('rev-lat').value.trim();
  const lon = document.getElementById('rev-lon').value.trim();
  if (!lat || !lon) { showToast('Enter latitude and longitude.', 'error'); return; }

  try {
    const r = await fetch(`${API_BASE}/geocode/reverse?lat=${lat}&lon=${lon}`);
    const data = await r.json();
    const el = document.getElementById('geocode-results');
    el.innerHTML = '';
    const item = document.createElement('div');
    item.className = 'result-item';
    item.innerHTML = `
      <div class="result-name">${escHtml(data.display_name || 'Unknown')}</div>
      <div class="result-coords">${data.lat}, ${data.lon}</div>
    `;
    el.appendChild(item);
    map.flyTo({ center: [data.lon, data.lat], zoom: 15 });
    addGeoMarker(data.lat, data.lon, data.display_name);
  } catch (e) {
    showToast(`Reverse geocode error: ${e.message}`, 'error');
  }
});

function renderGeocodeResults(results, container) {
  container.innerHTML = '';
  if (!results.length) {
    container.innerHTML = '<div style="color:var(--text-muted);font-size:12px;text-align:center;padding:16px">No results found</div>';
    return;
  }
  const lngs = [], lats = [];
  results.forEach(result => {
    const item = document.createElement('div');
    item.className = 'result-item';
    item.innerHTML = `
      <div class="result-name">${escHtml(result.display_name?.split(',')[0] || result.name || '—')}</div>
      <div class="result-display">${escHtml(result.display_name || '')}</div>
      <div class="result-coords">${result.lat?.toFixed(5)}, ${result.lon?.toFixed(5)}</div>
    `;
    item.addEventListener('click', () => {
      map.flyTo({ center: [result.lon, result.lat], zoom: 15 });
    });
    container.appendChild(item);
    addGeoMarker(result.lat, result.lon, result.display_name);
    lngs.push(result.lon); lats.push(result.lat);
  });
  if (lngs.length) {
    map.fitBounds([[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]], { padding: 80, maxZoom: 14 });
  }
}

// ─── Search ───────────────────────────────────────────────────────────────────

document.getElementById('search-btn').addEventListener('click', async () => {
  const q   = document.getElementById('search-input').value.trim();
  const lat = document.getElementById('near-lat').value.trim();
  const lon = document.getElementById('near-lon').value.trim();
  if (!q) { showToast('Enter a search keyword.', 'error'); return; }
  clearPoiMarkers();

  const params = new URLSearchParams({ q, limit: '10' });
  if (lat && lon) { params.set('near_lat', lat); params.set('near_lon', lon); }

  try {
    const r = await fetch(`${API_BASE}/search?${params}`);
    const data = await r.json();
    renderSearchResults(data.results || []);
  } catch (e) {
    showToast(`Search error: ${e.message}`, 'error');
  }
});

function renderSearchResults(results) {
  const container = document.getElementById('search-results');
  container.innerHTML = '';
  if (!results.length) {
    container.innerHTML = '<div style="color:var(--text-muted);font-size:12px;text-align:center;padding:16px">No results found</div>';
    return;
  }
  results.forEach(r => {
    const item = document.createElement('div');
    item.className = 'result-item';
    item.innerHTML = `
      <div class="result-name">${escHtml(r.name || r.display_name?.split(',')[0] || '—')}</div>
      <div class="result-display">${escHtml(r.display_name || '')}</div>
      ${r.distance_m != null ? `<div class="result-distance">${(r.distance_m / 1000).toFixed(2)} km away</div>` : ''}
      <div class="result-coords">${r.lat?.toFixed(5)}, ${r.lon?.toFixed(5)}</div>
    `;
    item.addEventListener('click', () => map.flyTo({ center: [r.lon, r.lat], zoom: 16 }));
    container.appendChild(item);
    addPoiMarker(r.lat, r.lon, r.name);
  });
}

// ─── Health ───────────────────────────────────────────────────────────────────

document.getElementById('health-btn').addEventListener('click', loadHealth);

async function loadHealth() {
  const container = document.getElementById('health-results');
  container.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:8px">Checking…</div>';
  try {
    const r = await fetch(`${API_BASE}/health`);
    const data = await r.json();
    container.innerHTML = '';
    (data.backends || []).forEach(b => {
      const item = document.createElement('div');
      item.className = 'health-item';
      const badgeClass = { ok: 'badge-ok', degraded: 'badge-degraded', unavailable: 'badge-unavailable' }[b.status] || '';
      item.innerHTML = `
        <div>
          <div class="health-name">${escHtml(b.name)}</div>
          ${b.note ? `<div class="health-note">${escHtml(b.note)}</div>` : ''}
        </div>
        <div style="display:flex;align-items:center;gap:10px">
          ${b.latency_ms ? `<span class="health-latency">${b.latency_ms} ms</span>` : ''}
          <span class="health-badge ${badgeClass}">${b.status}</span>
        </div>
      `;
      container.appendChild(item);
    });
  } catch (e) {
    container.innerHTML = `<div style="color:var(--error);font-size:12px;padding:8px">Failed to reach API: ${escHtml(e.message)}</div>`;
  }
}

// Auto-load health on tab switch
document.getElementById('tab-health').addEventListener('click', loadHealth);

// ─── Marker helpers ───────────────────────────────────────────────────────────

function addPoiMarker(lat, lng, name) {
  const el = document.createElement('div');
  el.style.cssText = `
    width: 10px; height: 10px; border-radius: 50%;
    background: #d29922; border: 2px solid #f0c040;
    cursor: pointer; box-shadow: 0 0 0 3px rgba(210,153,34,0.2);
  `;
  const m = new maplibregl.Marker({ element: el })
    .setLngLat([lng, lat])
    .setPopup(new maplibregl.Popup({ closeButton: false }).setText(name || `${lat}, ${lng}`))
    .addTo(map);
  poiMarkers.push(m);
}

function addGeoMarker(lat, lng, name) {
  const m = new maplibregl.Marker({ color: '#4f9cf9' })
    .setLngLat([lng, lat])
    .setPopup(new maplibregl.Popup({ closeButton: false }).setText(name || `${lat}, ${lng}`))
    .addTo(map);
  geocodeMarkers.push(m);
}

function clearPoiMarkers()     { poiMarkers.forEach(m => m.remove()); poiMarkers = []; }
function clearGeoMarkers()     { geocodeMarkers.forEach(m => m.remove()); geocodeMarkers = []; }

// ─── Toast ────────────────────────────────────────────────────────────────────

let toastTimer = null;
function showToast(msg, type = 'info') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast ${type}`;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), 4000);
}

// ─── Utils ────────────────────────────────────────────────────────────────────

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
