from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.climate import (
    ClimateComparisonRequest,
    ClimateComparisonResponse,
    ClimateSource,
    ClimateSummary,
    ClimateAudit,
    ClimateDay,
    ReferenceClimateDailyResponse,
)
from app.services.climate_analysis import DEFAULT_DRY_GAP_THRESHOLDS, summarize_reference
from app.services.climate_validation import compare_climate_series
from app.services.farm_service import get_farm_or_404
from app.services.nasa_power import NASADataError
from app.services.observation_service import get_farm_observations
from app.services.reference_power import (
    DEFAULT_END,
    DEFAULT_START,
    REFERENCE_CSV,
    VARIABLES,
    ReferencePowerDataError,
    ReferencePowerDataset,
    get_reference_power,
)

router = APIRouter(tags=["climate analysis and validation"])

REFERENCE_LIMITATIONS = [
    "Nagpur is a city-centre proxy point, not a farm measurement.",
    "Daily dates are UTC. Align accumulation windows before comparing against local-day station data.",
    "Rainfall and dry-gap summaries are historical screens, not forecasts or crop-stress diagnoses.",
]


def _reference_dataset():
    try:
        return get_reference_power()
    except ReferencePowerDataError as exc:
        raise HTTPException(status_code=503, detail="The bundled NASA POWER reference data could not be loaded.") from exc


@router.get("/climate/reference/nagpur/summary", response_model=ClimateSummary)
def nagpur_reference_summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    dry_gap_thresholds_mm_day: list[float] | None = Query(default=None, min_length=1, max_length=10),
):
    """Summarize the supplied 2001-2025 Nagpur proxy export; never label it as farm data."""
    dataset = _reference_dataset()
    try:
        return summarize_reference(
            dataset,
            start_date,
            end_date,
            tuple(dry_gap_thresholds_mm_day) if dry_gap_thresholds_mm_day is not None else DEFAULT_DRY_GAP_THRESHOLDS,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/climate/reference/nagpur/daily", response_model=ReferenceClimateDailyResponse)
def nagpur_reference_daily(
    start_date: date = Query(...),
    end_date: date = Query(...),
):
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date")
    if (end_date - start_date).days > 365:
        raise HTTPException(status_code=422, detail="The daily response is limited to 366 days.")
    dataset = _reference_dataset()
    if start_date < dataset.source.period_start or end_date > dataset.source.period_end:
        raise HTTPException(status_code=422, detail="Requested dates fall outside the reference dataset period.")
    return ReferenceClimateDailyResponse(
        source=dataset.source,
        audit=dataset.audit,
        period_start=start_date,
        period_end=end_date,
        observations=[day for day in dataset.days if start_date <= day.observed_at <= end_date],
        limitations=REFERENCE_LIMITATIONS,
    )


@router.get("/climate/reference/nagpur/validation")
def nagpur_reference_validation():
    dataset = _reference_dataset()
    return {
        "source": dataset.source,
        "audit": dataset.audit,
        "validation_status": {
            "structural_audit": dataset.audit.status.upper(),
            "power_vs_local_station": "PENDING_STATION_DATA",
            "power_vs_gpm_imerg": "PENDING_IMERG_EXPORT",
            "modis_vegetation_export": "PENDING_FARM_POLYGON_AND_EXPORT",
        },
        "limitations": REFERENCE_LIMITATIONS,
        "raw_file": REFERENCE_CSV.name,
    }


@router.get("/farms/{farm_id}/climate/summary", response_model=ClimateSummary)
async def farm_coordinate_climate_summary(
    farm_id: str,
    start_date: date = Query(..., description="UTC start date (YYYY-MM-DD)"),
    end_date: date = Query(default_factory=date.today, description="UTC end date (YYYY-MM-DD)"),
    dry_gap_thresholds_mm_day: list[float] | None = Query(default=None, min_length=1, max_length=10),
    db: Session = Depends(get_db),
):
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date")
    farm = get_farm_or_404(db, farm_id)
    try:
        observation_response = await get_farm_observations(farm, start_date, end_date)
    except NASADataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    by_date: dict[date, dict[str, float | None]] = defaultdict(dict)
    null_counts = {variable: 0 for variable in VARIABLES}
    for record in observation_response.observations:
        if record.raw_parameter in VARIABLES:
            by_date[record.observed_at][record.raw_parameter] = record.value
            if record.value is None:
                null_counts[record.raw_parameter] += 1
    days = [ClimateDay(
        observed_at=day,
        values={variable: values.get(variable) for variable in VARIABLES},
        quality_flags={variable: "missing" if values.get(variable) is None else "provider_value_returned" for variable in VARIABLES},
    ) for day, values in sorted(by_date.items())]
    expected_dates = {start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1)}
    actual_dates = {day.observed_at for day in days}
    missing_dates = sorted(expected_dates - actual_dates)
    variables_present = {record.raw_parameter for record in observation_response.observations}
    rainfall_values = [day.values["PRECTOTCORR"] for day in days if day.values["PRECTOTCORR"] is not None]
    inverted_temperature_days = sum(
        1 for day in days
        if day.values["T2M_MAX"] is not None and day.values["T2M_MIN"] is not None
        and day.values["T2M_MAX"] < day.values["T2M_MIN"]
    )
    checks = {
        "all_expected_parameters_returned": set(VARIABLES).issubset(variables_present),
        "daily_date_coverage_complete": not missing_dates,
        "unique_daily_dates": len(actual_dates) == len(days),
        "precipitation_is_nonnegative": all(value >= 0 for value in rainfall_values),
        "daily_maximum_not_below_minimum": inverted_temperature_days == 0,
    }
    value_ranges = {}
    for variable, unit in (
        ("T2M", "°C"),
        ("T2M_MAX", "°C"),
        ("T2M_MIN", "°C"),
        ("PRECTOTCORR", "mm/day"),
        ("RH2M", "%"),
        ("ALLSKY_SFC_SW_DWN", "MJ/m²/day"),
    ):
        values = [day.values[variable] for day in days if day.values[variable] is not None]
        value_ranges[variable] = {
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None,
            "mean": sum(values) / len(values) if values else None,
            "unit": unit,
        }
    audit = ClimateAudit(
        status="passed" if all(checks.values()) else "failed",
        expected_daily_rows=len(expected_dates),
        actual_daily_rows=len(days),
        unique_dates=len(actual_dates),
        duplicate_dates=[],
        missing_dates=missing_dates,
        unexpected_dates=sorted(actual_dates - expected_dates),
        null_counts=null_counts,
        sentinel_counts={variable: 0 for variable in VARIABLES},
        range_violations={
            "negative_precipitation": sum(1 for value in rainfall_values if value < 0),
            "maximum_below_minimum": inverted_temperature_days,
        },
        value_ranges=value_ranges,
        first_date=min(actual_dates) if actual_dates else None,
        last_date=max(actual_dates) if actual_dates else None,
        checks=checks,
    )
    source = ClimateSource(
        source_id="NASA-POWER-LIVE-FARM-COORDINATE",
        label="NASA POWER grid cell at saved farm coordinate (not an on-farm sensor)",
        provider="NASA POWER",
        source_product={"meteorology": "MERRA-2", "solar": "CERES SYN1deg"},
        latitude=farm.latitude,
        longitude=farm.longitude,
        period_start=start_date,
        period_end=end_date,
        time_standard="UTC",
        spatial_resolution={
            "MERRA-2": "0.5° × 0.625° (~50 km; meteorological variables)",
            "CERES SYN1deg": "1° (~100 km; surface shortwave radiation)",
        },
        variables={
            "T2M": {"name": "Mean air temperature at 2 m", "unit": "°C", "source_product": "MERRA-2"},
            "T2M_MAX": {"name": "Maximum air temperature at 2 m", "unit": "°C", "source_product": "MERRA-2"},
            "T2M_MIN": {"name": "Minimum air temperature at 2 m", "unit": "°C", "source_product": "MERRA-2"},
            "PRECTOTCORR": {"name": "Corrected total precipitation", "unit": "mm/day", "source_product": "MERRA-2"},
            "RH2M": {"name": "Relative humidity at 2 m", "unit": "%", "source_product": "MERRA-2"},
            "ALLSKY_SFC_SW_DWN": {"name": "All-sky surface shortwave downward irradiance", "unit": "MJ/m²/day", "source_product": "CERES SYN1deg"},
        },
        retrieved_at=next((record.retrieved_at for record in observation_response.observations), None),
        raw_file_sha256=None,
    )
    dataset = ReferencePowerDataset(source=source, audit=audit, days=days)
    try:
        summary = summarize_reference(
            dataset,
            start_date,
            end_date,
            tuple(dry_gap_thresholds_mm_day) if dry_gap_thresholds_mm_day is not None else DEFAULT_DRY_GAP_THRESHOLDS,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    summary.validation_status = {
        "live_provider_response": "STRUCTURAL_CHECKS_PASSED" if audit.status == "passed" else "INCOMPLETE_PROVIDER_RESPONSE",
        "power_vs_local_station": "PENDING_STATION_DATA",
        "power_vs_gpm_imerg": "PENDING_IMERG_EXPORT",
        "modis_vegetation_export": "PENDING_FARM_POLYGON_AND_EXPORT",
    }
    return summary


@router.post("/climate/compare", response_model=ClimateComparisonResponse)
def compare_daily_climate_series(payload: ClimateComparisonRequest):
    """Compare pre-aligned daily products or a product with station observations."""
    return compare_climate_series(payload)
