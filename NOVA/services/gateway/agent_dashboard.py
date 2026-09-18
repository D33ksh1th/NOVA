"""Isolated monitor host. Attach an already-owned manager via app.state.agent_runtime.

Run with uvicorn services.gateway.agent_dashboard:app --host 127.0.0.1
--no-proxy-headers. This host never creates a model, tool registry or runtime.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from services.gateway.agent_status import router


def create_dashboard_app(runtime=None) -> FastAPI:
    app = FastAPI(title="NOVA Agent Monitor", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.agent_runtime = runtime
    app.include_router(router)
    app.mount("/ui-static", StaticFiles(directory=Path(__file__).parent / "ui"), name="ui-static")

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("/agents")

    return app


app = create_dashboard_app()