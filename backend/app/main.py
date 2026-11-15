import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import http_exception_handler, validation_exception_handler
from app.core.logging import configure_logging
from app.db.init_db import init_db, seed_payment_defaults
from app.services.nasa_satellites_hub import router as satellites_router

configure_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.auto_create_tables:
        logger.info("Creating local database tables when absent")
        init_db()
    else:
        logger.info("Ensuring default payment configuration exists")
        seed_payment_defaults()
    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    description=(
        "KISAN-X field workspace: farm profiles and mapped boundary estimates, NASA environmental context, "
        "a 13-source Earth observation hub, evidence-aware rotation comparisons, reports, and owner-verified direct UPI claims."
    ),
    version="0.3.1",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.include_router(api_router, prefix=settings.api_v1_prefix)
app.include_router(satellites_router)
WEB_DIR = Path(__file__).resolve().parents[1] / "web"
app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")


@app.get("/", tags=["health"])
def root():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(WEB_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(WEB_DIR / "sw.js", media_type="application/javascript",
                         headers={"Cache-Control": "no-cache"})


@app.get("/health", tags=["health"])
def health_alias():
    return {"status": "ok", "service": "kisan-x-api"}
