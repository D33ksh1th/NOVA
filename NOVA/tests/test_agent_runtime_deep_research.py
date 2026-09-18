import asyncio

from services.agent_runtime.agents.research_agent import research_queries
from services.agent_runtime.service import research_plan
from services.agent_runtime.reports import finish_report, new_report
from services.tools.base import ToolResult
from test_agent_runtime_phase1 import FakeLLM, _URL_RESULTS, build_manager, offline_gate


def test_distinct_bounded_search_angles():
    queries = [query for role in ("scout", "atlas", "prism") for query in research_queries("local speech models", role)]
    assert len(queries) == len(set(queries)) == 11
    assert all(len(query) <= 512 for query in research_queries("topic " * 100, "scout"))
    assert research_queries("one query", "") == ["one query"]


def test_research_model_receives_exact_question_and_relevance_rules(offline_gate):
    class CapturingModel(FakeLLM):
        async def complete(self, **kwargs):
            assert "Omit loosely related content" in kwargs["system"]
            assert "Never merge similarly named people" in kwargs["system"]
            return await super().complete(**kwargs)

    async def scenario():
        model = CapturingModel()
        manager, *_ = build_manager(_URL_RESULTS, model, offline_gate)
        question = "Which Piper releases support offline speech on macOS?"
        try:
            result = await manager.run_task(question, "research", {"query": question})
            assert str(result.status) == "SUCCESS"
            assert 'source="user:objective"' in model.seen_content
            assert question in model.seen_content
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_discovery_uses_multiple_broker_searches(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager(_URL_RESULTS, FakeLLM(), offline_gate)
        tool = registry.resolve_tool("web_search_tool")
        queries = []
        original = tool.invoke

        async def search(query, max_results=5, relevance_query=None):
            queries.append(query)
            return await original(query, max_results)

        tool.invoke = search
        result = await manager.run_task("speech models", "research", {"query": "speech models", "research_role": "scout"})
        assert str(result.status) == "SUCCESS"
        assert queries == research_queries("speech models", "scout")
        assert audit.verify()

    asyncio.run(scenario())


def test_highlights_only_publish_citation_accepted_prism_findings(offline_gate):
    class ComparisonModel(FakeLLM):
        async def complete(self, **kwargs):
            output = await super().complete(**kwargs)
            output["claims"][0].update(category="tradeoff", subject="Deployment", priority="high")
            return output

    async def scenario():
        manager, *_ = build_manager(_URL_RESULTS, ComparisonModel(), offline_gate)
        result = await manager.run_graph(research_plan("speech models"))
        report = finish_report(new_report("deep-test", "speech models"), result)
        assert len(report["coverage"]["searches"]) == 11
        assert report["coverage"]["cited_domains"] == 1
        assert sum(search["reviewed_sources"] for search in report["coverage"]["searches"]) == 6
        assert report["key_takeaways"][0]["category"] == "tradeoff"
        assert report["key_takeaways"][0]["subject"] == "Deployment"
        assert report["key_takeaways"][0]["source_ids"]
        result.gaps["prism"] = "FABRICATED_EVIDENCE"
        rejected = finish_report(new_report("rejected", "speech models"), result)
        assert rejected["key_takeaways"] == []
        await manager.close()

    asyncio.run(scenario())


def test_one_query_failure_is_partial_not_a_complete_research_claim(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager(_URL_RESULTS, FakeLLM(), offline_gate)
        tool = registry.resolve_tool("web_search_tool")
        original = tool.invoke

        async def search(query, max_results=5, relevance_query=None):
            if "official sources" in query:
                return ToolResult(ok=False, error="provider unavailable")
            return await original(query, max_results)

        tool.invoke = search
        result = await manager.run_task("models", "research", {"query": "models", "research_role": "scout"})
        assert str(result.status) == "PARTIAL"
        assert [search["status"] for search in result.payload["searches"]] == ["OK", "FAILED", "OK"]
        assert result.evidence
        await manager.close()

    asyncio.run(scenario())


def test_deep_graph_compares_both_parents_with_owned_evidence(offline_gate):
    async def scenario():
        model = FakeLLM()
        manager, audit, ledger, broker, registry = build_manager(_URL_RESULTS, model, offline_gate)
        plan = research_plan("speech models")
        assert plan.budget.max_tool_calls == 11
        result = await manager.run_graph(plan)
        assert result.status == "COMPLETED"
        assert len(result.results["scout"].payload["searches"]) == 3
        assert len(result.results["atlas"].payload["searches"]) == 3
        assert len(result.results["prism"].payload["searches"]) == 5
        assert "Piper is a fast local TTS." in model.seen_content
        assert all(evidence.task_id == result.results["prism"].task_id for evidence in result.results["prism"].evidence)
        assert audit.verify()
        await manager.close()

    asyncio.run(scenario())


def test_non_comparison_questions_do_not_get_comparison_searches():
    for role in ("scout", "atlas", "prism"):
        queries = research_queries('"Alex Smith" professional publications', role)
        assert all('"Alex Smith"' in query for query in queries)
        assert not any("comparison" in query or "benchmarks" in query for query in queries)
    assert any("comparison" in query for query in research_queries("compare Piper versus Kokoro", "atlas"))


def test_failed_scout_does_not_cancel_independent_atlas(offline_gate):
    from services.agent_runtime.contracts.model_usage import ModelResponseError

    class FailingScout(FakeLLM):
        async def complete(self, **kwargs):
            if "You are Scout" in kwargs["system"]:
                raise ModelResponseError("MODEL_USAGE_UNAVAILABLE")
            await asyncio.sleep(0)
            return await super().complete(**kwargs)

    async def scenario():
        manager, audit, *_ = build_manager(_URL_RESULTS, FailingScout(), offline_gate)
        try:
            result = await manager.run_graph(research_plan("speech models"))
            assert result.status == "FAILED"
            assert str(result.results["atlas"].status) == "SUCCESS"
            assert next(node for node in result.nodes if node.id == "prism").state == "SKIPPED"
            report = finish_report(new_report("independent", "speech models"), result)
            assert report["findings"] and all(finding["task_id"] == "atlas" for finding in report["findings"])
            assert audit.verify()
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_no_relevant_claims_is_partial(offline_gate):
    class NoRelevantClaims(FakeLLM):
        async def complete(self, **kwargs):
            return {"summary": "No relevant evidence", "claims": []}

    async def scenario():
        manager, *_ = build_manager(_URL_RESULTS, NoRelevantClaims(), offline_gate)
        try:
            result = await manager.run_task("exact question", "research")
            assert str(result.status) == "PARTIAL"
            assert result.payload["claims"] == [] and result.evidence == []
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_invalid_schema_fails_without_unbudgeted_retry_or_raw_output(offline_gate):
    class InvalidSchema(FakeLLM):
        async def complete(self, **kwargs):
            self.calls += 1
            return {"summary": "private model output", "claims": [{"text": "private text", "evidence_ids": []}]}

    async def scenario():
        model = InvalidSchema()
        manager, audit, *_ = build_manager(_URL_RESULTS, model, offline_gate)
        try:
            result = await manager.run_graph(research_plan("speech models"))
            assert model.calls == 2
            assert all(task.errors == ["MODEL_SCHEMA_INVALID: 1 field error(s)"] for task in result.results.values())
            assert "private model output" not in audit.dump()
            assert "private text" not in str(result.results)
            assert result.cost.retries == 0
        finally:
            await manager.close()

    asyncio.run(scenario())