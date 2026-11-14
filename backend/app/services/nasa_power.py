import asyncio
import logging
import time
from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.schemas.observation import ObservationRecord

logger = logging.getLogger(__name__)

PARAMETER_MAP = {
    "T2M": ("air_temperature_2m", "°C", "MERRA-2", "0.5° × 0.625° (~50 km)"),
    "T2M_MAX": ("air_temperature_2m_max", "°C", "MERRA-2", "0.5° × 0.625° (~50 km)"),
    "T2M_MIN": ("air_temperature_2m_min", "°C", "MERRA-2", "0.5° × 0.625° (~50 km)"),
    "PRECTOTCORR": ("precipitation_corrected", "mm/day", "MERRA-2", "0.5° × 0.625° (~50 km)"),
    "RH2M": ("relative_humidity_2m", "%", "MERRA-2", "0.5° × 0.625° (~50 km)"),
    "ALLSKY_SFC_SW_DWN": (
        "surface_shortwave_downward_all_sky",
        "MJ/m²/day",
        "CERES SYN1deg",
        "1° (~100 km)",
    ),
}

NASA_LIMITATIONS = [
    "NASA POWER is a gridded environmental data product, not an on-farm sensor.",
    "Check the selected parameter's current product resolution, provenance, and latency before farmer-facing use.",
    "Historical/reanalysis context is not a forecast and is not a substitute for local measurements.",
]


class NASADataError(Exception):
    pass


class NASA_POWER_Client:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, list[ObservationRecord]]] = {}
        self._lock = asyncio.Lock()

    async def fetch_daily(
        self, latitude: float, longitude: float, start_date: date, end_date: date
    ) -> list[ObservationRecord]:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        if (end_date - start_date).days > 3660:
            raise ValueError("The requested period cannot exceed 10 years.")

        cache_key = f"{latitude:.5f}|{longitude:.5f}|{start_date}|{end_date}"
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return cached

        params = {
            "parameters": ",".join(PARAMETER_MAP),
            "community": "AG",
            "longitude": longitude,
            "latitude": latitude,
            "start": start_date.strftime("%Y%m%d"),
            "end": end_date.strftime("%Y%m%d"),
            "format": "JSON",
            "time-standard": "UTC",
        }
        payload = await self._request(params)
        records = self._normalize(payload, latitude, longitude)
        await self._set_cached(cache_key, records)
        return records

    async def _get_cached(self, key: str) -> list[ObservationRecord] | None:
        if settings.nasa_power_cache_ttl_seconds <= 0:
            return None
        async with self._lock:
            item = self._cache.get(key)
            if item and (time.monotonic() - item[0]) < settings.nasa_power_cache_ttl_seconds:
                return item[1]
            self._cache.pop(key, None)
            return None

    async def _set_cached(self, key: str, records: list[ObservationRecord]) -> None:
        if settings.nasa_power_cache_ttl_seconds <= 0:
            return
        async with self._lock:
            self._cache[key] = (time.monotonic(), records)

    async def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(settings.nasa_power_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=settings.nasa_power_timeout_seconds) as client:
                    response = await client.get(settings.nasa_power_base_url, params=params)
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise NASADataError("NASA POWER returned a response in an unexpected format.")
                    return payload
            except (httpx.HTTPError, ValueError, NASADataError) as exc:
                last_error = exc
                if attempt < settings.nasa_power_retries:
                    await asyncio.sleep(min(0.5 * (2**attempt), 2.0))
        logger.warning("NASA POWER request failed after retries: %s", last_error)
        raise NASADataError("NASA POWER is temporarily unavailable. No substitute data was inserted.") from last_error

    @staticmethod
    def _normalize(payload: dict[str, Any], latitude: float, longitude: float) -> list[ObservationRecord]:
        properties = payload.get("properties") or {}
        parameters = properties.get("parameter") or {}
        if not parameters:
            message = (payload.get("messages") or {}).get("warning") or (payload.get("header") or {}).get("title")
            raise NASADataError(f"NASA POWER response did not contain parameter data. {message or ''}".strip())

        retrieved_at = datetime.now(timezone.utc)
        result: list[ObservationRecord] = []
        for raw_name, (variable, unit, source_product, spatial_resolution) in PARAMETER_MAP.items():
            series = parameters.get(raw_name) or {}
            for day_key, raw_value in sorted(series.items()):
                try:
                    observed_at = datetime.strptime(day_key, "%Y%m%d").date()
                except (TypeError, ValueError):
                    continue
                value: float | None
                try:
                    numeric = float(raw_value)
                    value = None if numeric <= -900 else numeric
                except (TypeError, ValueError):
                    value = None
                result.append(
                    ObservationRecord(
                        source_id=f"NASA-POWER-DAILY-{source_product.upper().replace(' ', '-')}",
                        provider="NASA POWER",
                        product=f"POWER Daily Point / {source_product}",
                        source_version="NASA POWER Daily Point; source/product versions are provider-managed",
                        variable=variable,
                        raw_parameter=raw_name,
                        value=value,
                        unit=unit,
                        observed_at=observed_at,
                        latitude=latitude,
                        longitude=longitude,
                        spatial_scale=f"{source_product} grid cell; regional context, not a farm measurement",
                        spatial_resolution=spatial_resolution,
                        temporal_scale="daily",
                        time_standard="UTC",
                        coverage_fraction=0.0 if value is None else 1.0,
                        observation_type="gridded_estimate_or_reanalysis",
                        quality_flag="missing" if value is None else "provider_value_returned",
                        retrieved_at=retrieved_at,
                        source_url=settings.nasa_power_base_url,
                        limitations=NASA_LIMITATIONS,
                        provider_metadata={
                            "community": "AG",
                            "time_standard": "UTC",
                            "source_product": source_product,
                            "source_version": "NASA POWER Daily Point; provider-managed",
                            "spatial_resolution": spatial_resolution,
                            "provider_header": payload.get("header", {}),
                            "provider_parameter_metadata": (properties.get("parameter_information") or {}).get(raw_name, {}),
                        },
                    )
                )
        return result


nasa_power_client = NASA_POWER_Client()
