# Member 4 integration checklist

## Before connecting the web workspace or Member 3's Flutter app

- [ ] Share the `/docs` OpenAPI URL and `docs/api-contract.md` with Member 3.
- [ ] The web workspace is served by the API at `/`; it uses the same `/api/v1` contract as native clients.
- [ ] Install the web app on a phone from the browser's **Add to Home Screen** action. Only its shell is cached offline; API actions require a connection.
- [ ] Agree whether the team's root API prefix will remain `/api/v1`.
- [ ] Agree stable JSON names and data types; do not rename fields informally.
- [ ] Confirm how the Flutter app stores and supplies `farm_id`.
- [ ] Confirm CORS requirements only for a separately hosted web client; native Flutter HTTP requests do not use browser CORS in the same way.
- [ ] Test loading, empty, timeout, validation, and upstream-error states.
- [ ] Keep the demo fixture visibly labelled as illustrative; do not represent it as live NASA data.

## Member 1 data handoff

- [ ] Source register with provider, product/version, exact parameter names and units.
- [ ] Official API endpoint and parameter-specific spatial/temporal resolution.
- [ ] Reproducible sample response for the chosen demo location and period.
- [ ] Missing-value/sentinel conventions, quality flags and latency notes.
- [ ] Aggregation method if any value is summarized across a longer period.

## Member 2 agronomy handoff

- [ ] Crop profiles scoped to the agreed region and season.
- [ ] Hard constraints separated from farmer preference trade-offs.
- [ ] Each rule has a stable ID, source ID, evidence statement, scope, confidence, and caveat.
- [ ] Soil fields are not inferred from satellite vegetation indices.
- [ ] Any numeric scoring rubric has reviewed weights and a documented method.
- [ ] Test cases include unsupported region/season and missing soil inputs.

## Demo acceptance

- [ ] Create/load a farm profile.
- [ ] Retrieve at least one real NASA data product for a historical period.
- [ ] Compare at least three candidate rotation options where the evidence supports them.
- [ ] Show reasons, trade-offs, missing inputs, source IDs, and limitations.
- [ ] Change one scenario assumption and show both baseline and scenario results.
- [ ] Retrieve the stored decision report.

## Climate and scenario endpoints

- [ ] Show the Nagpur reference summary and identify it as a proxy point, not farm data.
- [ ] Show daily reference data for a short UTC period and the structural audit.
- [ ] Show the pending station, IMERG, and MODIS validation states until source exports are supplied.
- [ ] Compare two pre-aligned series only after matching units and daily time standard; preserve nulls and quality flags.
- [ ] Show the live six-variable POWER summary for a saved coordinate with coverage and limitations.
- [ ] Treat trend results as exploratory; do not present them as forecasts or significance claims.
- [ ] Verify each scenario input is labelled hypothetical and that cost/price changes do not imply financial forecasts.
