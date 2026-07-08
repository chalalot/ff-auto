import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api import (
    workspace,
    gallery,
    config_routes,
    monitor,
    video as video_module,
    archive as archive_module,
    evaluations as evaluations_module,
    analysis as analysis_module,
    review as review_module,
    members as members_module,
    projects as projects_module,
    uploads as uploads_module,
)
from backend.database.engine import assert_database_ready

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast if the DB is unreachable or not migrated to alembic head.
    assert_database_ready()
    logger.info("ff-auto backend starting up")
    yield
    logger.info("ff-auto backend shutting down")


app = FastAPI(
    title="ff-auto API",
    description="Backend API for ff-auto image pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow React dev server and same-origin nginx in prod
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(workspace.router, prefix="/api/workspace", tags=["workspace"])
app.include_router(gallery.router, prefix="/api/gallery", tags=["gallery"])
app.include_router(config_routes.router, prefix="/api/config", tags=["config"])
app.include_router(monitor.router, prefix="/api/monitor", tags=["monitor"])
app.include_router(video_module.router, prefix="/api/video", tags=["video"])
app.include_router(archive_module.router, prefix="/api/archive", tags=["archive"])
app.include_router(evaluations_module.router, prefix="/api/evaluations", tags=["evaluations"])
app.include_router(analysis_module.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(review_module.router, prefix="/api/review", tags=["review"])
app.include_router(members_module.router, prefix="/api/members", tags=["members"])
app.include_router(projects_module.router, prefix="/api/projects", tags=["projects"])
app.include_router(uploads_module.router, prefix="/api/uploads", tags=["uploads"])


@app.get("/health")
def health():
    return {"status": "ok"}
