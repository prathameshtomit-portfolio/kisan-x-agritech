from fastapi import APIRouter

from app.api.v1.endpoints import ai_assistant, catalog, climate, earth_observation, farms, health, observations, payments, reports, rotations, simulations, weather_forecast

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(farms.router)
api_router.include_router(catalog.router)
api_router.include_router(climate.router)
api_router.include_router(payments.router)
api_router.include_router(observations.router)
api_router.include_router(rotations.router)
api_router.include_router(simulations.router)
api_router.include_router(reports.router)
api_router.include_router(earth_observation.router)
api_router.include_router(weather_forecast.router)
api_router.include_router(ai_assistant.router)
