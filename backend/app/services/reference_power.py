import csv
import hashlib
import io
import re
from collections import Counter
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from app.core.config import BACKEND_DIR
from app.schemas.climate import ClimateAudit, ClimateDay, ClimateSource

REFERENCE_CSV = BACKEND_DIR / "data" / "reference" / "nagpur_power_daily_2001_2025.csv"
VARIABLES = (
    "T2M",
    "T2M_MAX",
    "T2M_MIN",
    "PRECTOTCORR",
    "RH2M",
    "ALLSKY_SFC_SW_DWN",
)
VARIABLE_LABELS = {
    "T2M": ("Mean air temperature at 2 m", "°C", "MERRA-2"),
    "T2M_MAX": ("Maximum air temperature at 2 m", "°C", "MERRA-2"),
    "T2M_MIN": ("Minimum air temperature at 2 m", "°C", "MERRA-2"),
    "PRECTOTCORR": ("Corrected total precipitation", "mm/day", "MERRA-2"),
    "RH2M": ("Relative humidity at 2 m", "%", "MERRA-2"),
    "ALLSKY_SFC_SW_DWN": ("All-sky surface shortwave downward irradiance", "MJ/m²/day", "CERES SYN1deg"),
}
EXPECTED_COLUMNS = ("YEAR", "DOY", *VARIABLES)
DEFAULT_START = date(2001, 1, 1)
DEFAULT_END = date(2025, 12, 31)


class ReferencePowerDataError(RuntimeError):
    pass


class ReferencePowerDataset:
    def __init__(self, source: ClimateSource, audit: ClimateAudit, days: list[ClimateDay]):
        self.source = source
        self.audit = audit
        self.days = days


def _metadata_date_range(header: str) -> tuple[date, date]:
    match = re.search(r"Dates\s*\(month/day/year\):\s*(\d{2}/\d{2}/\d{4})\s+through\s+(\d{2}/\d{2}/\d{4})", header)
    if not match:
        raise ReferencePowerDataError("NASA POWER CSV is missing its declared date range.")
    return datetime.strptime(match.group(1), "%m/%d/%Y").date(), datetime.strptime(match.group(2), "%m/%d/%Y").date()


def load_reference_power(path: Path = REFERENCE_CSV) -> ReferencePowerDataset:
    if not path.is_file():
        raise ReferencePowerDataError(f"Reference NASA POWER file was not found: {path.name}")
    raw_bytes = path.read_bytes()
    raw_text = raw_bytes.decode("utf-8-sig")
    lines = raw_text.splitlines()
    try:
        end_header = next(index for index, line in enumerate(lines) if line.strip() == "-END HEADER-")
    except StopIteration as exc:
        raise ReferencePowerDataError("NASA POWER CSV has no -END HEADER- marker.") from exc
    header_text = "\n".join(lines[: end_header + 1])
    body = "\n".join(lines[end_header + 1 :]).strip()
    if not body:
        raise ReferencePowerDataError("NASA POWER CSV has no daily data rows.")

    period_start, period_end = _metadata_date_range(header_text)
    location = re.search(r"latitude\s+([-+]?\d+(?:\.\d+)?)\s+longitude\s+([-+]?\d+(?:\.\d+)?)", header_text, re.I)
    if not location:
        raise ReferencePowerDataError("NASA POWER CSV is missing its coordinate metadata.")
    latitude, longitude = float(location.group(1)), float(location.group(2))
    elevation_match = re.search(r"=\s*([-+]?\d+(?:\.\d+)?)\s+meters", header_text, re.I)
    elevation_m = float(elevation_match.group(1)) if elevation_match else None
    missing_match = re.search(r"missing source data[^\n]*:\s*([-+]?\d+(?:\.\d+)?)", header_text, re.I)
    sentinel = float(missing_match.group(1)) if missing_match else -999.0

    reader = csv.DictReader(io.StringIO(body))
    columns = tuple((column or "").strip() for column in (reader.fieldnames or []))
    rows: list[ClimateDay] = []
    sentinel_counts = Counter({name: 0 for name in VARIABLES})
    null_counts = Counter({name: 0 for name in VARIABLES})
    numeric_values: dict[str, list[float]] = {name: [] for name in VARIABLES}
    range_violations = Counter({"negative_precipitation": 0, "maximum_below_minimum": 0})
    for row_number, raw_row in enumerate(reader, start=2):
        try:
            year = int(raw_row["YEAR"])
            day_of_year = int(raw_row["DOY"])
            observed_at = date(year, 1, 1) + timedelta(days=day_of_year - 1)
            if observed_at.year != year:
                raise ValueError("DOY falls outside YEAR")
        except (KeyError, TypeError, ValueError) as exc:
            raise ReferencePowerDataError(f"Invalid YEAR/DOY in CSV row {row_number}.") from exc
        values: dict[str, float | None] = {}
        flags: dict[str, str] = {}
        for variable in VARIABLES:
            raw_value = (raw_row.get(variable) or "").strip()
            try:
                numeric = float(raw_value)
            except ValueError as exc:
                raise ReferencePowerDataError(f"Invalid {variable} value in CSV row {row_number}.") from exc
            if numeric == sentinel:
                values[variable] = None
                flags[variable] = "missing"
                sentinel_counts[variable] += 1
                null_counts[variable] += 1
            else:
                if numeric != numeric or numeric in (float("inf"), float("-inf")):
                    raise ReferencePowerDataError(f"Non-finite {variable} value in CSV row {row_number}.")
                values[variable] = numeric
                flags[variable] = "provider_value_returned"
                numeric_values[variable].append(numeric)
        if values["PRECTOTCORR"] is not None and values["PRECTOTCORR"] < 0:
            range_violations["negative_precipitation"] += 1
        if values["T2M_MAX"] is not None and values["T2M_MIN"] is not None and values["T2M_MAX"] < values["T2M_MIN"]:
            range_violations["maximum_below_minimum"] += 1
        rows.append(ClimateDay(observed_at=observed_at, values=values, quality_flags=flags))

    dates = [row.observed_at for row in rows]
    counts = Counter(dates)
    duplicates = sorted(day for day, count in counts.items() if count > 1)
    expected_dates = [period_start + timedelta(days=index) for index in range((period_end - period_start).days + 1)]
    expected_set = set(expected_dates)
    date_set = set(dates)
    missing_dates = sorted(expected_set - date_set)
    unexpected_dates = sorted(date_set - expected_set)
    checks = {
        "columns_present": set(EXPECTED_COLUMNS).issubset(columns),
        "date_range_declared": period_start == DEFAULT_START and period_end == DEFAULT_END,
        "daily_coverage_complete": not missing_dates and not unexpected_dates,
        "dates_unique": not duplicates and len(dates) == len(date_set),
        "coordinates_match_nagpur_proxy": abs(latitude - 21.1458) < 1e-4 and abs(longitude - 79.0882) < 1e-4,
        "row_count_matches_declared_period": len(rows) == len(expected_dates),
        "precipitation_is_nonnegative": range_violations["negative_precipitation"] == 0,
        "daily_maximum_not_below_minimum": range_violations["maximum_below_minimum"] == 0,
    }
    value_ranges = {
        variable: {
            "minimum": round(min(values), 2) if values else None,
            "maximum": round(max(values), 2) if values else None,
            "mean": round(sum(values) / len(values), 2) if values else None,
            "unit": VARIABLE_LABELS[variable][1],
        }
        for variable, values in numeric_values.items()
    }
    source = ClimateSource(
        source_id="NASA-POWER-NAGPUR-REFERENCE-2001-2025",
        label="Nagpur city-centre proxy (regional reference, not a farm measurement)",
        provider="NASA POWER",
        source_product={"meteorology": "MERRA-2", "solar": "CERES SYN1deg"},
        latitude=latitude,
        longitude=longitude,
        elevation_m=elevation_m,
        period_start=period_start,
        period_end=period_end,
        time_standard="UTC",
        spatial_resolution={
            "MERRA-2": "0.5° × 0.625° (~50 km; meteorological variables)",
            "CERES SYN1deg": "1° (~100 km; surface shortwave radiation)",
        },
        variables={
            variable: {"name": label, "unit": unit, "source_product": product}
            for variable, (label, unit, product) in VARIABLE_LABELS.items()
        },
        retrieved_at=None,
        raw_file_sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )
    audit = ClimateAudit(
        status="passed" if all(checks.values()) else "failed",
        expected_daily_rows=len(expected_dates),
        actual_daily_rows=len(rows),
        unique_dates=len(date_set),
        duplicate_dates=duplicates,
        missing_dates=missing_dates,
        unexpected_dates=unexpected_dates,
        null_counts=dict(null_counts),
        sentinel_counts=dict(sentinel_counts),
        range_violations=dict(range_violations),
        value_ranges=value_ranges,
        first_date=min(dates) if dates else None,
        last_date=max(dates) if dates else None,
        checks=checks,
    )
    return ReferencePowerDataset(source, audit, rows)


@lru_cache(maxsize=1)
def get_reference_power() -> ReferencePowerDataset:
    return load_reference_power()
