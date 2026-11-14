# NASA data adapter and reference export

## Live farm-coordinate adapter

The API requests NASA POWER Daily Point data with `time-standard=UTC` for six parameters:

| Parameter | Meaning | Unit | Product and approximate grid |
|---|---|---|---|
| `T2M` | Mean air temperature at 2 m | °C | MERRA-2, 0.5° × 0.625° (~50 km) |
| `T2M_MAX` | Maximum air temperature at 2 m | °C | MERRA-2, 0.5° × 0.625° (~50 km) |
| `T2M_MIN` | Minimum air temperature at 2 m | °C | MERRA-2, 0.5° × 0.625° (~50 km) |
| `PRECTOTCORR` | Corrected total precipitation | mm/day | MERRA-2, 0.5° × 0.625° (~50 km) |
| `RH2M` | Relative humidity at 2 m | % | MERRA-2, 0.5° × 0.625° (~50 km) |
| `ALLSKY_SFC_SW_DWN` | All-sky surface shortwave downward irradiance | MJ/m²/day | CERES SYN1deg, 1° (~100 km) |

Resolution is parameter-specific. Values represent gridded environmental context, not farm-level measurements. Product metadata is retained per observation; provider-managed versions can change.

## Bundled Nagpur reference CSV

`backend/data/reference/nagpur_power_daily_2001_2025.csv` is the supplied NASA POWER point export. `reference_power.py` parses its metadata and rows, computes a SHA-256 digest, and checks coordinates, declared date range, daily continuity/uniqueness, sentinel/null counts, negative rainfall, and maximum/minimum temperature consistency. The source is a Nagpur city-centre proxy point, not a farm or polygon average.

The API exposes the source audit and daily values. Aggregations preserve units: daily precipitation is summed for totals; temperature, humidity, and radiation are averaged. Annual values are only emitted for complete calendar years. June–September dry-gap screens use the configured daily rainfall thresholds and count consecutive runs. Method details and caveats are returned with each summary.

## Validation status and missing values

The bundled series passes structural checks, but that does not establish accuracy. Local station data, a GPM IMERG export, and a farm polygon with a MODIS export are not bundled; the validation endpoint reports these as pending. The comparison endpoint accepts matched daily series once their units, date windows, accumulation windows, time standard, and quality flags are documented.

Provider sentinel/missing values stay null. Missing dates are reported separately. No null is imputed as zero. The live adapter retries upstream failures and returns an error rather than substitute data; its process cache is in-memory and expires according to `NASA_POWER_CACHE_TTL_SECONDS`.
