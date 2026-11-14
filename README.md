# KISAN-X + KrishiQ — Farmer-first field intelligence

A full-stack hackathon prototype with a FastAPI service and responsive web app. The backend provides farm records, NASA POWER context, an evidence-aware rotation API, reports, a 13-source Earth-data hub, and direct owner-verified UPI payments.

> **Release status:** built for demonstration and judging, not yet a validated production agronomy service. NASA browse layers are visual context, the rotation lab contains explicitly labeled local prototype logic, and the Crop Doctor does not diagnose images. Review [docs/FRONTEND_BACKEND_INTEGRATION.md](docs/FRONTEND_BACKEND_INTEGRATION.md) for exactly what is server-backed and what stays on the device.

The farmer-facing guidance follows the supplied India Agriculture Intelligence Handbook's intake and escalation principles. KrishiQ remains local scripted guidance, not a live AI provider or field diagnosis. See [docs/AGRICULTURE_ADVISORY_STANDARD.md](docs/AGRICULTURE_ADVISORY_STANDARD.md) for its exact safety boundaries.

## Current web app

- The v0.3.1 farmer-facing experience is served by the same FastAPI app at `/`.
- Farmer-drawn GeoJSON field boundaries and approximate area are saved on the farm record. The outline is an estimate, not a surveyed cadastral boundary.
- NASA GIBS provides interactive browse imagery from six distinct mission/platform sources: Terra, Aqua, GPM, SMAP, Landsat and Suomi-NPP VIIRS. NASA POWER provides daily gridded weather context; the satellite hub reports source status and provenance for 13 Earth-data adapters.
- Direct UPI payment claims and owner verification use the existing backend and do not use a payment gateway.
- Diary and activity entries are explicitly device-local. KrishiQ uses a built-in local knowledge mode. Optional AI provider credentials are not enabled.

## What is included

- FastAPI REST API with OpenAPI docs at `/docs`.
- Farm profile create, update, and read endpoints.
- NASA POWER daily point-data adapter for six climate variables, with retries and an in-process TTL cache.
- Bundled 2001–2025 Nagpur proxy series with structural audit, climate summaries, dry-gap screens, and exploratory trend screens.
- Paired-series climate comparison endpoint for aligned NASA, IMERG, or station inputs; unprovided sources remain pending.
- A normalized observation model that preserves source, variable, units, date, location, retrieval time, quality, and limitations.
- Crop-profile and rotation-rule catalogues loaded from JSON files.
- A rule engine that checks hard constraints before surfacing preference trade-offs. Numeric ranking is disabled unless the rulebook and request provide explicit weights.
- What-if simulations that preserve the baseline and identify changed assumptions.
- Stored comparison/simulation reports.
- Direct owner-configured UPI checkout and manual claim verification, without a payment gateway.
- PIN-protected owner payment/QR dashboard; farmer receipts remain private.
- Subscription tier, payment claim, and active subscription tables on the configured SQLAlchemy database.
- A responsive, installable web workspace at `/` that uses the same versioned API as a native mobile client.
- Farm-list and evidence-catalogue endpoints for client dashboards.
- An offline-cached app shell; data changes and live NASA requests still require a network connection.
- Unit/API tests, GitHub Actions CI, a Dockerfile, and VS Code launch/task settings.

## Quick start — VS Code

You need Python 3.11 or newer. Python 3.12 is a good default.

1. Open the project folder in VS Code.
2. Open **Terminal → New Terminal**.
3. Create and activate a virtual environment:

   **Windows PowerShell**
   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   **macOS / Linux**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. Install dependencies:
   ```bash
   python -m pip install --upgrade pip
   pip install -r backend/requirements.txt
   ```
5. Copy `.env.example` to `.env` in the project root if you want to change the safe defaults.
6. Start the API from the `backend` folder:
   ```bash
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
7. Open `http://127.0.0.1:8000/` for the responsive web app or `/docs` to try the API. A phone on the same Wi-Fi can open `http://<computer-lan-ip>:8000/`. For a full PWA install with offline shell support, deploy behind HTTPS and choose **Add to Home Screen**.

The default database is SQLite, so you do not need to install PostgreSQL to start developing. The database file is created at `backend/kisanx.db`. Payment models use the same SQLAlchemy engine and support the configured SQLite or PostgreSQL URL.

## Run tests

From the project root, with the virtual environment activated:

```bash
cd backend
pytest
```

The GitHub Actions workflow runs these tests on pushes and pull requests and checks the browser JavaScript syntax.

## Upload and run from GitHub

See [docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md) for repository upload commands, the Docker run option, deployment configuration, and the GitHub Pages limitation. GitHub Pages alone cannot run this FastAPI backend; host the full-stack app on a Python-capable service for the backend-connected features to work.

## Main API routes

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Service health |
| POST | `/api/v1/farms` | Create a farm profile |
| GET | `/api/v1/farms/{farm_id}` | Retrieve a farm profile and missing-input status |
| GET | `/api/v1/farms` | List farm profiles for app dashboards (`limit`, `offset`) |
| PATCH | `/api/v1/farms/{farm_id}` | Update supplied farm fields |
| GET | `/api/v1/farms/{farm_id}/observations` | Fetch NASA POWER daily observations for the farm |
| GET | `/api/v1/pay/public-config` | Show direct UPI settings and active subscription tiers |
| POST | `/api/v1/pay/submit-claim` | Submit a UPI reference and optional proof image |
| GET | `/api/v1/owner/dashboard` | PIN-protected payment management dashboard data |
| POST | `/api/v1/owner/verify-claim` | PIN-protected manual approval or rejection |
| GET | `/api/v1/farms/{farm_id}/climate/summary` | Audit and summarize live climate observations at a farm coordinate |
| GET | `/api/v1/climate/reference/nagpur/summary` | Summarize the bundled historical Nagpur proxy dataset |
| GET | `/api/v1/climate/reference/nagpur/daily` | Read a bounded date range of bundled daily observations |
| GET | `/api/v1/climate/reference/nagpur/validation` | Read structural checks and pending external validation sources |
| POST | `/api/v1/climate/compare` | Compare two pre-aligned daily climate series |
| POST | `/api/v1/rotations/compare` | Compare candidate crop sequences |
| POST | `/api/v1/simulations` | Compare baseline and hypothetical scenario |
| GET | `/api/v1/reports/{report_id}` | Retrieve a stored result |
| GET | `/api/v1/catalog` | Read reviewed crop profiles, source references, and catalogue status |
| GET | `/api/v1/earth-observation/catalog` | Read available NASA GIBS visualization layers |
| GET | `/api/v1/nasa/power?lat=…&lon=…&days=…` | Retrieve daily NASA POWER context for the map location |
| POST | `/api/v1/earth-observation/sentinel-2/search` | Discover Copernicus Sentinel-2 scene metadata for a drawn boundary |
| GET | `/api/satellites/sync-all?latitude=…&longitude=…` | Query the 13-source NASA/partner data hub with explicit live/catalog/simulation provenance |
| POST | `/api/satellites/query-feature` | Return sources mapped to crop rotation, soil health, or weather context |

All endpoints are versioned under `/api/v1`, matching the Member 4 handover contract. The exact schemas and example requests are in `docs/api-contract.md`.

## Important data/science behaviour

- Missing soil values remain `null`; the backend does not infer pH, texture, nutrient status, or measurements.
- NASA gridded data is environmental context, not a farm sensor reading. Each returned observation includes a product, source, units, dates, retrieval time, and limitations.
- NASA observations are not used as a substitute for local soil tests or Member 2's agronomy research.
- The crop catalogue and rotation-rule files start empty on purpose. Add Member 2's reviewed, source-linked profiles/rules before expecting agronomic eligibility decisions.
- With an empty or out-of-scope evidence catalogue, the engine returns `insufficient` / `uncertain` rather than making up crop advice.
- The included test catalogue is synthetic and exists only to test software behaviour. It is never loaded into the runtime catalogue.
- What-if outputs are stress-test comparisons under changed assumptions, not weather forecasts or yield/profit predictions.

## NASA POWER integration

The adapter calls the NASA POWER Daily Point API for `T2M`, `T2M_MAX`, `T2M_MIN`, `PRECTOTCORR`, `RH2M`, and `ALLSKY_SFC_SW_DWN`, explicitly requesting UTC. The first five are mapped to MERRA-2 and shortwave radiation to CERES SYN1deg, with parameter-specific resolution notes. Check current official NASA POWER metadata before farmer-facing use because provider products and versions can change. The bundled Nagpur series is a point proxy, not farm data; station, IMERG, and MODIS validation remain pending until those source exports are supplied.

Live calls require internet access. If the NASA service is unavailable, the API returns a clear upstream error; it does not silently replace missing observations with zeros or fabricated sample data.

## Database notes

- SQLite is the default for a quick local start.
- Set `DATABASE_URL` in `.env` to a PostgreSQL URL to use PostgreSQL.
- The initial farm model stores an optional parcel geometry as GeoJSON JSON for the API contract. It does **not** yet create a native PostGIS geometry column or perform spatial joins. Those belong in a later migration when the Team 1 parcel-boundary contract is ready.
- For a shared PostgreSQL environment, run migrations with `alembic upgrade head` from `backend/` and set `AUTO_CREATE_TABLES=false`.

## Repository safety

Never commit `.env`, API credentials, farmer personal information, databases with real records, payment receipt/QR uploads, or private farm coordinates. `.env.example` contains setting names and safe defaults only. The current prototype has no farmer accounts or per-farmer authorization; see [docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md) before making it publicly accessible.

## Suggested next handoffs

- **Member 1 → Member 4:** NASA product/parameter, version, field names, units, retrieval notes, sample response, quality flags, and missing-data behaviour.
- **Member 2 → Member 4:** machine-readable crop profiles, region/season scope, hard constraints, preference rules, evidence IDs, source register, confidence, and review caveats.
- **Member 4 → Member 3:** stable OpenAPI contract, example farm, observation, comparison, scenario, and report payloads.

The web workspace runs on the same origin as the API. Native Flutter or other mobile clients can call the versioned JSON routes directly; browser CORS is configured for the local development origins in `.env.example`. See `docs/integration-checklist.md` before wiring a native client.
