from __future__ import annotations

import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS, DATABASE_PATH, GTFS_ZIP_PATH
from app.database import gtfs_is_usable, has_tables
from app.schemas import HealthResponse, ReadinessResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("crowdwise.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "starting api etm_database=%s gtfs_archive=%s",
        DATABASE_PATH.exists(),
        GTFS_ZIP_PATH.exists(),
    )
    poller = None
    cleanup_task = asyncio.create_task(_community_cleanup_loop(), name="crowdwise-community-expiry")
    from app.config import GTFS_RT_API_KEY, GTFS_RT_URL
    if GTFS_RT_URL and GTFS_RT_API_KEY:
        from app.services.realtime_service import polling_loop
        poller = asyncio.create_task(polling_loop(), name="crowdwise-gtfs-rt-poller")
        logger.info("GTFS-RT polling enabled")
    else:
        logger.info("GTFS-RT polling disabled; provider URL or API key is not configured")
    yield
    if poller is not None:
        poller.cancel()
        try:
            await poller
        except asyncio.CancelledError:
            pass
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("stopping api")


async def _community_cleanup_loop():
    from app.services.community_store import store
    while True:
        try:
            deleted = await asyncio.to_thread(store.purge_expired)
            if deleted:
                logger.info("expired community records purged count=%d", deleted)
        except Exception:
            logger.exception("community expiry cleanup failed")
        await asyncio.sleep(60)


app = FastAPI(
    title="CrowdWise API",
    description=(
        "Delhi bus ticket-volume analytics. Historical ticket records are not live data, "
        "and their transaction timestamps are not assumed to be boarding times."
    ),
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "X-CrowdWise-Client"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request failed method=%s path=%s", request.method, request.url.path)
        raise
    elapsed_ms = (perf_counter() - started) * 1000
    logger.info(
        "request method=%s path=%s status=%s duration_ms=%.1f",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        processed_data_available=has_tables("etm_records", "stop_catalog", "stop_demand", "data_quality"),
        gtfs_available=GTFS_ZIP_PATH.exists(),
        gtfs_processed_available=gtfs_is_usable(),
        generated_at=datetime.now(UTC),
    )


@app.get("/ready", response_model=ReadinessResponse, tags=["system"])
def readiness() -> ReadinessResponse:
    available = has_tables("etm_records", "stop_catalog", "stop_demand", "data_quality")
    if not available:
        raise HTTPException(status_code=503, detail="Processed ETM database is unavailable")
    return ReadinessResponse(status="ready", processed_data_available=True, generated_at=datetime.now(UTC))


from app.api.routes.analytics import router as analytics_router  # noqa: E402
from app.api.routes.journeys import router as journeys_router  # noqa: E402
from app.api.routes.routes import router as routes_router  # noqa: E402
from app.api.routes.stops import router as stops_router  # noqa: E402
from app.api.routes.system import router as system_router  # noqa: E402
from app.api.routes.community import crowding_router, presence_router, reports_router  # noqa: E402
from app.api.routes.vehicles import realtime_router, vehicles_router  # noqa: E402

app.include_router(analytics_router, prefix="/api/v1")
app.include_router(journeys_router, prefix="/api/v1")
app.include_router(routes_router, prefix="/api/v1")
app.include_router(stops_router, prefix="/api/v1")
app.include_router(system_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(crowding_router, prefix="/api/v1")
app.include_router(presence_router, prefix="/api/v1")
app.include_router(vehicles_router, prefix="/api/v1")
app.include_router(realtime_router, prefix="/api/v1")

