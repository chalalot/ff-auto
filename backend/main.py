import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api import workspace, gallery, config_routes, monitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
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


@app.get("/health")
def health():
    return {"status": "ok"}
