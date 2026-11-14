# Decision engine method

## Processing order

1. Validate the farm and candidate request through Pydantic schemas.
2. Load crop profiles and the rule catalogue supplied by Member 2.
3. Check crop profile region and season scope.
4. Check required local soil fields. Unknown values remain unknown and generate warnings.
5. Apply applicable hard constraints and record the rule IDs and evidence IDs.
6. Collect preference trade-offs as explanations, not hidden assumptions.
7. Rank only when the rulebook explicitly enables scoring, preference rules include source-linked numeric scores and positive weights, and the request supplies positive factor weights.
8. Return uncertainty, missing inputs, assumptions, evidence references, catalogue version, and software version.

## Supported rule conditions

The JSON rule format is documented in `backend/data/crop_profiles/README.md`. Unsupported or incomplete hard-rule conditions are not treated as successful evidence; they create an uncertainty warning.

## Evidence status

- `sufficient`: all candidate options passed with loaded scoped profiles and evaluated constraints.
- `partial`: at least some evidence or rules were applied, but not all conditions are supported.
- `insufficient`: no meaningful crop/rule evidence was available.

An option may independently be `eligible`, `ineligible`, or `uncertain`.

## Why there is no default numeric ranking

The source handbooks require a disclosed comparison rubric and warn against invented scores. The catalogue starts empty. The service therefore gives a side-by-side evidence comparison until Member 2 provides reviewed evidence and weights. The implementation supports opt-in scoring for a completed rulebook; it does not invent default agronomic weights.

## Important boundaries

- Satellite NDVI/EVI or weather data is not a soil test.
- NASA environmental context is not a farm-level sensor reading.
- The backend does not promise yield, profit, disease diagnosis, or future weather.
- A what-if rainfall percentage is a user assumption, not a prediction.
- Sowing delay and water availability changes are hypothetical inputs; they affect option checks only when reviewed rules explicitly consume them.
- Input-cost and sale-price changes are recorded for scenario review, not converted into yield, revenue, or profit forecasts.
- A recommendation should be escalated or labelled insufficient when the region/season/evidence does not support it.

## Climate analysis boundaries

The bundled NASA POWER series is a Nagpur proxy point. Daily data is UTC; station comparisons must align daily accumulation windows first. Annual and seasonal trend screens are exploratory, nominal, and unadjusted for autocorrelation or multiple comparisons. Cross-product metrics describe agreement between supplied series and are not ground-truth validation. Station comparison requires real observations and documented station representativeness.
