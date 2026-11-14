import math
from datetime import timedelta
from statistics import mean

from fastapi import HTTPException

from app.schemas.climate import (
    ClimateComparisonMetrics,
    ClimateComparisonRequest,
    ClimateComparisonResponse,
    RainOccurrenceCounts,
)


def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        average_rank = ((cursor + 1) + end) / 2
        for index in order[cursor:end]:
            ranks[index] = average_rank
        cursor = end
    return ranks


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(right) != len(left):
        return None
    left_mean, right_mean = mean(left), mean(right)
    left_sum = sum((value - left_mean) ** 2 for value in left)
    right_sum = sum((value - right_mean) ** 2 for value in right)
    if left_sum == 0 or right_sum == 0:
        return None
    covariance = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True))
    return covariance / math.sqrt(left_sum * right_sum)


def compare_climate_series(payload: ClimateComparisonRequest) -> ClimateComparisonResponse:
    estimated = {point.observed_at: point for point in payload.estimated.values}
    comparison = {point.observed_at: point for point in payload.comparison.values}
    overlap_start = max(min(estimated), min(comparison))
    overlap_end = min(max(estimated), max(comparison))
    if overlap_end < overlap_start:
        raise HTTPException(status_code=422, detail="The series have no overlapping dates.")

    expected_days = (overlap_end - overlap_start).days + 1
    overlap_dates = [overlap_start + timedelta(days=index) for index in range(expected_days)]
    paired = [
        (estimated[day].value, comparison[day].value)
        for day in overlap_dates
        if day in estimated
        and day in comparison
        and estimated[day].value is not None
        and comparison[day].value is not None
        and estimated[day].quality_flag.casefold() not in {"missing", "invalid", "rejected"}
        and comparison[day].quality_flag.casefold() not in {"missing", "invalid", "rejected"}
    ]
    if not paired:
        raise HTTPException(status_code=422, detail="The overlapping period contains no valid paired observations.")
    estimated_values = [pair[0] for pair in paired]
    comparison_values = [pair[1] for pair in paired]
    differences = [left - right for left, right in paired]
    metrics = ClimateComparisonMetrics(
        mean_bias_estimated_minus_comparison=mean(differences),
        mean_absolute_error=mean(abs(value) for value in differences),
        root_mean_square_error=math.sqrt(mean(value * value for value in differences)),
        pearson_r=_correlation(estimated_values, comparison_values),
        spearman_rho=_correlation(_average_ranks(estimated_values), _average_ranks(comparison_values)),
    )
    wet_counts = None
    if payload.wet_day_threshold_mm_day is not None:
        hits = misses = false_alarms = correct_negatives = 0
        for estimated_value, observed_value in paired:
            is_estimated_wet = estimated_value >= payload.wet_day_threshold_mm_day
            is_comparison_wet = observed_value >= payload.wet_day_threshold_mm_day
            if is_estimated_wet and is_comparison_wet:
                hits += 1
            elif not is_estimated_wet and is_comparison_wet:
                misses += 1
            elif is_estimated_wet:
                false_alarms += 1
            else:
                correct_negatives += 1
        wet_counts = RainOccurrenceCounts(
            threshold=payload.wet_day_threshold_mm_day,
            hits=hits,
            misses=misses,
            false_alarms=false_alarms,
            correct_negatives=correct_negatives,
        )
    comparison_is_station = payload.comparison.source_type == "station_observation"
    limitations = [
        "Only matching dates with two valid, non-missing values are paired; nulls are never converted to zero.",
        "The input series must already use aligned daily accumulation windows and quality control; this endpoint does not shift local station days into UTC.",
        "Correlation describes co-variation and does not establish amount agreement or product accuracy.",
    ]
    if comparison_is_station:
        limitations.append("Treat these as station-comparison metrics only after documenting station location, elevation, instrument history, and representativeness for the target farm/grid.")
    else:
        limitations.append("This is a cross-product check, not independent ground-truth validation; both products may share observing inputs or systematic errors.")
    return ClimateComparisonResponse(
        comparison_type="station_comparison_candidate" if comparison_is_station else "cross_product_check",
        estimated_source_id=payload.estimated.source_id,
        estimated_source_label=payload.estimated.source_label,
        comparison_source_id=payload.comparison.source_id,
        comparison_source_label=payload.comparison.source_label,
        unit=payload.estimated.unit,
        time_standard=payload.estimated.time_standard,
        overlap_start=overlap_start,
        overlap_end=overlap_end,
        expected_overlap_days=expected_days,
        paired_days=len(paired),
        coverage_fraction=round(len(paired) / expected_days, 6),
        missing_estimated_days=expected_days - sum(1 for day in overlap_dates if day in estimated and estimated[day].value is not None and estimated[day].quality_flag.casefold() not in {"missing", "invalid", "rejected"}),
        missing_comparison_days=expected_days - sum(1 for day in overlap_dates if day in comparison and comparison[day].value is not None and comparison[day].quality_flag.casefold() not in {"missing", "invalid", "rejected"}),
        metrics=metrics,
        wet_day_counts=wet_counts,
        limitations=limitations,
    )
