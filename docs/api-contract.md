# KISAN-X Member 4 API contract

Base URL: `http://127.0.0.1:8000`  
OpenAPI: `/docs`  
Web/PWA: `/` (same JSON API is used by web and mobile clients)

All JSON requests use `Content-Type: application/json`. Dates use ISO `YYYY-MM-DD`.

## Farm profiles

- `POST /api/v1/farms` creates a profile with name, coordinates, region, season, area, crop history, irrigation, soil fields, priorities, and optional GeoJSON.
- `GET /api/v1/farms/{farm_id}`, `PATCH /api/v1/farms/{farm_id}`, and `GET /api/v1/farms?limit=50&offset=0` read, update, and list profiles.
- Unknown soil measurements should be `null`; omitted PATCH fields are retained.

## Live NASA POWER observations

`GET /api/v1/farms/{farm_id}/observations?start_date=2025-06-01&end_date=2025-06-07`

Returns normalized daily records for `T2M`, `T2M_MAX`, `T2M_MIN`, `PRECTOTCORR`, `RH2M`, and `ALLSKY_SFC_SW_DWN`. Each record includes source/product, raw parameter, unit, UTC date, coordinates, product resolution, retrieval time, and limitations. NASA POWER is a grid-cell estimate, not a farm sensor. Missing values remain `null`, never zero.

## Climate reference and analysis

- `GET /api/v1/climate/reference/nagpur/summary?start_date=2001-01-01&end_date=2025-12-31` returns structural audit, annual and monthly summaries, monsoon statistics, dry-gap screens, exploratory trend screens, validation status, and limitations. Omit dates for the full supplied period. Optional repeated `dry_gap_thresholds_mm_day` parameters override the defaults.
- `GET /api/v1/climate/reference/nagpur/daily?start_date=2025-06-01&end_date=2025-06-30` returns the inclusive daily rows; maximum 366 days and only within the bundled 2001–2025 period.
- `GET /api/v1/climate/reference/nagpur/validation` returns the CSV structural audit and explicit pending status for station, IMERG, and MODIS validation.
- `GET /api/v1/farms/{farm_id}/climate/summary?start_date=2025-06-01&end_date=2025-06-30` requests live NASA daily data for the saved coordinate and applies coverage/range checks before the same summary calculations.
- `POST /api/v1/climate/compare` computes paired-date bias, MAE, RMSE, Pearson and Spearman correlations, coverage, and optional wet-day occurrence counts for two pre-aligned series. Units and UTC/LST standards must match. Null or rejected quality values are excluded, not set to zero. A station input is labelled a comparison candidate, not automatic ground truth.

The bundled Nagpur series is a city-centre proxy. Trend intervals and p-values are exploratory and unadjusted. Cross-product checks are not independent validation; station validation requires actual station data and documented time alignment.

## Reviewed catalogue and rotations

- `GET /api/v1/catalog` returns catalogue version, reviewed crop profiles, source references, and rule counts. An empty catalogue is explicit.
- `POST /api/v1/rotations/compare` accepts a `farm_id`, candidate rotations, priorities, and optional `save_report`. Crop IDs must exist in the reviewed catalogue. The result provides eligibility/uncertainty, evidence and rule IDs, warnings, missing inputs, and limitations. No default numeric agronomic ranking is invented.

## What-if simulation

`POST /api/v1/simulations` accepts the same candidates plus scenario overrides such as `irrigation`, `rainfall_change_pct`, `sowing_delay_days`, `water_availability_change_pct`, `input_cost_change_pct`, and `sale_price_change_pct`.

The response includes baseline and scenario comparisons and records the hypothetical input changes. A change affects suitability only when a scope-matched, evidence-backed reviewed rule supports it. Input costs and sale prices are not turned into profit forecasts.

## Reports, errors

`GET /api/v1/reports/{report_id}` returns a stored request/result snapshot and rulebook version.

Errors use `{ "error": { "code", "message", "details", "request_id" } }`. Common codes include `not_found`, `validation_error`, and `http_error`; NASA upstream failures return 502. Invalid periods, incompatible comparison units/time standards, and requests outside the reference period return 422.

## Direct UPI payments

- `GET /api/v1/pay/public-config` returns active tiers and owner UPI/QR details.
- `GET /api/v1/pay/qr` serves only the public owner QR image.
- `POST /api/v1/pay/submit-claim` accepts multipart fields `farmer_name`, `farmer_phone`, `tier_code`, `utr_number`, and optional `screenshot`.
- `GET /api/v1/pay/status/{farmer_phone}` returns the subscription expiry and recent claim statuses. It does not return farmer names, UTRs, or proof files.
- `GET /api/v1/owner/dashboard`, `POST /api/v1/owner/verify-claim`, `GET /api/v1/owner/claims/{claim_id}/proof`, and `POST /api/v1/owner/update-settings` require the `X-Owner-Pin` header.

Payments go directly to the configured owner UPI ID. There is no payment gateway or automatic bank reconciliation; owners must confirm the payment in their own UPI/bank app before approving a claim. Uploads are capped at 5 MB and validated by image signature. QR files are exposed through the QR route; proof images are private and served only through the owner PIN route. The mobile number is a prototype identifier, not authenticated account access, and no paid feature gating is connected yet.
