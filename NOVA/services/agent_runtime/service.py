"""Backend-owned governed runtime with thread-safe conversation dispatch."""

from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import asynccontextmanager
from pathlib import Path

from services.agent_runtime.agents.research_agent import ResearchOutput
from services.agent_runtime.conversation import AgentConversation, status_reply
from services.agent_runtime.events.audit import _redact_str
from services.agent_runtime.factory import build_runtime_async
from services.agent_runtime.graph.task_graph import GraphPlan
from services.agent_runtime.ids import new_id
from services.agent_runtime.models.ollama import OllamaRuntimeModel, load_local_tokenizer
from services.agent_runtime.models.qualify import qualify
from services.agent_runtime.reports import ReportStore, finish_report, new_report, now


ROOT = Path(__file__).resolve().parents[2]


def research_plan(objective: str, *, read_pages: bool = False) -> GraphPlan:
    budget = {"wall_clock_ms": 120000, "max_tool_calls": 3, "max_llm_tokens": 16000,
              "max_usd": 0, "max_retries": 0}
    common = {"agent": "research_agent", "capabilities": ["web.search"], "tools": ["web_search_tool"],
              "risk": "READ_ONLY", "budget": budget, "objective": "Return only claims backed by search evidence."}
    if read_pages:
        common.update(capabilities=["web.search", "web.read", "net.egress"], tools=["web_search_tool", "web_page_tool"])
    return GraphPlan.model_validate({"goal": objective,
        "budget": {**budget, "wall_clock_ms": 360000, "max_tool_calls": 11, "max_llm_tokens": 48000},
        "nodes": [
            {**common, "id": "scout", "name": "Scout", "description": objective},
            {**common, "id": "atlas", "name": "Atlas", "description": objective},
            {**common, "id": "prism", "name": "Prism", "description": objective,
             "budget": {**budget, "max_tool_calls": 5},
             "depends_on": [{"task_id": parent, "on_failure": "SKIP_DOWNSTREAM"} for parent in ("scout", "atlas")],
             "consumes": [{"task_id": parent, "key": "comparison_points", "input_key": parent} for parent in ("scout", "atlas")]},
        ]})


class RuntimeService:
    def __init__(self) -> None:
        self.manager = None
        self.model = None
        self.state = "STARTING"
        self.reason_code = ""
        self.loop = None
        self.jobs: set[asyncio.Task] = set()
        self.last_result = None
        self.reports = None
        self.last_report = None
        self.repository_enabled = False
        self.read_pages = False
        self._repository_submitting = False

    async def start(self, *, settings, tool_registry, action_gate) -> None:
        self.loop = asyncio.get_running_loop()
        reports_path = getattr(settings, "AGENT_RUNTIME_REPORTS_PATH", None)
        if reports_path:
            try:
                self.reports = ReportStore(ROOT / reports_path)
                await self.reports.open()
                recent = await self.reports.list(limit=1)
                if recent["items"]:
                    self.last_report = await self.reports.get(recent["items"][0]["id"])
            except Exception:
                self.state, self.reason_code = "UNAVAILABLE", "REPORT_STORAGE_FAILED"
                return
        if not settings.AGENT_RUNTIME_ENABLED:
            self.state = "DISABLED"
            return
        try:
            tokenizer_path = ROOT / settings.AGENT_RUNTIME_TOKENIZER_PATH
            report = await qualify(model=settings.AGENT_RUNTIME_MODEL, tokenizer_path=tokenizer_path,
                                   expected_digest=settings.AGENT_RUNTIME_MODEL_DIGEST,
                                   base_url=settings.AGENT_RUNTIME_MODEL_URL)
            if report.status != "PREFLIGHT_ONLY":
                self.state, self.reason_code = "UNAVAILABLE", report.reason
                return
            tokenizer = await asyncio.to_thread(load_local_tokenizer, tokenizer_path)
            self.model = OllamaRuntimeModel(model=settings.AGENT_RUNTIME_MODEL, tokenizer=tokenizer,
                                            base_url=settings.AGENT_RUNTIME_MODEL_URL,
                                            response_schema=ResearchOutput.model_json_schema())
            pilot = ROOT.parent / "nova-desktop"
            self.repository_enabled = bool(getattr(settings, "AGENT_RUNTIME_REPOSITORY_ENABLED", False)
                                           and pilot.is_dir() and not pilot.is_symlink() and self.reports is not None)
            self.manager = await build_runtime_async(tool_registry=tool_registry, action_gate=action_gate,
                llm=self.model, audit_path=ROOT / settings.AGENT_RUNTIME_AUDIT_PATH,
                repository_root=pilot if self.repository_enabled else None,
                read_pages=getattr(settings, "AGENT_RUNTIME_READ_PAGES", False))
            self.read_pages = getattr(settings, "AGENT_RUNTIME_READ_PAGES", False)
            if self.reports is not None:
                await self.reports.recover()
                if self.last_report:
                    self.last_report = await self.reports.get(self.last_report["id"])
            self.state = "READY"
        except Exception:
            self.state, self.reason_code = "UNAVAILABLE", "RUNTIME_STARTUP_FAILED"
            try:
                if self.manager is not None:
                    await self.manager.close()
            finally:
                self.manager = None
                if self.model is not None:
                    await self.model.close()
                    self.model = None

    def runtime_status(self) -> dict:
        status = self.manager.runtime_status() if self.manager is not None else {
            "history_limit": 20, "agents": [], "graphs": [],
        }
        return {**status, "state": self.state, "reason_code": self.reason_code,
                "pending_runs": max(0, len(self.jobs) - sum(graph["status"] == "RUNNING" for graph in status["graphs"]))}

    def command(self, action: str, objective: str = "") -> dict:
        if self.loop is None or not self.loop.is_running():
            return self._reply("My agent runtime is not connected to the backend.", "agent_unavailable")
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if current is self.loop:
            return self._dispatch(action, objective)
        future = asyncio.run_coroutine_threadsafe(self.acommand(action, objective), self.loop)
        try:
            return future.result(timeout=5)
        except FutureTimeout:
            future.cancel()
            return self._reply("The agent runtime is busy. Ask for agent status before retrying a request.", "agent_busy")
        except Exception:
            return self._reply("Agent status is temporarily unavailable.", "agent_unavailable")

    async def acommand(self, action: str, objective: str = "") -> dict:
        return self._dispatch(action, objective)

    async def repository_review(self, objective: str, files: list[str]) -> dict:
        if self.state != "READY" or not self.repository_enabled or self.manager is None or self.reports is None:
            return self._reply("The scoped repository reader is unavailable.", "agent_unavailable")
        if self.jobs or self._repository_submitting:
            return self._reply("An agent task is already active.", "agent_busy")
        objective = objective.strip()
        if (not 1 <= len(objective) <= 400 or _redact_str(objective) != objective
                or not 1 <= len(files) <= 3 or len(set(files)) != len(files)
                or any(not isinstance(path, str) or not 1 <= len(path) <= 240
                       or _redact_str(path) != path or path.startswith("/") or "\\" in path
                       or any(ord(character) < 32 for character in path)
                       or any(part in {"", ".", ".."} for part in path.split("/")) for path in files)):
            return self._reply("Provide a question and one to three distinct relative file paths without secrets.", "agent_refused")
        budget = {"wall_clock_ms": 120000, "max_tool_calls": 3, "max_llm_tokens": 16000,
                  "max_usd": 0, "max_retries": 0}
        plan = GraphPlan.model_validate({"goal": objective, "budget": budget, "nodes": [{
            "id": "repo-reader", "name": "Repo Reader", "agent": "repo_reader", "description": objective,
            "objective": objective, "capabilities": ["repo.read"], "tools": ["repository_read_tool"],
            "risk": "READ_ONLY", "budget": budget, "repository": "nova-desktop", "files": files}]})
        report = new_report(new_id("submission"), objective)
        report.update(kind="repository_review", scope={"repository": "nova-desktop", "files": list(files),
                                                       "mode": "READ_ONLY"})
        self._repository_submitting = True
        try:
            await self.reports.save(report)
            if self.state != "READY":
                report.update(status="CANCELLED", updated_at=now())
                await self.reports.save(report)
                return self._reply("Repository task cancelled before scheduling.", "agent_unavailable")
            self.last_report = report
            self._track(self._run(plan, report), report["id"])
            return self._reply("Read-only repository review queued.", "agent_repository_started", report_id=report["id"])
        except asyncio.CancelledError:
            report.update(status="CANCELLED", updated_at=now())
            await self.reports.save(report)
            raise
        except Exception:
            return self._reply("Repository task could not be saved. No review was scheduled.", "agent_unavailable")
        finally:
            self._repository_submitting = False

    @staticmethod
    def _reply(response: str, action: str, **data) -> dict:
        return {"response": response, "intent": "agent_runtime", "action": action,
                "data": {"monitor_url": "/agents", **data}}

    def _dispatch(self, action: str, objective: str) -> dict:
        if action == "status":
            status = self.runtime_status()
            reply = "An agent research run is queued." if status["pending_runs"] and self.state == "READY" else status_reply(status)
            return self._reply(reply, "agent_status", state=self.state, reason_code=self.reason_code)
        if action == "results":
            if self.last_report is not None:
                report = self.last_report
                parts = [f"Research: {report['topic']}. Outcome: {report['status'].lower()}."]
                preferred = [finding for finding in report["findings"] if finding["task_id"] == "prism"] or report["findings"]
                parts.extend(finding["text"] for finding in preferred[:2])
                if not report["findings"]:
                    parts.append("No verified findings are available yet.")
                if report["gaps"]:
                    parts.append(f"{len(report['gaps'])} task outcomes need attention in the report.")
                return self._reply("\n".join(parts), "agent_results", report_id=report["id"],
                                   report_url=f"/agents?report={report['id']}")
            if self.last_result is None:
                return self._reply("I do not have completed agent findings in this session yet.", "agent_results")
            parts = [status_reply(self.runtime_status())]
            empty_searches = 0
            failed_searches = 0
            failed_models = 0
            for node_id, result in self.last_result.results.items():
                if result.status == "FAILED" and any("MODEL_" in error or "ModelResponseError" in error for error in result.errors):
                    failed_models += 1
                if result.status == "FAILED" and result.summary == "Search provider failed or was unavailable.":
                    failed_searches += 1
                if result.status not in {"SUCCESS", "PARTIAL"} or self.last_result.gaps.get(node_id) not in {None, "PARTIAL_RESULT"}:
                    continue
                if result.status == "PARTIAL" and not result.evidence and not result.payload.get("claims"):
                    empty_searches += 1
                evidence = {item.evidence_id: item.ref for item in result.evidence}
                for claim in result.payload.get("claims", [])[:3]:
                    sources = [evidence[identity] for identity in claim.get("evidence_ids", []) if identity in evidence]
                    if sources:
                        parts.append(claim["text"] + " Sources: " + ", ".join(sources))
            if empty_searches:
                parts.append(f"{empty_searches} research tasks received no attributable search sources. "
                             "Those tasks produced no findings; the model was not used to invent an answer.")
            elif len(parts) == 1:
                parts.append("No verified findings are available from this run.")
            if failed_searches:
                parts.append("The web search provider failed or was unavailable. This is a retrieval failure, not a completed research answer.")
            if failed_models:
                parts.append("The research model failed before verified findings were available. "
                             "Dependent work was stopped. Reserved tokens are a safety budget charge, not confirmed model usage.")
            return self._reply("\n".join(parts), "agent_results")
        if action == "stop" and self.manager is not None:
            if self.state == "HALTED":
                return self._reply("My agent runtime is already halted.", "agent_halted")
            self.state = "HALTED"
            for job in tuple(self.jobs):
                job.cancel()
            self._track(self._halt(), "agent-halt")
            return self._reply("I have requested cancellation of agent work and blocked new runs. Restart the backend to re-enable the runtime.", "agent_halt_requested")
        if self.state != "READY" or self.manager is None:
            return self._reply(status_reply(self.runtime_status()), "agent_unavailable", reason_code=self.reason_code)
        if action != "research":
            return self._reply("Only read-only agent research is enabled.", "agent_refused")
        if self.jobs or self._repository_submitting:
            return self._reply("An agent run is already active. Ask for agent status or stop all agents.", "agent_busy")
        objective = objective.strip()
        if not 1 <= len(objective) <= 400 or _redact_str(objective) != objective:
            return self._reply("Use a research topic between 1 and 400 characters, without credentials or secrets.", "agent_refused")
        plan = research_plan(objective, read_pages=self.read_pages)
        self.last_result = None
        submission_id = new_id("submission")
        report = new_report(submission_id, objective) if self.reports is not None else None
        self.last_report = report
        self._track(self._run(plan, report), submission_id)
        return self._reply("On it. I'll let you know when the report is ready.",
                           "agent_research_started", submission_id=submission_id,
                           **({"report_id": submission_id, "report_url": f"/agents?report={submission_id}"} if report else {}))

    def _track(self, coroutine, name: str) -> None:
        task = asyncio.create_task(coroutine, name=name)
        self.jobs.add(task)
        task.add_done_callback(self.jobs.discard)

    async def _run(self, plan: GraphPlan, report: dict | None = None) -> None:
        try:
            if report is not None:
                report.update(status="RUNNING", updated_at=now())
                await self.reports.save(report)
            self.last_result = await self.manager.run_graph(plan)
            if report is not None:
                report = finish_report(report, self.last_result)
                await self.reports.save(report)
                self.last_report = report
        except asyncio.CancelledError:
            if report is not None:
                report.update(status="CANCELLED", updated_at=now())
                await self.reports.save(report)
                self.last_report = report
            raise
        except Exception:
            if report is not None:
                report.update(status="FAILED", updated_at=now())
                report["gaps"] = [{"task_id": "", "name": "Runtime", "reason": "Run execution or report storage failed."}]
                self.last_report = report
                try:
                    await self.reports.save(report)
                except Exception:
                    self.reason_code = "REPORT_STORAGE_FAILED"
            if self.state != "HALTED":
                self.state = "UNAVAILABLE"
                self.reason_code = self.reason_code or "AGENT_RUN_FAILED"

    async def _halt(self) -> None:
        try:
            await self.manager.halt_all("NOVA conversation requested stop")
            await self._cancel_queued_report()
        except Exception:
            self.reason_code = "AUDIT_HALT_FAILED"

    async def _cancel_queued_report(self) -> None:
        if self.reports is not None and self.last_report is not None and self.last_report["status"] == "QUEUED":
            self.last_report.update(status="CANCELLED", updated_at=now())
            self.last_report["gaps"] = [{"task_id": "", "name": "Runtime", "reason": "Run cancelled before research started."}]
            await self.reports.save(self.last_report)

    async def close(self) -> None:
        self.state = "HALTED"
        for job in tuple(self.jobs):
            job.cancel()
        if self.manager is not None:
            try:
                await self.manager.halt_all("Backend shutdown")
            finally:
                await asyncio.gather(*tuple(self.jobs), return_exceptions=True)
                try:
                    try:
                        await self._cancel_queued_report()
                    finally:
                        await self.manager.close()
                finally:
                    if self.model is not None:
                        await self.model.close()
        elif self.model is not None:
            await self.model.close()


@asynccontextmanager
async def attach_runtime(app, registry, settings):
    owner = RuntimeService()
    previous = getattr(registry.conversation, "agent_runtime", None)
    registry.conversation.agent_runtime = AgentConversation(owner)
    app.state.agent_runtime = owner
    try:
        await owner.start(settings=settings, tool_registry=registry.tool_registry, action_gate=registry.action_gate)
        yield owner
    finally:
        try:
            await owner.close()
        finally:
            registry.conversation.agent_runtime = previous
            app.state.agent_runtime = None