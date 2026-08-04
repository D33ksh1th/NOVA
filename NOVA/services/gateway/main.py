"""
NOVA Gateway
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from packages.config import settings
from packages.database import database_manager
from services.gateway.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_manager.initialize()
    from packages.registry import registry
    registry.gmail_monitor.start()
    yield
    registry.gmail_monitor.stop()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)


def _csv_or_all(value: str):
    value = (value or "*").strip()
    if value == "*":
        return ["*"]
    return [item.strip() for item in value.split(",") if item.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_csv_or_all(settings.CORS_ALLOW_ORIGINS),
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=_csv_or_all(settings.CORS_ALLOW_METHODS),
    allow_headers=_csv_or_all(settings.CORS_ALLOW_HEADERS),
)

UI_DIR = Path(__file__).resolve().parent / "ui"

if UI_DIR.exists():
    app.mount("/ui-static", StaticFiles(directory=str(UI_DIR)), name="ui-static")

# Register all API routes
app.include_router(router)