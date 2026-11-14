const API = `${(window.KISANX_API_BASE || '').replace(/\/$/, '')}/api/v1`;
const DEMO_STORAGE = 'kisanx-rotation-demo-v2';
const DIARY_STORAGE = 'kisanx-rotation-diary-v1';
let activeView = 'overview';
let map = null;
let activeSatelliteLayer = null;
let activeSatelliteLayerId = 'modis_terra_truecolor';
let satelliteCatalog = [];
let satelliteControlsBound = false;
let satelliteTileErrorShown = false;
let farmPolygon = null;
let demoPolygon = null;
let drawMode = false;
let drawPoints = [];
let drawMarkers = [];
let farmCache = [];
let parcelCache = [];
let lastWeather = null;
let backendConnected = false;
let speechOn = true;
let recognition = null;
let voiceLanguage = 'en-IN';
let toastTimer = null;
const $ = (id) => document.getElementById(id);

function toast(message) {
  const el = $('toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2800);
}
async function api(path, options = {}) {
  const url = path.startsWith('/api/') ? path : API + path;
  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const res = await fetch(url, {...options, headers});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.error?.message || data.detail || `Request failed (${res.status})`);
  return data;
}
function goto(view) {
  if (!document.getElementById(`view-${view}`)) return;
  activeView = view;
  document.body.classList.toggle('satellite-focus', view === 'satellite');
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === `view-${view}`));
  document.querySelectorAll('.nav-item[data-view]').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  const label = document.querySelector(`.nav-item[data-view="${view}"]`);
  $('breadcrumbCurrent').textContent = label ? label.textContent.trim().replace('BETA', '').trim() : view;
  $('sidebar').classList.remove('open');
  if (view === 'satellite') setTimeout(() => { initMap(); if (map) map.invalidateSize(); }, 100);
  if (view === 'farms') loadFarms();
  if (view === 'settings') loadProviderStatuses();
  if (view === 'research') loadResearchFeatures();
  if (view === 'soil') loadSoilHistory();
  window.scrollTo({top: 0, behavior: 'smooth'});
}

document.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => goto(b.dataset.view)));
document.querySelectorAll('[data-goto]').forEach(b => b.addEventListener('click', () => goto(b.dataset.goto)));
$('mobileMenu').addEventListener('click', () => $('sidebar').classList.toggle('open'));
$('helpTop').addEventListener('click', () => openKrishiQ());

const SATELLITE_FALLBACK_CATALOG = [
  {id:'modis_terra_truecolor',title:'NASA MODIS Terra true colour',layer:'MODIS_Terra_CorrectedReflectance_TrueColor',format:'image/jpeg',period:'Daily',resolution:'250 m class imagery',units:'RGB reflectance visualisation',summary:'Corrected-reflectance imagery for visual landscape and seasonal context.',limitation:'MODIS pixels are much larger than many small farms. Use this for landscape context, not detailed diagnosis or parcel-level crop scoring.',use:'Visual context',provider:'NASA MODIS Terra',temporal:'Daily visualisation',kind:'visualisation'},
  {id:'modis_aqua_truecolor',title:'NASA MODIS Aqua true colour',layer:'MODIS_Aqua_CorrectedReflectance_TrueColor',format:'image/jpeg',period:'Daily',resolution:'250 m class imagery',units:'RGB reflectance visualisation',summary:'Aqua afternoon-pass corrected-reflectance imagery for landscape and seasonal context.',limitation:'MODIS pixels are much larger than many small farms. This is visual context, not parcel-level crop scoring; Aqua is a separate platform from Terra.',use:'Visual context',provider:'NASA MODIS Aqua',temporal:'Daily visualisation',kind:'visualisation'},
  {id:'imerg_precipitation',title:'NASA GPM IMERG precipitation rate',layer:'IMERG_Precipitation_Rate',format:'image/png',period:'Daily visualisation',resolution:'0.1° grid · about 10 km',units:'mm/hour rate visualisation',summary:'Satellite-based precipitation-rate context derived from the GPM IMERG product.',limitation:'A gridded precipitation estimate is not a farm rain gauge. Do not report it as measured rainfall at the farmer’s exact field.',use:'Regional rainfall context',provider:'NASA GPM IMERG',temporal:'Daily browse visualisation',kind:'visualisation'},
  {id:'smap_surface',title:'NASA SMAP surface soil moisture',layer:'SMAP_L4_Analyzed_Surface_Soil_Moisture',format:'image/png',period:'Daily visualisation',resolution:'9 km grid',units:'m³/m³ visualised soil-moisture estimate',summary:'Model-assisted surface soil-moisture analysis informed by SMAP observations.',limitation:'The approximately 9 km footprint is regional context and cannot resolve moisture in an individual small parcel.',use:'Regional moisture context',provider:'NASA SMAP L4',temporal:'Daily analysis visualisation',kind:'visualisation'},
  {id:'smap_rootzone',title:'NASA SMAP root-zone soil moisture',layer:'SMAP_L4_Analyzed_Root_Zone_Soil_Moisture',format:'image/png',period:'Daily visualisation',resolution:'9 km grid',units:'m³/m³ model-derived estimate',summary:'Model-derived root-zone moisture context, not a direct root-zone sensor reading.',limitation:'The estimate is model-assisted and spatially coarse. Confirm soil water with field observation or a suitable sensor.',use:'Regional root-zone context',provider:'NASA SMAP L4',temporal:'Daily analysis visualisation',kind:'visualisation'},
  {id:'landsat_weld_ndvi',title:'Landsat WELD monthly NDVI',layer:'Landsat_WELD_NDVI_Global_Monthly',format:'image/png',period:'Monthly',resolution:'Landsat-derived 30 m class product',units:'NDVI visualisation',summary:'Monthly Landsat-derived vegetation-index visualisation for historical regional comparison.',limitation:'This is a monthly composite, not a new scene on every selected day. Confirm temporal availability before interpreting a month; cloud, mixed pixels and crop stage affect NDVI.',use:'Historical vegetation context',provider:'NASA GIBS / Landsat WELD',temporal:'Monthly composite',kind:'visualisation'},
  {id:'viirs_snpp_thermal_anomalies',title:'NASA/NOAA Suomi-NPP VIIRS thermal anomalies',layer:'VIIRS_SNPP_Thermal_Anomalies_375m_All',format:'image/png',period:'Daily',resolution:'375 m thermal anomaly product',units:'Thermal anomaly browse visualisation',summary:'Browse view of active thermal anomalies that can support regional fire awareness.',limitation:'An anomaly is not proof of crop-residue burning on a specific farm. Check date, confidence, and authoritative FIRMS records before acting.',use:'Regional fire awareness',provider:'NASA GIBS / Suomi-NPP VIIRS',temporal:'Near-real-time browse visualisation',kind:'visualisation'}
];

function getSatelliteDef(id) {
  return satelliteCatalog.find(x => x.id === id) || SATELLITE_FALLBACK_CATALOG.find(x => x.id === id) || SATELLITE_FALLBACK_CATALOG[0];
}
function setSatelliteStatus(message, state='info') {
  const el = $('satelliteStatus');
  if (!el) return;
  el.textContent = message;
  el.dataset.state = state;
  const light = document.querySelector('.sat-state-light');
  if (light) light.dataset.state = state;
}
function updateSatelliteLayerButtons(id) {
  document.querySelectorAll('[data-satellite-layer]').forEach(button => {
    const selected = button.dataset.satelliteLayer === id;
    button.classList.toggle('active', selected);
    button.setAttribute('aria-pressed', selected ? 'true' : 'false');
  });
  const select = $('satelliteLayerSelect');
  if (select && select.value !== id) select.value = id;
}
function renderSatelliteMetadata(def) {
  if (!def) return;
  const put = (id, value) => { const el = $(id); if (el) el.textContent = value || 'Not specified'; };
  put('selectedLayerTitle', def.title);
  put('selectedLayerSummary', def.summary);
  put('selectedLayerLimit', def.limitation);
  put('mapLayerLegend', def.title);
  put('mapLegendProduct', def.title);
  const kindLabels = {
    modis_terra_truecolor: 'VISUAL CONTEXT',
    imerg_precipitation: 'REGIONAL RAINFALL ESTIMATE',
    smap_surface: 'MODEL-ASSISTED ESTIMATE',
    smap_rootzone: 'MODEL-ASSISTED ESTIMATE',
    landsat_weld_ndvi: 'DERIVED INDEX VISUALISATION',
    viirs_snpp_thermal_anomalies: 'REGIONAL THERMAL ANOMALY'
  };
  put('selectedLayerBadge', kindLabels[def.id] || 'DATA VISUALISATION');
  const rows = [
    ['Provider', def.provider], ['Spatial scale', def.resolution], ['Time step', def.temporal || def.period],
    ['Units / display', def.units], ['Decision role', def.use || 'Visual context']
  ];
  const metadata = $('selectedLayerMetadata');
  if (metadata) metadata.innerHTML = rows.map(([k,v]) => `<div class="eo-meta-row"><span>${escapeHTML(k)}</span><strong>${escapeHTML(v || 'Not specified')}</strong></div>`).join('');
  updateSatelliteLayerButtons(def.id);
}
function createGibsLayer(def, selectedDate='') {
  const options = {
    layers: def.layer,
    styles: '',
    format: def.format || 'image/png',
    transparent: (def.format || '').includes('png'),
    version: '1.1.1',
    attribution: '&copy; NASA Global Imagery Browse Services (GIBS)',
    opacity: Number($('layerOpacity')?.value || 78) / 100,
    uppercase: true
  };
  if (selectedDate) {
    // Monthly composites are indexed by month; normalize the date to the first day.
    options.time = def.period === 'Monthly' ? `${selectedDate.slice(0,7)}-01` : selectedDate;
  }
  return L.tileLayer.wms('https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi', options);
}
function activateSatelliteLayer(id, selectedDate='') {
  const def = getSatelliteDef(id);
  if (!def || !map) return;
  if (activeSatelliteLayer) map.removeLayer(activeSatelliteLayer);
  activeSatelliteLayerId = id;
  satelliteTileErrorShown = false;
  activeSatelliteLayer = createGibsLayer(def, selectedDate);
  activeSatelliteLayer.on('tileerror', () => {
    if (!satelliteTileErrorShown) {
      satelliteTileErrorShown = true;
      setSatelliteStatus('No tile returned for this layer/date. Try Latest available or choose another date.', 'warning');
    }
  });
  activeSatelliteLayer.on('load', () => {
    satelliteTileErrorShown = false;
    const dateText = selectedDate ? ` · ${def.period === 'Monthly' ? selectedDate.slice(0,7) : selectedDate}` : ' · latest available service date';
    setSatelliteStatus(`${def.provider} visualisation loaded${dateText}.`, 'success');
  });
  activeSatelliteLayer.addTo(map);
  renderSatelliteMetadata(def);
  const selector = $('satelliteLayerSelect');
  if (selector) selector.value = id;
}
async function loadSatelliteCatalog() {
  try {
    const result = await api('/earth-observation/catalog');
    if (result.layers?.length) satelliteCatalog = result.layers;
    else satelliteCatalog = SATELLITE_FALLBACK_CATALOG;
    setSatelliteStatus('NASA GIBS layer catalogue loaded. Choose a layer to explore.', 'success');
  } catch (_) {
    satelliteCatalog = SATELLITE_FALLBACK_CATALOG;
    setSatelliteStatus('Using the built-in public NASA GIBS layer catalogue. Backend catalogue is offline.', 'warning');
  }
  const select = $('satelliteLayerSelect');
  if (select) {
    const current = select.value || 'modis_terra_truecolor';
    select.innerHTML = satelliteCatalog.map(x => `<option value="${escapeHTML(x.id)}">${escapeHTML(x.title)}</option>`).join('');
    select.value = satelliteCatalog.some(x=>x.id===current) ? current : 'modis_terra_truecolor';
  }
  renderSatelliteMetadata(getSatelliteDef(select?.value || 'modis_terra_truecolor'));
  if (map) activateSatelliteLayer(select?.value || 'modis_terra_truecolor', $('satelliteDate')?.value || '');
}
function bindSatelliteControls() {
  if (satelliteControlsBound) return;
  satelliteControlsBound = true;
  $('satelliteLayerSelect').addEventListener('change', () => {
    activateSatelliteLayer($('satelliteLayerSelect').value, $('satelliteDate').value);
  });
  document.querySelectorAll('[data-satellite-layer]').forEach(button => button.addEventListener('click', () => {
    const selected = button.dataset.satelliteLayer;
    const date = $('satelliteDate').value;
    if (map) activateSatelliteLayer(selected, date);
    else { activeSatelliteLayerId = selected; renderSatelliteMetadata(getSatelliteDef(selected)); setSatelliteStatus('Layer selected. Reconnect to load the interactive map tiles.', 'warning'); }
  }));
  $('mapZoomToField').addEventListener('click', () => {
    if (!map) return;
    const boundary = farmPolygon || demoPolygon;
    if (boundary) map.fitBounds(boundary.getBounds(), {padding:[42,42], maxZoom:14});
    else map.setView([21.39575,79.32575], 11);
  });
  $('expandSatelliteMap').addEventListener('click', () => {
    const expanded = $('satelliteMainPanel').classList.toggle('map-expanded');
    $('expandSatelliteMap').innerHTML = expanded ? '⤢ <span>Collapse</span>' : '⤢ <span>Expand</span>';
    setTimeout(() => map && map.invalidateSize(), 180);
  });
  $('applySatelliteDate').addEventListener('click', () => {
    const chosen = $('satelliteDate').value;
    if (!chosen) { toast('Choose an observation date first.'); return; }
    activateSatelliteLayer($('satelliteLayerSelect').value, chosen);
  });
  $('latestSatelliteDate').addEventListener('click', () => {
    $('satelliteDate').value = '';
    activateSatelliteLayer($('satelliteLayerSelect').value, '');
  });
  $('layerOpacity').addEventListener('input', e => {
    $('layerOpacityValue').textContent = `${e.target.value}%`;
    if (activeSatelliteLayer) activeSatelliteLayer.setOpacity(Number(e.target.value)/100);
  });
  $('boundaryToggle').addEventListener('change', e => {
    const layer = farmPolygon || demoPolygon;
    if (!layer || !map) return;
    if (e.target.checked) layer.addTo(map); else map.removeLayer(layer);
  });
  $('searchSentinelBtn').addEventListener('click', searchSentinelScenes);
  $('loadPowerContext').addEventListener('click', loadPowerContext);
  $('loadSatelliteMetrics')?.addEventListener('click', loadSatelliteMetrics);
  $('boundaryFarmSelect')?.addEventListener('change', () => focusFarmBoundary(selectedBoundaryFarm()));
}

function selectedBoundaryFarm() {
  const id=$('boundaryFarmSelect')?.value;
  return farmCache.find(f=>f.farm_id===id) || null;
}
function populateBoundaryFarmSelect() {
  const select=$('boundaryFarmSelect'); if(!select)return;
  const selected=select.value;
  select.innerHTML=farmCache.map(f=>`<option value="${escapeHTML(f.farm_id)}">${escapeHTML(f.name)}</option>`).join('') || '<option value="">No saved farms</option>';
  select.value=farmCache.some(f=>f.farm_id===selected)?selected:(farmCache[0]?.farm_id||'');
  const farm=selectedBoundaryFarm();
  $('boundaryFarmNote').textContent=farm?.geometry_geojson?'Saved farmer-drawn boundary · estimated area':farm?'No boundary saved for this farm yet':'Illustrative centre · not a verified farm boundary';
}
function focusFarmBoundary(farm) {
  if(!map)return;
  if(farmPolygon){map.removeLayer(farmPolygon);farmPolygon=null;}
  if(farm?.geometry_geojson?.type==='Polygon'){
    if(demoPolygon)map.removeLayer(demoPolygon);
    const latlngs=farm.geometry_geojson.coordinates[0].map(([lon,lat])=>[lat,lon]);
    farmPolygon=L.polygon(latlngs,{color:'#2d8050',weight:2.5,fillColor:'#8fc69b',fillOpacity:.25}).addTo(map);
    farmPolygon.bindTooltip('Farmer-drawn boundary · estimated area');
    map.fitBounds(farmPolygon.getBounds(),{padding:[25,25]});
  } else {
    if(demoPolygon)demoPolygon.addTo(map);
    if(farm)map.setView([farm.latitude,farm.longitude],13);
    else map.setView([21.39575,79.32575],11);
  }
}

async function loadSatelliteMetrics() {
  const target = $('satelliteMetricsResults');
  if (!target) return;
  const center = map ? map.getCenter() : L.latLng(21.39575,79.32575);
  target.innerHTML = '<div class="empty-inline">Requesting NASA catalog and available public observations...</div>';
  try {
    const data = await api(`/api/satellites/sync-all?latitude=${center.lat}&longitude=${center.lng}`);
    target.innerHTML = `<p class="micro-note">${data.datasets_live_numeric} live numeric · ${data.datasets_catalog_only} live catalog only · ${data.datasets_simulated} simulated fallback. Synthetic metrics are never observations.</p><div class="satellite-metric-list">${data.datasets.map(item=>`<article class="sentinel-scene"><div><strong>${escapeHTML(item.dataset_name)}</strong><small>${escapeHTML(item.platform)} · ${escapeHTML(item.observation_time||'date unavailable')}</small></div><span class="soft-pill">${escapeHTML(item.source_status.replaceAll('_',' '))}</span><small>${escapeHTML(item.quality?.flag||'provider status')}</small><pre>${escapeHTML(JSON.stringify(item.metrics,null,2))}</pre>${item.simulation?'<b class="warning-pill">Synthetic fallback · not an observation</b>':''}</article>`).join('')}</div>`;
  } catch (e) {
    target.innerHTML = `<div class="empty-inline">NASA data hub could not be reached: ${escapeHTML(e.message)}. Retry while the backend is running.</div>`;
  }
}
function initMap() {
  bindSatelliteControls();
  if (map) { map.invalidateSize(); return; }
  if (!window.L) { toast('Map library could not load. Check your connection.'); setSatelliteStatus('Leaflet could not load. Check the internet connection.', 'warning'); return; }
  const fallback = $('satMapFallback');
  if (fallback) fallback.hidden = true;
  map = L.map('farmMap', {zoomControl: false, preferCanvas: true}).setView([21.39575, 79.32575], 11);
  L.control.zoom({position:'bottomright'}).addTo(map);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'}).addTo(map);
  demoPolygon = L.polygon([[21.401,79.315],[21.404,79.329],[21.394,79.337],[21.389,79.321]], {color:'#4e8e66',weight:2,fillColor:'#9bc7a4',fillOpacity:.18,dashArray:'5 4'}).addTo(map);
  demoPolygon.bindTooltip('Illustrative demo boundary — not surveyed land');
  const savedGeometry = selectedBoundaryFarm()?.geometry_geojson;
  if (savedGeometry) {
    if (demoPolygon) map.removeLayer(demoPolygon);
    const latlngs = savedGeometry.coordinates[0].map(([lon,lat])=>[lat,lon]);
    farmPolygon = L.polygon(latlngs,{color:'#2d8050',weight:2.5,fillColor:'#8fc69b',fillOpacity:.25}).addTo(map);
    farmPolygon.bindTooltip('Farmer-drawn boundary · estimated area');
    map.fitBounds(farmPolygon.getBounds(),{padding:[25,25]});
  }
  map.on('click', (e) => {
    if (!drawMode) return;
    drawPoints.push([e.latlng.lat, e.latlng.lng]);
    const marker = L.circleMarker(e.latlng, {radius:5,color:'#245b3d',fillColor:'#e6f1e7',fillOpacity:1,weight:2}).addTo(map);
    drawMarkers.push(marker);
    $('drawStatus').textContent = `${drawPoints.length} boundary points added. Add at least 3 points, then save.`;
    $('saveBoundaryBtn').disabled = drawPoints.length < 3;
  });
  activateSatelliteLayer(activeSatelliteLayerId || 'modis_terra_truecolor', '');
  loadSatelliteCatalog();
}
function closeRing(points) {
  const coords = points.map(([lat, lon]) => [lon, lat]);
  if (coords.length && (coords[0][0] !== coords.at(-1)[0] || coords[0][1] !== coords.at(-1)[1])) coords.push(coords[0]);
  return coords;
}
function getCurrentParcelGeometry() {
  if (drawPoints.length >= 3) return {type:'Polygon', coordinates:[closeRing(drawPoints)]};
  const saved = parcelCache.find(p => p.geojson?.type === 'Polygon' || p.geojson?.type === 'MultiPolygon');
  if (saved) return saved.geojson;
  return {type:'Polygon', coordinates:[[[79.315,21.401],[79.329,21.404],[79.337,21.394],[79.321,21.389],[79.315,21.401]]]};
}
function formatDateTime(value) {
  if (!value) return 'Date unavailable';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}
async function searchSentinelScenes() {
  const status = $('sentinelSearchStatus');
  const results = $('sentinelSceneResults');
  const start = $('sentinelStartDate').value;
  const end = $('sentinelEndDate').value;
  if (!start || !end || start > end) { status.textContent = 'Choose a valid start and end date.'; return; }
  status.textContent = 'Searching the Copernicus STAC catalogue…';
  results.innerHTML = '';
  try {
    const data = await api('/earth-observation/sentinel-2/search', {method:'POST', body:JSON.stringify({geometry:getCurrentParcelGeometry(),start_date:start,end_date:end,max_cloud_cover:Number($('sentinelCloudLimit').value),limit:15})});
    status.textContent = `${data.count} scene(s) found. Metadata search only; imagery bands are not downloaded or analysed yet.`;
    if (!data.scenes?.length) { results.innerHTML = '<div class="empty-inline">No scenes matched these dates and cloud filter. Widen the date range or cloud threshold.</div>'; return; }
    results.innerHTML = data.scenes.map(scene => `<article class="sentinel-scene"><div><strong>${escapeHTML(scene.id)}</strong><small>${escapeHTML(formatDateTime(scene.datetime))} · ${escapeHTML(scene.platform || 'Sentinel-2')}</small></div><span class="scene-cloud">${scene.cloud_cover == null ? 'Cloud N/A' : `${Number(scene.cloud_cover).toFixed(1)}% cloud`}</span><small class="scene-collection">Collection: ${escapeHTML(scene.collection || 'sentinel-2-l2a')} · Assets: ${escapeHTML((scene.asset_keys || []).join(', ') || 'metadata only')}</small>${scene.item_url ? `<a href="${escapeHTML(scene.item_url)}" target="_blank" rel="noopener">Open STAC item ↗</a>` : ''}</article>`).join('');
  } catch (e) {
    status.textContent = `Catalogue search unavailable: ${e.message}. Start the FastAPI backend and try again.`;
  }
}
async function loadPowerContext() {
  const target = $('powerContextResults');
  target.innerHTML = '<div class="empty-inline">Requesting NASA POWER daily data…</div>';
  const center = map ? map.getCenter() : L.latLng(21.39575,79.32575);
  const days = Number($('powerDays').value || 30);
  try {
    const data = await api(`/nasa/power?lat=${center.lat}&lon=${center.lng}&days=${days}`);
    const parameters = data.parameters || {};
    const series = (key) => Object.values(parameters[key] || {}).map(Number).filter(v => Number.isFinite(v) && v > -900);
    const rain = series('PRECTOTCORR');
    const temp = series('T2M');
    const maxTemp = series('T2M_MAX');
    const totalRain = rain.length ? rain.reduce((a,b)=>a+b,0) : null;
    const meanTemp = temp.length ? temp.reduce((a,b)=>a+b,0)/temp.length : null;
    const peakTemp = maxTemp.length ? Math.max(...maxTemp) : null;
    const fmt = v => v == null ? '—' : `${v.toFixed(1)}`;
    target.innerHTML = `<div class="power-stats"><article><small>Rain total*</small><strong>${fmt(totalRain)} <em>mm</em></strong></article><article><small>Mean air temp.</small><strong>${fmt(meanTemp)} <em>°C</em></strong></article><article><small>Highest daily max</small><strong>${fmt(peakTemp)} <em>°C</em></strong></article></div><div class="eo-power-foot">${escapeHTML(data.requested_period?.start || '')} to ${escapeHTML(data.requested_period?.end || '')} · ${rain.length} daily values for precipitation · NASA POWER grid context.</div><p class="eo-data-caution">*Sum of available daily PRECTOTCORR values returned for this point request. It is gridded data, not a local rain-gauge total or forecast.</p>`;
  } catch (e) {
    target.innerHTML = `<div class="empty-inline">${escapeHTML(e.message)}. Run the FastAPI backend to request NASA POWER data.</div>`;
  }
}
function toLocalISODate(value) {
  const d = new Date(value);
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0,10);
}
function initialiseSatelliteDates() {
  const end = new Date();
  // Keep a small latency buffer for optical scene availability.
  end.setDate(end.getDate() - 2);
  const start = new Date(end);
  start.setDate(start.getDate() - 90);
  if ($('sentinelEndDate') && !$('sentinelEndDate').value) $('sentinelEndDate').value = toLocalISODate(end);
  if ($('sentinelStartDate') && !$('sentinelStartDate').value) $('sentinelStartDate').value = toLocalISODate(start);
}
initialiseSatelliteDates();

$('drawBoundaryBtn').addEventListener('click', () => {
  initMap();
  drawMode = !drawMode;
  if (drawMode) {
    drawPoints = []; drawMarkers.forEach(m => map.removeLayer(m)); drawMarkers = [];
    $('drawBoundaryBtn').textContent = '✓ Finish drawing';
    $('drawStatus').textContent = 'Tap or click at least 3 points around your field boundary. This is an estimate.';
    map.getContainer().style.cursor = 'crosshair';
  } else {
    map.getContainer().style.cursor = '';
    $('drawBoundaryBtn').textContent = '＋ Draw field';
    $('drawStatus').textContent = drawPoints.length >= 3 ? `${drawPoints.length} points ready to save.` : 'Drawing cancelled or incomplete.';
    $('saveBoundaryBtn').disabled = drawPoints.length < 3;
  }
});
$('saveBoundaryBtn').addEventListener('click', async () => {
  if (drawPoints.length < 3) return;
  try {
    if (!farmCache.length) await createFarm('My first farm');
    const coords = drawPoints.map(([lat,lon]) => [lon,lat]);
    coords.push(coords[0]);
    const geometry = {type:'Polygon',coordinates:[coords]};
    const areaHectares = polygonAreaHectares(coords);
    const vertices = coords.slice(0,-1);
    const centerLat = vertices.reduce((sum,p)=>sum+p[1],0)/vertices.length;
    const centerLon = vertices.reduce((sum,p)=>sum+p[0],0)/vertices.length;
    const farm = selectedBoundaryFarm() || farmCache[0];
    const updated = await api(`/farms/${encodeURIComponent(farm.farm_id)}`, {method:'PATCH', body:JSON.stringify({geometry_geojson:geometry,area_value:areaHectares,area_unit:'hectare',latitude:centerLat,longitude:centerLon})});
    const farmIndex=farmCache.findIndex(item=>item.farm_id===updated.farm_id);
    if(farmIndex>=0)farmCache[farmIndex]=updated;
    populateBoundaryFarmSelect();
    parcelCache = [{farm_id:updated.farm_id,geojson:geometry,area_hectares:areaHectares,geometry_quality:'farmer-drawn estimate'}];
    toast(`Boundary saved to the backend · estimated ${areaHectares.toFixed(2)} ha.`);
    drawMode = false; map.getContainer().style.cursor='';
    $('drawBoundaryBtn').textContent='＋ Draw field'; $('saveBoundaryBtn').disabled=true;
    drawMarkers.forEach(m => map.removeLayer(m)); drawMarkers=[];
    if (farmPolygon) map.removeLayer(farmPolygon);
    if (demoPolygon) map.removeLayer(demoPolygon);
    farmPolygon = L.polygon(drawPoints, {color:'#2d8050',weight:2.5,fillColor:'#8fc69b',fillOpacity:.25}).addTo(map);
    farmPolygon.bindTooltip('Farmer-drawn parcel · estimated boundary');
    map.fitBounds(farmPolygon.getBounds(), {padding:[25,25]});
    $('drawStatus').textContent = 'Saved as a farmer-drawn estimated boundary.';
    await loadFarms();
  } catch (e) { toast(e.message); }
});
$('resetBoundaryBtn').addEventListener('click', () => {
  if (farmPolygon && map) map.removeLayer(farmPolygon);
  farmPolygon = null; drawPoints=[]; drawMarkers.forEach(m => map && map.removeLayer(m)); drawMarkers=[];
  if (demoPolygon && map && $('boundaryToggle').checked) demoPolygon.addTo(map);
  $('drawStatus').textContent='Map boundary reset. Saved parcel records are not deleted.';
  $('saveBoundaryBtn').disabled=true;
});

async function createFarm(name) {
  const center = map ? map.getCenter() : {lat:21.39575,lng:79.32575};
  const farm = await api('/farms', {method:'POST', body:JSON.stringify({name, latitude:center.lat, longitude:center.lng, crop_history:[], soil_fields:{}, priorities:[]})});
  farmCache.unshift(farm);
  return farm;
}
async function loadFarms() {
  try {
    const data = await api('/farms');
    farmCache = Array.isArray(data) ? data : [];
    populateBoundaryFarmSelect();
    parcelCache = farmCache.filter(f=>f.geometry_geojson).map(f=>({farm_id:f.farm_id,geojson:f.geometry_geojson,area_hectares:f.area_unit==='hectare'?f.area_value:null}));
    $('parcelCount').textContent = parcelCache.length;
    $('farmCounter').textContent = `${farmCache.length} farm${farmCache.length===1?'':'s'}`;
    $('farmList').innerHTML = farmCache.length ? farmCache.map(f => {
      const n = parcelCache.filter(p=>p.farm_id===f.farm_id).length;
      return `<div class="farm-row"><span class="farm-icon">▦</span><div><strong>${escapeHTML(f.name)}</strong><small>${escapeHTML(f.region)} · ${n} parcel${n===1?'':'s'}</small></div><span class="soft-pill">ACTIVE</span></div>`;
    }).join('') : '<div class="empty-inline">No farms yet. Create your first farm.</div>';
  } catch (e) {
    farmCache = []; parcelCache = [];
    $('parcelCount').textContent = '0'; $('farmCounter').textContent = 'API unavailable';
    $('farmList').innerHTML = `<div class="empty-inline">Could not load saved farms: ${escapeHTML(e.message)}. Reconnect to the backend and retry.</div>`;
  }
}

function polygonAreaHectares(ring) {
  const radius = 6378137;
  const lat0 = ring.reduce((sum,p)=>sum+p[1],0)/ring.length*Math.PI/180;
  const points = ring.map(([lon,lat])=>[radius*lon*Math.PI/180*Math.cos(lat0),radius*lat*Math.PI/180]);
  let twice=0;
  for(let i=0;i<points.length-1;i++) twice += points[i][0]*points[i+1][1]-points[i+1][0]*points[i][1];
  return Math.abs(twice/2)/10000;
}
$('createFarmBtn').addEventListener('click', async () => {
  const name = prompt('Name this farm');
  if (!name || !name.trim()) return;
  try { await createFarm(name.trim()); await loadFarms(); toast('Farm created.'); } catch(e) { toast(e.message); }
});

function escapeHTML(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }

['waterPriority','soilPriority','incomePriority'].forEach(id => {
  const el = $(id);
  if (!el) return;
  el.addEventListener('input', e => $(id+'Value').textContent = `${e.target.value} / 5`);
});

function rotationPayload() {
  const pH = $('soilPH').value.trim();
  const oc = $('organicCarbon').value.trim();
  return {
    current_crop: $('currentCrop').value,
    previous_crop: $('previousCrop').value,
    district: $('districtInput').value.trim() || 'Ramtek, Nagpur, Maharashtra',
    irrigation: $('irrigationInput').value,
    soil_type: $('soilType').value,
    rainfall_scenario: $('rainfallScenario').value,
    post_monsoon_moisture: $('moistureInput').value,
    plan_year: Number($('planYear').value),
    field_area_ha: $('fieldArea').value ? Number($('fieldArea').value) : null,
    water_priority: Number($('waterPriority').value),
    soil_priority: Number($('soilPriority').value),
    income_priority: Number($('incomePriority').value),
    soil_ph: pH ? Number(pH) : null,
    organic_carbon: oc ? Number(oc) : null,
    measured_soil_report: $('verifiedSoil').checked
  };
}

const ROTATION_CROPS = {
  'soybean': {family:'legume', season:'Kharif', water:2, duration:'medium'},
  'green gram': {family:'legume', season:'Kharif', water:1, duration:'short'},
  'black gram': {family:'legume', season:'Kharif', water:1, duration:'short'},
  'pigeon pea': {family:'legume', season:'Kharif', water:2, duration:'long'},
  'cotton': {family:'malvaceae', season:'Kharif', water:3, duration:'long'},
  'sorghum': {family:'cereal', season:'Kharif', water:1, duration:'medium'},
  'pearl millet': {family:'cereal', season:'Kharif', water:1, duration:'short'},
  'chickpea': {family:'legume', season:'Rabi', water:1, duration:'short'},
  'safflower': {family:'oilseed', season:'Rabi', water:1, duration:'medium'},
  'rabi sorghum': {family:'cereal', season:'Rabi', water:2, duration:'medium'}
};
const esc = escapeHTML;
function cropName(s) { return String(s||'').replace(/\b\w/g, x=>x.toUpperCase()); }
function localCompatibility(previous, next, payload={}) {
  const a=ROTATION_CROPS[previous], b=ROTATION_CROPS[next];
  if(!a||!b) return {status:'Needs local review',tone:'amber',score:50,reasons:['One crop is outside the prototype crop catalogue.']};
  const reasons=[]; let status='Potentially diversified', tone='green', score=82;
  if(previous===next){status='Repeat crop warning';tone='amber';score=36;reasons.push('The same crop would repeat. Check pest, disease and nutrient history before considering it.');}
  else if(a.family===b.family){status='Same-family caution';tone='amber';score=54;reasons.push(`Both crops are in the ${a.family} family. This may reduce family diversity; review crop-specific pest and disease history.`);}
  else {reasons.push(`The crop families differ (${a.family} → ${b.family}), which may improve sequence diversity.`);}
  if(a.duration==='long' && b.season==='Rabi') {score-=15;tone='amber';status='Check harvest timing';reasons.push('The previous crop may occupy the field for a long duration. Confirm the actual harvest date and remaining Rabi sowing window.');}
  if(b.season==='Rabi') {
    if(payload.rainfall_scenario==='excess') {score-=12;tone='amber';status='Check drainage and field condition';reasons.push('An excess-rain scenario needs field checks for waterlogging, drainage, erosion and access before considering a follow-up crop.');}
    else if(payload.rainfall_scenario==='deficit'||payload.rainfall_scenario==='delayed'||payload.post_monsoon_moisture==='low') {score-=22;tone='amber';status='Rabi moisture caution';reasons.push('Low or delayed moisture scenario: do not assume a second crop. Verify stored soil water and local advisories.');}
    else if(payload.irrigation==='rainfed' && payload.post_monsoon_moisture!=='adequate') {score-=12;tone='amber';status='Conditional Rabi option';reasons.push('Rainfed Rabi cropping depends on measured/observed residual moisture. The app cannot infer it from the selected scenario.');}
    else {reasons.push('Rabi option remains conditional on sowing window, stored moisture, variety and local recommendation.');}
  }
  score=Math.max(10,Math.min(95,score));
  reasons.push('This is a sequence-screening heuristic, not proof of agronomic compatibility.');
  return {status,tone,score,reasons};
}
function localRotationResult(p) {
  const current=ROTATION_CROPS[p.current_crop]||ROTATION_CROPS.soybean;
  const lastFamily=ROTATION_CROPS[p.current_crop]?.family||'unknown';
  let sets;
  if(p.rainfall_scenario==='deficit'||p.rainfall_scenario==='delayed') {
    sets=[
      {title:'Water-conscious pathway',crops:['sorghum','green gram','pearl millet'],desc:'Keeps the Kharif options comparatively short-duration or lower-water in this demonstration; verify the district contingency plan before choosing.'},
      {title:'Soil-diversity pathway',crops:['pearl millet','soybean','sorghum'],desc:'Alternates cereal and legume families across the Kharif planning slots; Rabi crop slots are not automatically filled in a dry scenario.'},
      {title:'Farmer-observation pathway',crops:['sorghum','black gram','green gram'],desc:'A conservative comparison set. Crop choice still depends on rainfall onset, seed availability, soil depth and local advice.'}
    ];
  } else {
    const first = lastFamily==='legume' ? 'sorghum' : 'soybean';
    const second = first==='sorghum' ? 'green gram' : 'sorghum';
    const third = first==='sorghum' ? 'pearl millet' : 'green gram';
    sets=[
      {title:'Balanced family-diversity pathway',crops:[first,second,third],desc:'Illustrates cereal–legume family alternation while keeping each Rabi crop conditional on residual moisture.'},
      {title:'Short-duration option pathway',crops:['green gram','sorghum','soybean'],desc:'Compares shorter-duration Kharif options with a cereal break; sequence and sowing windows require local review.'},
      {title:'Rainfed sequence evidence pathway',crops:['sorghum','green gram','soybean'],desc:'Builds on local sequence examples including sorghum–chickpea/safflower and green gram–safflower pairs; the full three-year combination is a prototype composition.'}
    ];
  }
  const plans=sets.map((set,idx)=>{
    let familySet=new Set(set.crops.map(c=>ROTATION_CROPS[c].family));
    const years=set.crops.map((crop,i)=>{
      let rabi='No Rabi crop assumed';
      let rabiReason='Keep the option open until field moisture, harvest timing and the local sowing window are confirmed.';
      let rabiType='conditional';
      const dry=p.rainfall_scenario==='deficit'||p.rainfall_scenario==='delayed'||p.post_monsoon_moisture==='low';
      const excess=p.rainfall_scenario==='excess';
      const rabiAllowed=!dry && !excess && (p.irrigation!=='rainfed'||p.post_monsoon_moisture==='adequate');
      if(dry){rabi='Rest / moisture conservation';rabiReason='The selected delayed/deficit or low-moisture scenario does not auto-fill a second crop. Review ICAR-CRIDA contingency guidance and field conditions.';}
      else if(excess){rabi='Drainage / waterlogging check first';rabiReason='An excess-rain scenario is not a crop recommendation. Check field drainage, waterlogging, erosion, soil trafficability and the actual sowing window before considering another crop.';}
      else if(rabiAllowed && crop==='soybean'){rabi='Chickpea or Rabi sorghum';rabiReason='PDKV Akola describes soybean–chickpea / Rabi sorghum under available profile moisture or limited irrigation; check local sowing timing.';}
      else if(rabiAllowed && crop==='green gram'){rabi='Safflower (conditional)';rabiReason='PDKV dryland material lists green gram–safflower; use only where soil, rainfall timing and local advice fit.';}
      else if(rabiAllowed && crop==='sorghum'){rabi='Chickpea or safflower';rabiReason='Published dryland sequence examples include sorghum–chickpea / safflower in suitable rainfed soil-moisture situations.';}
      else if(!dry && p.irrigation==='reliable'){rabi='Review chickpea / safflower options';rabiReason='Reliable irrigation does not make a crop automatically suitable; check soil, variety, disease history and market.';}
      else {rabi='No second crop assumed';rabiReason='Residual moisture is unknown. Do not infer it from satellite pixels or the rainfall scenario selector.';}
      if(p.current_crop==='pigeon pea' && i===0){rabi='Harvest-date check first';rabiReason='Pigeon pea may be long duration; confirm harvest timing before considering any follow-up crop.';}
      return {year:p.plan_year+i,kharif:cropName(crop),kharif_key:crop,rabi,rabi_reason:rabiReason,rabi_type:rabiType,
        kharif_reason:i===0?`Compared with the most recent crop (${cropName(p.current_crop)}), this is a candidate next Kharif crop. Confirm crop history, variety and local sowing window.${sameHistory?` Recent history shows ${cropName(p.previous_crop)} and ${cropName(p.current_crop)} in the same broad family; review pest and disease history.`:''}`:`This is a possible next-year crop-family change in the scenario, not a field prescription.`};
    });
    let waterAverage=set.crops.reduce((n,c)=>n+ROTATION_CROPS[c].water,0)/set.crops.length;
    let waterFit=p.irrigation==='rainfed'?Math.max(0,1-(waterAverage-1)/3):p.irrigation==='limited'?Math.max(0,1-(waterAverage-1.5)/3):0.8;
    let diversity=familySet.size/3;
    let rainfallFit=p.rainfall_scenario==='deficit'||p.rainfall_scenario==='delayed'?(waterAverage<=1.5?0.9:0.45):p.rainfall_scenario==='excess'?0.4:p.rainfall_scenario==='unknown'?0.5:0.72;
    const waterWeight=.30+.10*((Number(p.water_priority||5)-1)/4);
    const diversityWeight=.30+.10*((Number(p.soil_priority||5)-1)/4);
    const rainfallWeight=.30;
    const weightTotal=waterWeight+diversityWeight+rainfallWeight;
    const weights={water_demand:waterWeight/weightTotal,crop_family_diversity:diversityWeight/weightTotal,rainfall_scenario:rainfallWeight/weightTotal};
    const components={water_demand_fit:Math.round(waterFit*100),crop_family_diversity:Math.round(diversity*100),rainfall_scenario_fit:Math.round(rainfallFit*100),soil_suitability:null};
    let score=Math.round(100*(weights.water_demand*waterFit+weights.crop_family_diversity*diversity+weights.rainfall_scenario*rainfallFit));
    if(idx===2) score=Math.max(35,score-4);
    const sameHistory=ROTATION_CROPS[p.previous_crop]?.family===ROTATION_CROPS[p.current_crop]?.family;
    const historyNote=sameHistory?`Recent history shows ${cropName(p.previous_crop)} followed by ${cropName(p.current_crop)}, both in the same broad family. Review the field's pest and disease history.`:null;
    const reasons=[`${familySet.size} crop families represented across the three planned Kharif slots.`,`Water-demand tier average: ${waterAverage.toFixed(1)} (rough catalogue tier, not litres or irrigation requirement).`,p.soil_type==='unknown'?'Soil class is unknown; soil context is incomplete.':`Soil class entered: ${p.soil_type.replace('_',' ')}. It is shown as context but not scored as crop suitability.`,`Your water priority (${p.water_priority}/5) adjusts the water-demand weight; soil-diversity priority (${p.soil_priority}/5) adjusts the crop-family-diversity weight.`,`Soil pH, organic carbon and nutrients are not used as crop-suitability thresholds in this prototype.`,p.income_priority>=4?'Income stability is a high priority, but verified local price, cost and yield data are not connected.':'Income priority is recorded but not scored because verified local price/cost/yield data are not connected.'];
    if(historyNote) reasons.push(historyNote);
    if(p.rainfall_scenario==='excess') reasons.push('Excess rainfall is a drainage/waterlogging caution, not automatically favourable crop water.');
    return {title:set.title,description:set.desc,illustrative_fit_score:score,score_label:'Illustrative comparison fit',score_components:components,score_weights:{water_demand:Math.round(weights.water_demand*100),crop_family_diversity:Math.round(weights.crop_family_diversity*100),rainfall_scenario:Math.round(weights.rainfall_scenario*100)},years,reasons};
  });
  plans.sort((a,b)=>b.illustrative_fit_score-a.illustrative_fit_score);
  const warnings=[
    'Three-year calendars are prototype scenarios composed from published local crop-pair examples; the complete three-year pathways have not been field-validated.',
    'A Rabi crop is conditional on harvest timing, soil moisture, soil depth, sowing window, variety, irrigation and current local advisories.',
    'For excess rain, check drainage, waterlogging, erosion and field access before considering another crop; the planner does not prescribe an automatic switch.',
    'A selected rainfall scenario is a what-if assumption, not a NASA/IMD forecast. Open Weather to inspect the dated data separately.',
    p.measured_soil_report?'Soil values are marked as copied from a report; check the original report, units and sample date.':'No verified soil report is marked. Soil nutrient suitability is not scored.',
    'NASA satellite observations add environmental context; exact soil pH, NPK and micronutrients must come from laboratory or verified Soil Health Card measurements.'
  ];
  return {engine:'KRISHIQ rotation planner prototype v0.3.0',region:p.district,profile:p,plans,decision_status:'Exploratory 3-year scenarios — not a planting prescription',evidence_and_limits:warnings,
    sources:[{name:'PDKV Akola · AICRP Integrated Farming Systems',url:'https://www.pdkv.ac.in/?page_id=4678',note:'Soybean–chickpea / Rabi sorghum under available profile moisture or limited irrigation.'},{name:'PDKV Akola · AICRP Dryland Agriculture',url:'https://www.pdkv.ac.in/?page_id=4490',note:'Green gram–safflower, sorghum–chickpea and soybean–chickpea examples under specified contexts.'},{name:'ICAR-CRIDA District Contingency Plans',url:'https://www.icar-crida.res.in/Crop_Contingency_Plan.html',note:'District and rainfall-stage specific contingency guidance.'}],
    score_note:'Illustrative fit compares catalogue water-demand tier, crop-family diversity and the selected rainfall what-if. Your priorities adjust weights. Soil class is context only and is not scored as suitability. This is not confidence, yield, profitability or agronomic validation.'};
}
function renderRotationPlan(data) {
  $('scenarioState').textContent=`${data.plans.length} pathways`;
  const profile=data.profile||{};
  $('rotationPlanResults').innerHTML=`<div class="results-warning"><strong>${esc(data.decision_status)}</strong><br>${esc(data.score_note||'Illustrative comparison only.')}</div>
    <div class="rotation-profile-strip"><span><b>Region</b>${esc(data.region||'Ramtek')}</span><span><b>Most recent crop</b>${esc(cropName(profile.current_crop||'soybean'))}</span><span><b>Rainfall case</b>${esc(profile.rainfall_scenario||'not set')}</span><span><b>Water</b>${esc(profile.irrigation||'not set')}</span></div>
    <div class="rotation-plan-list">${data.plans.map((plan,i)=>`<article class="rotation-plan-card ${i===0?'rotation-plan-best':''}"><div class="rotation-plan-card-head"><div><span class="rotation-plan-kicker">PATHWAY ${i+1}</span><h3>${esc(plan.title)}</h3><p>${esc(plan.description)}</p></div><div class="rotation-fit"><strong>${plan.illustrative_fit_score}</strong><small>illustrative fit / 100</small></div></div><div class="rotation-year-grid">${plan.years.map(y=>`<div class="rotation-year-card"><div class="rotation-year-head">${y.year}</div><div class="rotation-season-slot"><span>KHARIF</span><strong>${esc(y.kharif)}</strong><small>${esc(y.kharif_reason)}</small></div><div class="rotation-season-slot rabi-slot"><span>RABI · CONDITIONAL</span><strong>${esc(y.rabi)}</strong><small>${esc(y.rabi_reason)}</small></div></div>`).join('')}</div><div class="rotation-reasons"><strong>Score components</strong><div class="rotation-score-components">${Object.entries(plan.score_components||{}).filter(([k,v])=>v!==null).map(([k,v])=>`<span><b>${esc(k.replaceAll('_',' '))}</b><em>${v}/100</em></span>`).join('')}</div><small class="score-weight-note">Weights: ${Object.entries(plan.score_weights||{}).map(([k,v])=>`${esc(k.replaceAll('_',' '))} ${v}%`).join(' · ')}</small><strong>Why this pathway scored this way</strong><ul>${plan.reasons.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div><button class="secondary-btn save-plan-btn" data-plan-index="${i}">Save this as my draft plan</button></article>`).join('')}</div>
    <div class="rotation-limit-list"><strong>Evidence and checks before acting</strong><ul>${(data.evidence_and_limits||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>
    <div class="rotation-source-links">${(data.sources||[]).map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener"><strong>${esc(s.name)}</strong><small>${esc(s.note)}</small><span>Open source ↗</span></a>`).join('')}</div>`;
  $('rotationPlanResults').querySelectorAll('.save-plan-btn').forEach(btn=>btn.addEventListener('click',()=>{
    const chosen=data.plans[Number(btn.dataset.planIndex)];
    localStorage.setItem('kisanx-selected-rotation-plan',JSON.stringify({saved_at:new Date().toISOString(),region:data.region,plan:chosen}));
    toast('Draft plan saved on this device. It is not a planting instruction.');
  }));
  localStorage.setItem(DEMO_STORAGE,JSON.stringify(data));
}
async function runRotationPlan() {
  const payload=rotationPayload();
  $('scenarioState').textContent='Comparing…';
  $('rotationPlanResults').innerHTML='<div class="empty-state"><div class="empty-illustration">⟳</div><h3>Building your three-year view</h3><p>Comparing crop families, broad water-demand tiers, soil context and conditional Rabi options.</p></div>';
  try {
    const data=localRotationResult(payload); data.mode='frontend demonstration';
    renderRotationPlan(data);
    toast(data.mode==='frontend demonstration'?'Frontend demo plan generated.':'Rotation scenarios generated.');
  } catch(e) { $('scenarioState').textContent='Error'; $('rotationPlanResults').innerHTML=`<div class="empty-inline">${esc(e.message)}</div>`; }
}
$('runRotationBtn').addEventListener('click',runRotationPlan);
$('tryRotationExample').addEventListener('click',()=>{
  $('currentCrop').value='soybean';$('previousCrop').value='cotton';$('soilType').value='medium_black';$('irrigationInput').value='rainfed';$('rainfallScenario').value='normal';$('moistureInput').value='adequate';$('soilPriority').value=5;$('waterPriority').value=5;
  $('soilPriorityValue').textContent='5 / 5';$('waterPriorityValue').textContent='5 / 5';runRotationPlan();
});

function setRotationTab(name) {
  document.querySelectorAll('[data-rotation-tab]').forEach(btn=>{const on=btn.dataset.rotationTab===name;btn.classList.toggle('active',on);btn.setAttribute('aria-selected',String(on));});
  document.querySelectorAll('.rotation-tab-pane').forEach(pane=>{const on=pane.id===`rotationPane-${name}`;pane.hidden=!on;pane.classList.toggle('active',on);});
  if(name==='diary') loadRotationDiary();
}
document.querySelectorAll('[data-rotation-tab]').forEach(btn=>btn.addEventListener('click',()=>setRotationTab(btn.dataset.rotationTab)));
$('checkCompatibilityBtn').addEventListener('click',async()=>{
  const previous=$('compatPrevious').value,next=$('compatNext').value,payload=rotationPayload();
  const result=localCompatibility(previous,next,payload);
  $('compatibilityResult').innerHTML=`<div class="compatibility-result-head ${esc(result.tone||'amber')}"><strong>${esc(result.status)}</strong><span>${esc(result.score)} / 100 · screening score</span></div><ul>${result.reasons.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`;
});

function readDiaryLocal(){try{return JSON.parse(localStorage.getItem(DIARY_STORAGE)||'[]');}catch(_){return [];}}
function renderRotationDiary(entries){
  $('rotationDiaryList').innerHTML=entries.length?entries.map(e=>`<article class="diary-entry"><div><strong>${esc(e.crop)} · ${esc(e.season_label)}</strong><small>${esc(e.created_at||'Saved on this device')}</small></div><div class="diary-values"><span>Cost: ${e.cost_inr==null?'—':'₹'+Number(e.cost_inr).toLocaleString('en-IN')}</span><span>Harvest: ${e.harvest_quantity_kg==null?'—':Number(e.harvest_quantity_kg).toLocaleString('en-IN')+' kg'}</span><span>Net before unlisted costs: ${e.net_before_unlisted_costs_inr==null?'—':'₹'+Number(e.net_before_unlisted_costs_inr).toLocaleString('en-IN')}</span></div><p>${esc(e.note||'No note recorded')}</p></article>`).join(''):'<div class="empty-inline">No farm outcomes recorded yet. Add an actual season result above.</div>';
}
async function loadRotationDiary(){
  renderRotationDiary(readDiaryLocal());
}
$('saveRotationDiaryBtn').addEventListener('click',async()=>{
  const cost=$('diaryCost').value,qty=$('diaryHarvest').value,price=$('diaryPrice').value;
  const payload={season_label:$('diarySeason').value.trim()||'Season not specified',crop:$('diaryCrop').value,cost_inr:cost===''?null:Number(cost),harvest_quantity_kg:qty===''?null:Number(qty),sale_price_per_kg:price===''?null:Number(price),note:$('diaryNote').value.trim()};
  if(!payload.season_label||[payload.cost_inr,payload.harvest_quantity_kg,payload.sale_price_per_kg].some(v=>v!==null&&(!Number.isFinite(v)||v<0))){$('diaryFeedback').textContent='Please check your season and numeric entries.';return;}
  const gross=payload.harvest_quantity_kg!==null&&payload.sale_price_per_kg!==null?payload.harvest_quantity_kg*payload.sale_price_per_kg:null;
  const entry={...payload,id:crypto.randomUUID?crypto.randomUUID():String(Date.now()),created_at:new Date().toLocaleString(),gross_revenue_inr:gross,net_before_unlisted_costs_inr:gross!==null&&payload.cost_inr!==null?gross-payload.cost_inr:null};
  const all=readDiaryLocal();all.unshift(entry);localStorage.setItem(DIARY_STORAGE,JSON.stringify(all));
  $('diaryFeedback').textContent='Outcome recorded. Financial values use the figures you entered and may exclude other costs.';
  $('diaryNote').value='';$('diaryCost').value='';$('diaryHarvest').value='';$('diaryPrice').value='';
  loadRotationDiary();toast('Farm outcome saved.');
});
$('refreshWeatherBtn').addEventListener('click', refreshWeather);
async function refreshWeather() {
  $('weatherFeedback').textContent='Fetching daily NASA POWER data…';
  $('weatherTable').textContent='Loading…';
  try {
    const farm=selectedBoundaryFarm()||farmCache[0];
    const center=map?.getCenter();
    const latitude=farm?.latitude ?? center?.lat ?? 21.39575;
    const longitude=farm?.longitude ?? center?.lng ?? 79.32575;
    const data = await api(`/nasa/power?lat=${latitude}&lon=${longitude}&days=30`);
    lastWeather = data;
    const keys = Object.keys(data.parameters?.T2M || {}).slice(-7);
    const rain = data.parameters?.PRECTOTCORR || {};
    const t = data.parameters?.T2M || {};
    const rh = data.parameters?.RH2M || {};
    $('weatherPeriod').textContent=`${data.requested_period.start} – ${data.requested_period.end}`;
    $('weatherFeedback').textContent='NASA POWER returned a daily regional series. Units and timestamps are retained from the response.';
    $('weatherTable').innerHTML = keys.length ? `<table class="weather-table"><thead><tr><th>Date</th><th>Avg. temp</th><th>Rainfall</th><th>Humidity</th></tr></thead><tbody>${keys.reverse().map(k=>`<tr><td>${k.slice(0,4)}-${k.slice(4,6)}-${k.slice(6,8)}</td><td>${formatValue(t[k])}</td><td>${formatValue(rain[k])}</td><td>${formatValue(rh[k])}</td></tr>`).join('')}</tbody></table><p class="micro-note">${escapeHTML(data.provenance)}</p><a class="source-link" href="${escapeHTML(data.source_url)}" target="_blank" rel="noopener">Open source response ↗</a>` : '<div class="empty-inline">NASA POWER response contained no daily values in this range.</div>';
    toast('NASA POWER data loaded.');
  } catch(e) { $('weatherFeedback').textContent=e.message; $('weatherTable').textContent='No data returned. Try again later or inspect the NASA POWER API status.'; }
}
function formatValue(v) { return v === undefined || v === null || v === -999 ? '—' : Number(v).toFixed(1); }

$('saveSoilBtn').addEventListener('click', async () => {
  if (!farmCache.length) { toast('Create a farm before saving measured soil values.'); goto('farms'); return; }
  const values = {pH:$('soilInputPH').value || null, EC:$('soilEC').value || null, organic_carbon_percent:$('soilOC').value || null, N:$('soilN').value || null, P:$('soilP').value || null, K:$('soilK').value || null, sample_date:$('soilDate').value || null, source:$('soilSource').value.trim() || 'Farmer-entered report'};
  if (![values.pH,values.EC,values.organic_carbon_percent,values.N,values.P,values.K].some(Boolean)) { toast('Enter at least one measured value from a report.'); return; }
  try {
    const farm=selectedBoundaryFarm()||farmCache[0];
    const updated=await api(`/farms/${encodeURIComponent(farm.farm_id)}`,{method:'PATCH',body:JSON.stringify({soil_fields:{...(farm.soil_fields||{}),...values}})});
    const farmIndex=farmCache.findIndex(item=>item.farm_id===updated.farm_id);
    if(farmIndex>=0)farmCache[farmIndex]=updated;
    $('soilFeedback').textContent='Measured values and their source were saved to this farm record.';
    toast('Soil record saved to the backend.'); loadSoilHistory();
  } catch(e) { $('soilFeedback').textContent=e.message; }
});
async function loadSoilHistory() {
  const farm=selectedBoundaryFarm()||farmCache[0];
  const values=farm?.soil_fields||{};
  const measured=Object.entries(values).filter(([key,value])=>!['sample_date','source'].includes(key)&&value!==null&&value!=='');
  $('soilHistory').innerHTML=measured.length?`<div class="farm-row"><span class="farm-icon">♧</span><div><strong>${escapeHTML(values.source||'Farmer-entered report')}</strong><small>${escapeHTML(values.sample_date||'Sample date not recorded')} · ${escapeHTML(measured.map(([k,v])=>`${k}: ${v}`).join(', '))}</small></div><span class="soft-pill">FARM RECORD</span></div>`:'No measured soil values have been saved for the selected farm.';
}

const RND = [
 ['16','AGRICAUSE','Investigate why a parcel zone may be changing. Combine satellite time series, weather, soil tests and farmer observations into competing hypotheses.','Prototype: evidence graph and abstention; expert-labelled cases required.'],
 ['17','FIELDTWIN','Compare plausible farm what-if scenarios using parcel-specific inputs and calibrated crop models.','Prototype: one-crop scenario; prediction intervals and back-testing required.'],
 ['18','PLOT-LAB','Record expert-approved comparisons and learn from repeated field observations.','Prototype: approved templates only; simple comparisons do not prove causation.'],
 ['19','PEST-SIGNAL MESH','Share coarse, consented and verified regional crop-risk signals without exposing exact farms.','Prototype: human verification, duplicate filtering and privacy review required.'],
 ['20','HARVEST WINDOW','Plan a likely readiness window with field confirmation, weather and storage context.','Prototype: validate one crop locally; market prices are not guaranteed farm-gate prices.'],
 ['21','BIOCYCLE','Estimate potential residue resources and connect them to verified local uses.','Prototype: compare estimates against weighed samples; suitability is crop-specific.']
];
function loadResearchFeatures(){
  $('researchCards').innerHTML=RND.map(x=>`<article class="research-card"><span class="research-id">FEATURE ${x[0]} · ORIGINAL KISAN-X R&D</span><h3>${x[1]}</h3><p>${x[2]}</p><span class="research-status">RESEARCH PROTOTYPE</span><p>${x[3]}</p></article>`).join('');
}

async function loadProviderStatuses() {
  $('providerList').innerHTML='<div class="provider-slot"><div class="provider-ident"><span class="provider-dot">NASA</span><div><strong>NASA POWER daily point</strong><small class="muted">Public API · no key configured or required</small></div></div><div class="provider-actions"><span class="soft-pill">Connected through backend</span></div><p class="micro-note">Daily gridded climate context is requested server-side. It is not a farm sensor or forecast.</p></div><div class="provider-slot"><div class="provider-ident"><span class="provider-dot">GIBS</span><div><strong>NASA Earth imagery</strong><small class="muted">Public map tiles · no token</small></div></div><div class="provider-actions"><span class="soft-pill">Public access</span></div><p class="micro-note">Browse visualisations only. The app does not calculate parcel-level satellite indices.</p></div><div class="micro-note">Optional AI provider credentials are not configured in this release. KrishiQ uses its transparent built-in knowledge mode.</div>';
}
// Activity log remains in this page session only in this starter. Production should sync through authenticated APIs.
let activities=[];
$('saveActivityBtn').addEventListener('click',()=>{
  const note=$('activityNote').value.trim();
  activities.unshift({type:$('activityType').value,date:$('activityDate').value||new Date().toISOString().slice(0,10),note});
  $('activityList').innerHTML=activities.map(a=>`<div class="farm-row"><span class="farm-icon">▤</span><div><strong>${escapeHTML(a.type)}</strong><small>${escapeHTML(a.date)} · ${escapeHTML(a.note||'No additional note')}</small></div></div>`).join('');
  $('activityNote').value='';toast('Activity recorded in this demo session.');
});
$('addActivityBtn').addEventListener('click',()=>goto('calendar'));
$('cropPhoto').addEventListener('change',e=>{
  const file=e.target.files?.[0];
  if(!file)return;
  $('photoFeedback').textContent=`Selected ${file.name} (${Math.round(file.size/1024)} KB). This prototype has not analysed the image.`;
});

function openKrishiQ(){ $('krishiqPanel').hidden=false; $('chatInput').focus(); }
$('krishiqLauncher').addEventListener('click',()=>openKrishiQ());
$('closeKrishiq').addEventListener('click',()=>{$('krishiqPanel').hidden=true;});
document.querySelectorAll('[data-prompt]').forEach(b=>b.addEventListener('click',()=>{openKrishiQ();$('chatInput').value=b.dataset.prompt;sendChat();}));
$('speakToggle').addEventListener('click',()=>{speechOn=!speechOn;$('speakToggle').textContent=`Voice: ${speechOn?'on':'off'}`;});
function addChat(text,role,evidence=[]){
  const bubble=document.createElement('div');
  bubble.className=`chat-bubble ${role==='user'?'user-bubble':'assistant-bubble'}`;
  bubble.textContent=text;
  if(evidence.length){const div=document.createElement('div');div.className='chat-evidence';div.textContent='Evidence context: '+evidence.map(x=>x.source).join(' · ');bubble.appendChild(div);}
  $('chatMessages').appendChild(bubble);$('chatMessages').scrollTop=$('chatMessages').scrollHeight;
}
function speak(text){
  if(!speechOn||!('speechSynthesis' in window))return;
  window.speechSynthesis.cancel();
  const utter=new SpeechSynthesisUtterance(text.slice(0,950));
  utter.lang=voiceLanguage;
  window.speechSynthesis.speak(utter);
}
async function sendChat(){
  const input=$('chatInput');const message=input.value.trim();if(!message)return;
  input.value='';addChat(message,'user');$('voiceStatus').textContent='Local knowledge mode';
  const q=message.toLowerCase();
  const say=(answer)=>{addChat(answer,'assistant');speak(answer);};
  const hasAny=(words)=>words.some(word=>q.includes(word));
  if(hasAny(['poison','poisoning','swallowed chemical','difficulty breathing','not breathing','unconscious','severe allergic'])){
    const answer='This may be an emergency. Contact local emergency services or a qualified medical/veterinary professional now. Move people and animals away from exposure if it is safe to do so, and keep the product container or label available. I cannot assess or treat an emergency.';
    say(answer);return;
  }
  if(hasAny(['pesticide','insecticide','fungicide','herbicide','spray dose','chemical dose','mix chemicals','pesticide dose'])){
    const answer='I can’t safely name a pesticide, dose, or mixture from this chat. First confirm the crop and variety, district, crop stage, affected area and pattern, and the pest or symptom evidence. Check the current Indian registration and exact crop-pest product label with the local KVK/State Agriculture University or qualified adviser before any chemical use. Don’t mix products based on a guess.';
    say(answer);return;
  }
  if(hasAny(['cow','buffalo','goat','sheep','chicken','poultry','livestock','animal medicine','veterinary']) && hasAny(['sick','medicine','not eating','fever','diarrhea','diarrhoea','treatment','dose','symptom'])){
    const answer='Please contact a veterinarian, especially if the animal is weak, has fever, breathing trouble, bloating, diarrhoea, is pregnant, or changed suddenly. I can help organise the history, but I can’t diagnose or prescribe medicine. Note the species, age, how long this has been happening, feed/water changes, and other signs.';
    say(answer);return;
  }
  if(hasAny(['diagnose','diagnosis','what disease','what pest','why are my leaves','yellow leaves','leaf spots','plant disease','crop disease'])){
    const answer='Symptoms are clues, not a confirmed diagnosis. Please share the crop and variety, district, sowing date and growth stage, when the problem began, whether it is uniform or patchy, recent rain/irrigation and inputs, plus clear whole-plant and close-up photos. Until the cause is clearer, avoid applying extra fertilizer or pesticide based only on appearance.';
    say(answer);return;
  }
  if(hasAny(['fertilizer dose','fertiliser dose','how much fertilizer','how much fertiliser','fertilizer quantity','fertiliser quantity'])){
    const answer='A safe fertilizer quantity needs the crop and variety, district, field area and unit, sowing date, crop stage, irrigation, and the soil-test recommendation. The exact product grade matters too. Share those details and verify the rate against the current local crop package; I won’t guess a dose.';
    say(answer);return;
  }
  if(hasAny(['will it rain','rain tomorrow','weather tomorrow','should i irrigate','irrigate tomorrow'])){
    goto('weather');
    const answer='I opened weather and climate context. This app currently shows historical NASA POWER data, not a live IMD forecast, so it cannot answer tomorrow’s rain or irrigation decision. Check the latest IMD/KVK advisory for your block and consider crop stage, recent rain, soil and water availability.';
    say(answer);return;
  }
  const routes=[['satellite',['map','satellite']],['rotation',['rotation','crop sequence']],['weather',['weather','rain','rainfall']],['soil',['soil','soil health']],['farms',['farm','field']]];
  const route=routes.find(([,words])=>words.some(w=>q.includes(w)));
  if(route){goto(route[0]);const reply=`Opening ${route[0]==='rotation'?'the crop rotation planner':route[0]==='satellite'?'the satellite map':route[0]==='soil'?'soil intelligence':route[0]==='weather'?'weather intelligence':'your farms'}. Navigation is handled on this device.`;addChat(reply,'assistant');speak(reply);return;}
  let answer='I can guide you to the map, crop rotation planner, measured soil records, weather screen, or farm list. KrishiQ is using built-in local guidance in this release, not a live AI model. For field advice, local crop, variety, district, season, stage, soil test and water context may change the answer.';
  if(q.includes('chickpea')||q.includes('soybean')||q.includes('sorghum')) answer='Crop sequence choice depends on crop history, soil type, harvest timing, sowing window and stored soil moisture. The planner shows prototype options and selected published examples; verify any decision with local KVK advice.';
  else if(q.includes('soil')) answer='Use measured Soil Health Card or laboratory values for pH, organic carbon and nutrients. Satellite images do not directly measure exact NPK or pH in your field.';
  else if(q.includes('satellite')||q.includes('smap')||q.includes('ndvi')) answer='The map layers are NASA browse visualisations at their stated scales. Open dataset status shows which responses are live numeric data, catalog metadata, or clearly marked synthetic fallback.';
  addChat(answer,'assistant');speak(answer);
}
$('chatForm').addEventListener('submit',e=>{e.preventDefault();sendChat();});
$('micBtn').addEventListener('click',()=>{
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){$('voiceStatus').textContent='Speech recognition is not supported in this browser. Try a recent Chrome-based browser.';toast('Speech input is not available in this browser.');return;}
  if(recognition){recognition.stop();recognition=null;$('micBtn').classList.remove('listening');$('voiceStatus').textContent='Microphone stopped';return;}
  recognition=new SR();recognition.lang=voiceLanguage;recognition.interimResults=true;recognition.continuous=false;
  recognition.onstart=()=>{$('micBtn').classList.add('listening');$('voiceStatus').textContent='Listening… speak now';};
  recognition.onresult=e=>{let transcript='';for(let i=e.resultIndex;i<e.results.length;i++)transcript+=e.results[i][0].transcript;$('chatInput').value=transcript;if(e.results[e.results.length-1].isFinal)sendChat();};
  recognition.onerror=e=>{$('voiceStatus').textContent=`Microphone: ${e.error}`;};
  recognition.onend=()=>{$('micBtn').classList.remove('listening');recognition=null;if($('voiceStatus').textContent==='Listening… speak now')$('voiceStatus').textContent='Tap the microphone to speak';};
  try{recognition.start();}catch(e){$('voiceStatus').textContent='Could not start microphone. Check browser permission.';}
});
$('languageSelect').addEventListener('change',e=>{
  voiceLanguage=e.target.value==='en'?'en-IN':e.target.value;
  const names={'hi-IN':'हिन्दी','mr-IN':'मराठी'};
  $('voiceStatus').textContent=`Speech language set to ${names[voiceLanguage]||e.target.options[e.target.selectedIndex].text}. Voice availability depends on the device.`;
});

document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openKrishiQ();}});

async function boot(){
  try{await loadFarms();}catch(e){}
if ($('sentinelEndDate')) { const end = new Date(); end.setDate(end.getDate()-5); $('sentinelEndDate').value = end.toISOString().slice(0,10); const start = new Date(end); start.setDate(start.getDate()-45); $('sentinelStartDate').value = start.toISOString().slice(0,10); }
  loadResearchFeatures();
  $('soilDate').value=new Date().toISOString().slice(0,10);
  $('activityDate').value=new Date().toISOString().slice(0,10);
  if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js').catch(()=>{});}
  try{const h=await api('/health');backendConnected=h.status==='ok';if(!backendConnected)toast('Backend status is not ready.');}catch(e){backendConnected=false;console.info('Running frontend demonstration mode; connect FastAPI for server-backed records and live integrations.');}
}
boot();
