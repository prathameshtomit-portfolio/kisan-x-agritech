from datetime import date

from app.schemas.observation import ObservationResponse
from app.services.nasa_power import NASADataError, NASA_POWER_Client, nasa_power_client


def build_observation_response(
    farm_id: str,
    start_date: date,
    end_date: date,
    records,
) -> ObservationResponse:
    return ObservationResponse(
        farm_id=farm_id,
        period_start=start_date,
        period_end=end_date,
        retrieval_status="success" if records else "no_data",
        observations=records,
        missing_values=sum(1 for item in records if item.value is None),
        source_notes=[
            "NASA POWER values are gridded context, not farm-sensor readings.",
            "Daily values are not interchangeable with monthly totals or forecasts.",
            "Missing provider values remain null; they are not replaced with zero.",
        ],
    )


async def get_farm_observations(farm, start_date: date, end_date: date, client: NASA_POWER_Client | None = None):
    api = client or nasa_power_client
    records = await api.fetch_daily(farm.latitude, farm.longitude, start_date, end_date)
    return build_observation_response(farm.farm_id, start_date, end_date, records)
