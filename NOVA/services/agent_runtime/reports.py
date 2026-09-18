"""Persisted, verified research reports, separate from the append-only audit."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urldefrag, urlsplit

from services.agent_runtime.contracts.model_usage import MODEL_FAILURE_MESSAGES
from services.agent_runtime.events.audit import _redact_str
from services.agent_runtime.policy.url_policy import UrlPolicy, check_url
from services.agent_runtime.policy.image_policy import allowed_thumbnail


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password:
            return value if _redact_str(value) == value else None
    except ValueError:
        pass
    return None


def new_report(report_id: str, topic: str) -> dict:
    return {"id": report_id, "topic": _redact_str(topic), "created_at": now(), "updated_at": now(),
            "status": "QUEUED", "graph_id": None, "tasks": [], "findings": [], "sources": [],
            "gaps": [], "images": [], "elapsed_ms": 0}


def finish_report(report: dict, result) -> dict:
    findings, sources, tasks, gaps, images, searches = [], {}, [], [], {}, []
    page_reads = []
    repository = report.get("kind") == "repository_review"
    approved_refs = {f"repo:{path}" for path in report.get("scope", {}).get("files", [])} if repository else set()
    for node in result.nodes:
        task_result = result.results.get(node.id)
        if task_result:
            for page in task_result.payload.get("page_reads", []):
                if source_url(page.get("url", "")):
                    page_reads.append({"task_id": node.id, "agent_name": node.name, **page})
            for search in task_result.payload.get("searches", []):
                searches.append({"task_id": node.id, "agent_name": node.name,
                                 "query": _redact_str(str(search.get("query", ""))),
                                 "status": search.get("status", "UNKNOWN"),
                                 "sources": search.get("sources", 0),
                                 "reviewed_sources": search.get("reviewed_sources", 0),
                                 "retrieval": search.get("retrieval", {})})
        accepted = (node.state == "COMPLETED" and task_result is not None
                    and task_result.status in {"SUCCESS", "PARTIAL"}
                    and result.gaps.get(node.id) in {None, "PARTIAL_RESULT"})
        task = {"id": node.id, "name": node.name, "agent": node.agent, "state": str(node.state),
                "result_status": str(task_result.status) if task_result else None,
                "attempts": node.attempts, "depends_on": list(node.depends_on)}
        tasks.append(task)
        if accepted:
            evidence = {item.evidence_id: item for item in task_result.evidence
                        if item.task_id == task_result.task_id and (source_url(item.ref) if not repository else
                            item.kind == "file_content" and item.tool == "repository_read_tool" and item.ref in approved_refs)}
            cited_pages = {urldefrag(evidence[identity].ref)[0]
                           for claim in task_result.payload.get("claims", [])
                           if claim.get("evidence_ids") and all(identity in evidence for identity in claim["evidence_ids"])
                           for identity in claim["evidence_ids"]}
            for image in task_result.media:
                if (image.task_id == task_result.task_id and image.kind == "image_reference"
                        and urldefrag(image.ref)[0] in cited_pages
                        and image.image_url and image.image_url.startswith("https://")
                        and allowed_thumbnail(image.image_url) and source_url(image.ref)
                        and _redact_str(image.image_url) == image.image_url):
                    images.setdefault(image.image_url, {"id": image.evidence_id, "title": _redact_str(image.title),
                                                       "url": image.image_url, "source_url": image.ref,
                                                       "relevance": image.relevance,
                                                       "retrieved_at": image.retrieved_at.isoformat(), "digest": image.digest})
            for claim in task_result.payload.get("claims", []):
                identities = claim.get("evidence_ids", [])
                if not identities or not all(identity in evidence for identity in identities):
                    continue
                findings.append({"task_id": node.id, "agent_name": node.name,
                                 "text": _redact_str(claim["text"]), "source_ids": list(dict.fromkeys(identities)),
                                 "category": claim.get("category", "finding"),
                                 "subject": _redact_str(claim.get("subject", "")),
                                 "priority": claim.get("priority", "normal")})
                for identity in identities:
                    item = evidence[identity]
                    sources[identity] = {"id": identity, "url": item.ref, "domain": "nova-desktop" if repository else urlsplit(item.ref).hostname,
                                         "kind": item.kind,
                                         "title": _redact_str(item.title), "relevance": item.relevance,
                                         "retrieved_at": item.retrieved_at.isoformat(), "digest": item.digest}
        if node.id in result.gaps or not accepted:
            reason = "Task did not produce verified findings."
            model_reason = next((MODEL_FAILURE_MESSAGES[error.partition(":")[0]] for error in task_result.errors
                                 if error.partition(":")[0] in MODEL_FAILURE_MESSAGES), None) if task_result else None
            if task_result and task_result.status == "PARTIAL":
                failed_searches = sum(search.get("status") == "FAILED" for search in task_result.payload.get("searches", []))
                if failed_searches:
                    reason = f"{failed_searches} search request(s) failed; available findings are incomplete."
                elif not task_result.payload.get("claims"):
                    reason = "No relevant, attributable findings were established for this question."
                else:
                    reason = "Some searches returned no attributable sources; available findings are incomplete."
                if repository:
                    reason = "Selected files were unavailable, excluded, too large for context, or insufficient to establish findings."
                elif any(not page.get("supplied_to_model") for page in task_result.payload.get("page_reads", [])):
                    reason = "Some selected pages were unavailable, denied, or excluded from context; findings may rely on snippets."
            elif task_result and any("FABRICATED_EVIDENCE" in error for error in task_result.errors):
                reason = "Citations could not be verified for this task."
            elif model_reason:
                reason = model_reason
            elif task_result and any("MODEL_" in error or "ModelResponseError" in error for error in task_result.errors):
                reason = "The research model failed before verification."
            elif task_result and any(error in {"TIMED_OUT", "BUDGET_EXCEEDED"} for error in task_result.errors):
                reason = "The task exhausted its time or resource budget."
            elif task_result and task_result.summary == "Search provider failed or was unavailable.":
                reason = "Search providers were unavailable; no attributable sources were retrieved."
            elif node.state == "SKIPPED":
                reason = "Synthesis was skipped because a required research task failed."
            elif node.state in {"CANCELLED", "SKIPPED"}:
                reason = "Task cancelled or blocked by a dependency."
            gaps.append({"task_id": node.id, "name": node.name, "reason": reason})
    synthesis = findings if repository else [finding for finding in findings if finding["task_id"] == "prism"]
    takeaways = sorted(synthesis, key=lambda finding: finding["priority"] != "high")[:3]
    return {**report, "status": result.status, "graph_id": result.graph_id, "updated_at": now(),
            "tasks": tasks, "findings": findings, "sources": sorted(sources.values(), key=lambda source: -(source.get("relevance") or {}).get("score", -1)), "gaps": gaps,
            "key_takeaways": takeaways,
            "coverage": {"searches": searches, "cited_domains": len({source["domain"] for source in sources.values()}),
                  "page_reads": page_reads,
                  "evidence_scope": "selected_repository_files" if repository else "search_results_and_page_extracts" if any(page["supplied_to_model"] for page in page_reads) else "search_results"},
            "images": sorted(images.values(), key=lambda image: -(image.get("relevance") or {}).get("score", -1)), "elapsed_ms": result.elapsed_ms}


class ReportStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._write_lock = asyncio.Lock()

    async def open(self) -> None:
        await asyncio.to_thread(self._initialize)

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        connection = self._connection()
        try:
            with connection:
                connection.execute("CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, topic TEXT NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL)")
        finally:
            connection.close()

    def _connection(self):
        return sqlite3.connect(self.path, timeout=5)

    async def save(self, report: dict) -> None:
        body = json.dumps(report, allow_nan=False)
        snapshot = dict(report)
        async with self._write_lock:
            write = asyncio.create_task(asyncio.to_thread(self._save, snapshot, body))
            try:
                await asyncio.shield(write)
            except asyncio.CancelledError:
                await write
                raise

    def _save(self, report, body):
        connection = self._connection()
        try:
            with connection:
                connection.execute("INSERT INTO reports VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET status=excluded.status, body=excluded.body",
                                   (report["id"], report["created_at"], report["topic"], report["status"], body))
        finally:
            connection.close()

    async def get(self, report_id: str) -> dict | None:
        return await asyncio.to_thread(self._get, report_id)

    def _get(self, report_id):
        connection = self._connection()
        try:
            row = connection.execute("SELECT body FROM reports WHERE id=?", (report_id,)).fetchone()
            return json.loads(row[0]) if row else None
        finally:
            connection.close()

    async def list(self, *, limit: int = 30, offset: int = 0, query: str = "") -> dict:
        return await asyncio.to_thread(self._list, limit, offset, query)

    def _list(self, limit, offset, query):
        connection = self._connection()
        try:
            total = connection.execute("SELECT count(*) FROM reports WHERE instr(lower(topic), lower(?)) > 0", (query,)).fetchone()[0]
            rows = connection.execute("SELECT id, topic, status, created_at FROM reports WHERE instr(lower(topic), lower(?)) > 0 ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                                      (query, limit, offset)).fetchall()
            return {"items": [dict(zip(("id", "topic", "status", "created_at"), row)) for row in rows], "total": total}
        finally:
            connection.close()

    async def recover(self) -> None:
        await asyncio.to_thread(self._recover)

    def _recover(self):
        connection = self._connection()
        try:
            with connection:
                rows = connection.execute("SELECT id, body FROM reports WHERE status IN ('QUEUED', 'RUNNING')").fetchall()
                for identity, body in rows:
                    report = json.loads(body)
                    report.update(status="INTERRUPTED", updated_at=now())
                    report["gaps"] = [{"task_id": "", "name": "Runtime", "reason": "Backend stopped before this report was completed."}]
                    connection.execute("UPDATE reports SET status=?, body=? WHERE id=?", ("INTERRUPTED", json.dumps(report), identity))
        finally:
            connection.close()