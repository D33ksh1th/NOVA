import asyncio
from unittest.mock import Mock, call
from types import SimpleNamespace

import pytest

from services.tools import web_search_tool
from services.agent_runtime.factory import build_runtime
from test_agent_runtime_phase1 import FakeLLM, offline_gate
from test_agent_runtime_service import attached_service
from services.agent_runtime.policy.relevance import relevance_score


def test_relevance_scores_rank_exact_partial_and_unrelated_matches():
    exact = relevance_score("Python 3.13 release", "Python 3.13 release", "Release notes")
    partial = relevance_score("Python 3.13 release", "Python release", "Language news")
    unrelated = relevance_score("Python 3.13 release", "Laptop review", "Hardware measurements")
    assert exact["score"] == 100
    assert 0 < partial["score"] <= 35
    assert unrelated["score"] == 0
    assert partial["missing_terms"] == ["13", "3"]


def test_relevance_does_not_reward_repetition_or_wrong_quoted_identity():
    assert relevance_score("Piper TTS", "Piper TTS", "Piper " * 100)["score"] == 100
    assert relevance_score('"Alex Smith"', "Alexis Smith", "Researcher")["score"] == 0
    assert relevance_score("the and", "the and")["score"] == 0
    assert relevance_score("Ｐｙｔｈｏｎ", "Python")["score"] == 100


def test_general_search_preserves_sources_and_filters_invalid_rows(monkeypatch):
    client = Mock()
    client.text.return_value = [
        {"title": "Laptop review", "href": "https://example.com/laptop", "body": "A review with measurements."},
        {"title": "Duplicate", "href": "https://example.com/laptop", "body": "duplicate"},
        {"title": "No link", "body": "No attributable source"},
        {"title": "Unsafe", "href": "javascript:alert(1)", "body": "not a URL"},
        {"title": "Credentials", "href": "https://user:pass@example.com/", "body": "not a source"},
        {"title": "Empty", "href": "https://example.com/empty", "body": " "},
        {"title": "Malformed", "href": "https://[", "body": "bad URL"},
    ]
    factory = Mock(return_value=client)
    monkeypatch.setattr(web_search_tool, "DDGS", factory)
    result = asyncio.run(web_search_tool.WebSearchTool().invoke("gaming laptops under 1500 USD"))
    assert all(call.kwargs == {"timeout": 8, "verify": True} for call in factory.call_args_list)
    assert {request.kwargs["backend"] for request in client.text.call_args_list} == {"duckduckgo", "bing", "brave", "google"}
    assert all(request.kwargs["max_results"] == 20 for request in client.text.call_args_list)
    assert result.ok
    assert result.data["results"] == [{"title": "Laptop review", "url": "https://example.com/laptop",
                                       "snippet": "A review with measurements.", "source": "web_search",
                                       "relevance": relevance_score("gaming laptops under 1500 USD", "Laptop review", "A review with measurements.")}]


def test_general_search_bounds_results_and_snippets(monkeypatch):
    client = Mock()
    client.text.return_value = [{"title": "x" * 400, "href": f"https://example.com/{index}", "body": "x" * 3000}
                               for index in range(10)]
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)
    result = asyncio.run(web_search_tool.WebSearchTool().invoke("topic", max_results=3))
    assert result.ok and result.data["truncated"]
    assert len(result.data["results"]) == 3
    assert len(result.data["results"][0]["snippet"]) == 1600
    assert len(result.data["results"][0]["title"]) == 200


def test_search_outage_is_not_an_empty_success(monkeypatch):
    client = Mock()
    client.text.side_effect = TimeoutError("Search provider timed out")
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)
    result = asyncio.run(web_search_tool.WebSearchTool().invoke("topic"))
    assert not result.ok


def test_images_retain_source_attribution_and_reject_local_urls(monkeypatch):
    client = Mock()
    client.images.return_value = [
        {"title": "Laptop", "url": "https://example.com/review", "thumbnail": "https://external-content.duckduckgo.com/laptop.jpg"},
        {"title": "Unsafe", "url": "https://example.com", "thumbnail": "https://127.0.0.1/private"},
        {"title": "Missing attribution", "thumbnail": "https://images.example.com/other.jpg"},
    ]
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)
    images = web_search_tool.WebSearchTool()._search_images("laptops", [{"url": "https://example.com/review", "title": "Laptop"}])
    assert images == [{"title": "Laptop", "url": "https://example.com/review", "image_url": "https://external-content.duckduckgo.com/laptop.jpg", "relevance": relevance_score("laptops", "Laptop")}]
    assert client.images.call_count == 2
    assert all(request.kwargs["max_results"] == 20 for request in client.images.call_args_list)


def test_images_fall_back_to_bing_without_accepting_arbitrary_hosts(monkeypatch):
    client = Mock()
    client.images.side_effect = [TimeoutError("unavailable"), [
        None,
        {"title": "Malformed", "url": "https://[", "thumbnail": "https://ts1.mm.bing.net/image"},
        {"title": "Untrusted", "url": "https://example.com", "thumbnail": "https://ts1.explicit.bing.net/image"},
        {"title": "Public profile", "url": "https://www.linkedin.com/in/example", "thumbnail": "https://ts1.mm.bing.net/image"},
    ]]
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)
    images = web_search_tool.WebSearchTool()._search_images("person employer", [{"url": "https://www.linkedin.com/in/example", "title": "Public profile"}])
    assert images == [{"title": "Public profile", "url": "https://www.linkedin.com/in/example", "image_url": "https://ts1.mm.bing.net/image", "relevance": relevance_score("person employer", "Public profile")}]
    assert client.images.call_args.kwargs["backend"] == "bing"


def test_image_failure_does_not_discard_text_sources(monkeypatch):
    client = Mock()
    client.text.return_value = [{"title": "Source", "href": "https://example.com", "body": "Supported text"}]
    client.images.side_effect = TimeoutError("Image search unavailable")
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)
    result = asyncio.run(web_search_tool.WebSearchTool().invoke("topic"))
    assert result.ok and result.data["results"] and result.data["images"] == []


def test_image_candidates_need_exact_source_page_and_matching_title(monkeypatch):
    client = Mock()
    client.text.return_value = [{"title": "NovaBook 14 review", "href": "https://example.com/review",
                                 "body": "NovaBook 14 specifications."}]
    client.images.return_value = [
        {"title": "NovaBook 14 review", "url": "https://other.test/review", "thumbnail": "https://ts1.mm.bing.net/other-site"},
        {"title": "NovaBook 14 review", "url": "https://example.com/another", "thumbnail": "https://ts1.mm.bing.net/other-page"},
        {"title": "Beach holiday", "url": "https://example.com/review", "thumbnail": "https://ts1.mm.bing.net/unrelated"},
        {"title": "NovaBook 16 review", "url": "https://example.com/review", "thumbnail": "https://ts1.mm.bing.net/wrong-model"},
        {"title": "NovaBook 14", "url": "https://example.com/review#photo", "thumbnail": "https://ts1.mm.bing.net/match"},
    ]
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)
    result = asyncio.run(web_search_tool.WebSearchTool().invoke("NovaBook 14"))
    assert result.data["images"] == [{"title": "NovaBook 14", "url": "https://example.com/review#photo",
                                      "image_url": "https://ts1.mm.bing.net/match", "relevance": relevance_score("NovaBook 14", "NovaBook 14")}]


def test_unrelated_images_are_empty_without_losing_text(monkeypatch):
    client = Mock()
    client.text.return_value = [{"title": "Alex Smith Example", "href": "https://example.com/alex", "body": "Research profile"}]
    client.images.return_value = [{"title": "Alexis Smith Example", "url": "https://example.com/alex",
                                   "thumbnail": "https://ts1.mm.bing.net/wrong-person"}]
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)
    result = asyncio.run(web_search_tool.WebSearchTool().invoke('"Alex Smith" Example'))
    assert result.ok and result.data["results"] and result.data["images"] == []
    assert client.images.call_count == 2


def test_image_search_does_not_run_without_text_sources(monkeypatch):
    client = Mock()
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)
    assert web_search_tool.WebSearchTool()._search_images("topic", []) == []
    client.images.assert_not_called()


def test_no_search_results_still_cannot_invent_sources(monkeypatch):
    client = Mock()
    client.text.return_value = []
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)
    result = asyncio.run(web_search_tool.WebSearchTool().invoke("topic"))
    assert result.ok and result.data["results"] == []


@pytest.mark.parametrize("provider_fails", [False, True])
def test_real_tool_flows_through_research_graph(monkeypatch, offline_gate, provider_fails):
    client = Mock()
    if provider_fails:
        client.text.side_effect = TimeoutError("Provider unavailable")
    else:
        client.text.return_value = [{"title": "Piper TTS", "href": "https://example.com/piper",
                                     "body": "Piper is a fast local TTS."}]
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)

    async def scenario():
        model = FakeLLM()
        manager = build_runtime(tool_registry=SimpleNamespace(all=lambda: [web_search_tool.WebSearchTool()]),
                                action_gate=offline_gate, llm=model)
        owner = attached_service(manager)
        owner.command("research", "local speech models")
        await asyncio.gather(*tuple(owner.jobs))
        reply = owner.command("results")["response"]
        if provider_fails:
            assert "retrieval failure" in reply and model.calls == 0
        else:
            assert "3 successful" in reply and model.calls == 3
            assert "Sources: https://example.com/piper" in reply
            assert client.text.call_count == 44
        await owner.close()

    asyncio.run(scenario())


def test_sources_are_interleaved_deduplicated_and_domain_diverse(monkeypatch):
    client = Mock()
    client.text.side_effect = [
        [{"title": "Vendor", "href": "https://vendor.test/product", "body": "Vendor statement"},
         {"title": "Vendor again", "href": "https://vendor.test/other", "body": "Another statement"}],
        [{"title": "Study", "href": "https://university.test/study", "body": "Independent measurement"},
         {"title": "Duplicate", "href": "https://vendor.test/product#section", "body": "Same page"},
         {"title": "Review", "href": "https://reviews.test/review", "body": "A comparison"}],
    ]
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)
    _, results = web_search_tool.WebSearchTool()._search_structured("topic")
    assert [result["url"] for result in results] == ["https://vendor.test/product", "https://university.test/study",
                                                   "https://reviews.test/review", "https://vendor.test/other"]


def test_one_text_provider_failure_keeps_other_sources(monkeypatch):
    client = Mock()
    client.text.side_effect = [TimeoutError(), [{"title": "Study", "href": "https://university.test/study", "body": "Evidence"}]]
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)
    _, results = web_search_tool.WebSearchTool()._search_structured("topic")
    assert len(results) == 1


def test_primary_outage_uses_bounded_alternate_provider(monkeypatch):
    client = Mock()
    client.text.side_effect = [TimeoutError(), [], [
        {"title": "Piper releases", "href": "https://example.com/releases", "body": "Offline speech on macOS"}
    ]]
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)
    _, results = web_search_tool.WebSearchTool()._search_structured("Piper releases")
    assert len(results) == 1
    assert {request.kwargs["backend"] for request in client.text.call_args_list} == {"duckduckgo", "bing", "brave", "google"}


def test_exact_topic_outranks_related_pages(monkeypatch):
    client = Mock()
    client.text.return_value = [
        {"title": "Speech technology", "href": "https://other.test/", "body": "General industry news"},
        {"title": "Piper macOS releases", "href": "https://project.test/", "body": "Piper offline speech releases"},
    ]
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)
    _, results = web_search_tool.WebSearchTool()._search_structured("Piper macOS releases")
    assert results[0]["url"] == "https://project.test/"


def test_quoted_entity_excludes_similarly_named_people(monkeypatch):
    client = Mock()
    client.text.return_value = [
        {"title": "Alex Smith", "href": "https://example.com/alex", "body": "Researcher at Example"},
        {"title": "Alexis Smith", "href": "https://example.com/alexis", "body": "Researcher at Example"},
    ]
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)
    _, results = web_search_tool.WebSearchTool()._search_structured('"Alex Smith" Example')
    assert [result["url"] for result in results] == ["https://example.com/alex"]


def test_broader_search_finds_best_match_in_later_provider_and_keeps_best_duplicate(monkeypatch):
    client = Mock()

    def text(query, backend, max_results):
        assert max_results == 20
        if backend == "google":
            return [{"title": "Piper TTS", "href": "https://example.com/shared#detail", "body": "Piper TTS"}]
        return [{"title": "General software", "href": "https://example.com/shared", "body": "Software news"},
                {"title": "Piper", "href": "https://example.com/partial", "body": "Speech"}]

    client.text.side_effect = text
    client.images.return_value = []
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)
    result = asyncio.run(web_search_tool.WebSearchTool().invoke("Piper TTS independent evidence", relevance_query="Piper TTS"))
    assert result.data["results"][0]["title"] == "Piper TTS"
    assert result.data["results"][0]["relevance"]["score"] == 100
    assert len(result.data["results"]) == 2
    assert result.data["coverage"]["pages_crawled"] == 0
    assert len(result.data["coverage"]["providers_requested"]) == 4


def test_images_rank_both_providers_before_selecting_top_three(monkeypatch):
    client = Mock()

    def images(query, backend, **kwargs):
        titles = ["Piper TTS", "Piper TTS installation", "Piper TTS news"] if backend == "duckduckgo" else ["Piper TTS macOS"]
        return [{"title": title, "url": "https://example.com/piper", "thumbnail": f"https://ts1.mm.bing.net/{backend}/{index}"}
                for index, title in enumerate(titles)]

    client.images.side_effect = images
    monkeypatch.setattr(web_search_tool, "DDGS", lambda **kwargs: client)
    images = web_search_tool.WebSearchTool()._search_images("Piper TTS macOS", [{"url": "https://example.com/piper", "title": "Piper TTS"}])
    assert len(images) == 3
    assert images[0]["title"] == "Piper TTS macOS" and images[0]["relevance"]["score"] == 100