# Frontend and backend integration status

The v0.3.1 frontend is served by the existing FastAPI app. `backend/web/index.html`, `assets/app.js`, and `assets/app.css` are its shell; the existing SQLAlchemy API and UPI payment module remain the central backend.

## Server-backed features

- Farm create/list/update use `/api/v1/farms`. Farmer-drawn GeoJSON polygons and a projected area estimate are stored in the farm record. The polygon is not a surveyed boundary.
- Measured soil values are saved in the farm's `soil_fields` record with source/date notes. They are not satellite-derived.
- NASA POWER recent daily data is returned by `/api/v1/nasa/power`.
- GIBS layer metadata is served by `/api/v1/earth-observation/catalog`; the browser requests public NASA WMS browse imagery directly.
- The browse map exposes six distinct mission/platform sources: Terra, Aqua, GPM, SMAP, Landsat and Suomi-NPP VIIRS. Aqua true-colour and VIIRS thermal-anomaly layers are included; these remain imagery visualisations, not parcel-level extracted measurements.
- Copernicus Sentinel-2 scene search returns catalogue metadata only.
- Sentinel-2 boundary search rejects non-polygon geometry, unclosed or undersized rings, out-of-range/non-numeric coordinates and oversized boundaries before calling the external catalogue.
- The NASA dataset hub is mounted at `/api/satellites/sync-all` and `/api/satellites/query-feature`.
- Direct owner UPI payments continue to use `/api/v1/pay/*` and `/api/v1/owner/*`; owner operations require `X-Owner-Pin`.

## Device-local or research-only features

- The three-year rotation planner, pair checker, and crop outcome diary run in the browser and are explicitly described as prototype/demo logic. They are not persisted to the central backend or validated agronomic recommendations.
- The activity log is session-local. KrishiQ uses a built-in local knowledge mode and voice navigation; there is no external AI provider configured.
- KrishiQ applies handbook-informed safety triage in the browser. It does not provide a diagnosis, a pesticide recommendation, a fertilizer dose, veterinary treatment or a live forecast.
- Crop Doctor accepts a photo for inspection context but performs no image analysis or disease diagnosis.
- The Research Lab cards are proposals, not implemented product capabilities.
- A plan payment claim can be submitted, but no feature access is gated by subscription status.

## Satellite data interpretation

NASA GIBS layers are browse visualisations. NASA POWER, SMAP, GPM, and other gridded products are contextual signals at product-specific scales. The 13-source hub returns live numeric readings only for sources that expose public point values under this configuration; the rest provide catalog metadata and clearly labeled synthetic fallback metrics. Synthetic values have `simulation: true` and `decision_eligible: false` and must not drive farmer alerts or recommendations.

## Submission and production handoff

The app is suitable as a hackathon prototype. Before use with real farm decisions, populate and review the crop/rule catalogues, validate local data against ground observations, add authentication and farmer consent controls, define backup/retention practices, and deploy over HTTPS with production secrets and a database. Do not configure a real payment merchant or advertise unavailable services as live.
