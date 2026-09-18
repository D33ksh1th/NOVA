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
from services.gateway.agent_status import router as agent_status_router
from services.gateway.music import router as music_router
from services.agent_runtime.service import attach_runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_manager.initialize()
    from packages.registry import registry
    from packages.events import bus, Event
    import packages.events.subscribers  # noqa: F401 — register core listeners
    bus.emit(Event.APP_STARTED, source="gateway", severity=0)
    registry.gmail_monitor.start()
    # Pre-warm TTS model so first response doesn't have 500ms cold start
    if hasattr(registry.voice_engine.synthesizer, '_get_kokoro'):
        import threading
        threading.Thread(
            target=lambda: registry.voice_engine.synthesizer._get_kokoro(
                registry.voice_engine.synthesizer._model_path,
                registry.voice_engine.synthesizer._voices_path,
            ),
            daemon=True,
        ).start()
    # Keep Ollama model warm — ping every 4 min so it stays loaded in RAM
    import threading, requests as _req
    def _keep_ollama_warm():
        import time as _t
        while True:
            try:
                _req.post(
                    f"{settings.OLLAMA_HOST}/api/generate",
                    json={"model": settings.CHAT_MODEL, "prompt": "", "stream": False, "options": {"num_predict": 1}},
                    timeout=10,
                )
            except Exception:
                pass
            _t.sleep(240)
    threading.Thread(target=_keep_ollama_warm, daemon=True, name="ollama-keepalive").start()
    try:
        async with attach_runtime(app, registry, settings):
            yield
    finally:
        bus.emit(Event.APP_STOPPED, source="gateway", severity=0)
        bus.stop()
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
app.include_router(agent_status_router)
app.include_router(music_router)
app.include_router(router)