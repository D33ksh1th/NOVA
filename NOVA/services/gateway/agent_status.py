"""Local runtime monitoring and commands. Never imports the live service registry."""

from datetime import datetime, timezone
from ipaddress import ip_address
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field


DESKTOP_ORIGINS = frozenset({"http://localhost:1420", "http://127.0.0.1:1420", "tauri://localhost"})


def require_local(request: Request) -> None:
    try:
        local = request.client is not None and ip_address(request.client.host).is_loopback
    except ValueError:
        local = False
    if not local or request.url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="Local monitor access required")
    origin = request.headers.get("origin")
    if origin is not None and origin not in DESKTOP_ORIGINS and origin != f"{request.url.scheme}://{request.url.netloc}":
        raise HTTPException(status_code=403, detail="Same-origin monitor access required")


router = APIRouter(dependencies=[Depends(require_local)])


class NodeStatus(BaseModel):
    id: str
    name: str
    agent: str
    depends_on: list[str] = Field(default_factory=list)
    state: str
    result_status: str | None = None
    attempts: int = 0


class GraphStatus(BaseModel):
    graph_id: str
    status: str
    nodes: list[NodeStatus]
    finished_tasks: int
    successful_tasks: int
    total_tasks: int
    finished_percent: float | None
    elapsed_ms: int


class AgentStatus(BaseModel):
    id: str
    enabled: bool
    concurrency_limit: int
    capabilities: list[str]
    risk: str


class RuntimeStatus(BaseModel):
    state: Literal["DISABLED", "STARTING", "UNAVAILABLE", "READY", "HALTED"]
    reason_code: str = ""
    pending_runs: int = 0
    history_limit: int
    agents: list[AgentStatus]
    graphs: list[GraphStatus]
    observed_at: str


@router.get("/api/agent-runtime/status", response_model=RuntimeStatus)
async def runtime_status(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    runtime = getattr(request.app.state, "agent_runtime", None)
    status = runtime.runtime_status() if runtime is not None else {
        "state": "DISABLED", "history_limit": 20, "agents": [], "graphs": [],
    }
    return {**status, "observed_at": datetime.now(timezone.utc).isoformat()}


@router.get("/agents", include_in_schema=False)
async def agent_monitor():
    return FileResponse(Path(__file__).parent / "ui" / "agents.html", headers={"Cache-Control": "no-store"})


class AgentCommand(BaseModel):
    action: Literal["research", "status", "results", "stop"]
    objective: str = Field(default="", max_length=400)


@router.post("/api/agent-runtime/command")
async def agent_command(body: AgentCommand, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    runtime = getattr(request.app.state, "agent_runtime", None)
    if runtime is None or not hasattr(runtime, "acommand"):
        raise HTTPException(status_code=503, detail="Agent runtime is not attached")
    return await runtime.acommand(body.action, body.objective)


def report_store(request: Request):
    store = getattr(getattr(request.app.state, "agent_runtime", None), "reports", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Research report storage is unavailable")
    return store

class RepositoryReviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repository: Literal["nova-desktop"]
    objective: str = Field(min_length=1, max_length=400)
    files: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(min_length=1, max_length=3)


@router.post("/api/agent-runtime/repository-review")
async def repository_review(body: RepositoryReviewCommand, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    runtime = getattr(request.app.state, "agent_runtime", None)
    if runtime is None or not hasattr(runtime, "repository_review"):
        raise HTTPException(status_code=503, detail="Repository reader is not attached")
    return await runtime.repository_review(body.objective, body.files)


@router.get("/api/agent-runtime/reports")
async def report_history(request: Request, response: Response, limit: int = Query(30, ge=1, le=100),
                         offset: int = Query(0, ge=0), query: str = Query("", max_length=400)):
    response.headers["Cache-Control"] = "no-store"
    return await report_store(request).list(limit=limit, offset=offset, query=query)


@router.get("/api/agent-runtime/reports/{report_id}")
async def research_report(report_id: str, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    report = await report_store(request).get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Research report not found")
    return report