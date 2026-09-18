"""
Web Search Tool

Legacy chat uses DuckDuckGo Instant Answers. Governed agents use regular
web search through DDGS with DuckDuckGo and Bing and attributable result URLs.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from itertools import zip_longest
import json
import re
import urllib.parse
import urllib.request
from typing import List

from ddgs import DDGS

from services.tools.base import Tool, ToolResult
from packages.common import logger
from services.agent_runtime.policy.url_policy import UrlPolicy, check_url
from services.agent_runtime.policy.image_policy import allowed_thumbnail, image_matches_source
from services.agent_runtime.policy.relevance import relevance_score

_INSTANT_URL = "https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"
_USER_AGENT = "Mozilla/5.0 (compatible; NOVA-AI/1.0)"
_TIMEOUT = 8


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


class WebSearchTool(Tool):

    # ── Agent-runtime metadata (broker-only; execute() path is unaffected) ──
    SUPPORTS_STRUCTURED_ARGS = True
    PROVIDES_CAPABILITIES = frozenset({"web.search"})
    ARG_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": ["query"],
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 512},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
            "relevance_query": {"type": "string", "minLength": 1, "maxLength": 512},
        },
    }

    @property
    def name(self) -> str:
        return "web_search"

    def can_handle(self, message: str) -> bool:
        text = message.lower()
        return any(k in text for k in [
            "search for", "search about", "look up", "google",
            "find online", "what is", "who is", "tell me about",
            "search the web", "find information",
        ])

    def execute(self, message: str) -> dict:
        query = self._extract_query(message)
        if not query:
            return {
                "action": "web_search",
                "success": False,
                "response": "I couldn't figure out what to search for.",
            }

        logger.info(f"WebSearchTool: searching '{query}'")
        try:
            answer, snippets = self._search(query)
        except Exception as ex:
            logger.warning(f"WebSearchTool: error: {ex}")
            return {
                "action": "web_search",
                "success": False,
                "response": f"Search failed: {ex}",
            }

        if answer:
            response = answer
        elif snippets:
            response = "Here's what I found: " + " — ".join(snippets[:3])
        else:
            response = f"I searched for '{query}' but couldn't find a clear answer. Try asking more specifically."

        return {
            "action": "web_search",
            "success": True,
            "query": query,
            "response": response,
        }

    # ── Helpers ──────────────────────────────────────────────────

    def _extract_query(self, message: str) -> str:
        patterns = [
            r"(?:search for|search about|look up|google|find online|search the web for)\s+(.+)",
            r"(?:tell me about|find information (?:on|about))\s+(.+)",
            r"(?:who|what) is\s+(.+)\??$",
        ]
        for pat in patterns:
            m = re.search(pat, message, re.IGNORECASE)
            if m:
                return _clean(m.group(1).rstrip("?").strip())
        # Fallback: strip leading command words and use rest
        cleaned = re.sub(
            r"(?i)^(nova[,\s]+)?(please\s+)?(search|google|look up|find)\s+",
            "", message
        ).strip()
        return _clean(cleaned) if cleaned else ""

    def _search(self, query: str):
        url = _INSTANT_URL.format(query=urllib.parse.quote_plus(query))
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # AbstractText = best single-sentence answer
        abstract = _clean(data.get("AbstractText") or "")
        answer_text = _clean(data.get("Answer") or "")
        definition = _clean(data.get("Definition") or "")

        best_answer = answer_text or abstract or definition

        # Related topics as fallback snippets
        snippets: List[str] = []
        for topic in (data.get("RelatedTopics") or [])[:5]:
            if isinstance(topic, dict):
                text = _clean(topic.get("Text") or "")
                if text:
                    snippets.append(text)

        return best_answer or None, snippets

    # ── Structured, broker-only entrypoint (Constitution I3/I16; 3D/4A) ──────

    async def invoke(self, query: str, max_results: int = 5, relevance_query: str | None = None) -> ToolResult:
        q = _clean(query)
        if not q:
            return ToolResult(ok=False, error="empty query")
        try:
            answer, results = await asyncio.to_thread(self._search_structured, q, relevance_query)
        except Exception as ex:  # network/parse failure is a result, not a crash
            logger.warning(f"WebSearchTool.invoke: {ex}")
            return ToolResult(ok=False, error=str(ex))

        truncated = len(results) > max_results
        candidates = len(results)
        results = results[:max_results]
        images = await asyncio.to_thread(self._search_images, q, results, relevance_query) if results else []
        if answer:
            response = answer
        elif results:
            response = "Here's what I found: " + " — ".join(r["snippet"] for r in results[:3] if r["snippet"])
        else:
            response = f"I searched for '{q}' but found no attributable sources."

        return ToolResult(ok=True, data={
            "query": q,
            "results": results,
            "response": response,
            "truncated": truncated,
            "images": images,
            "coverage": {"candidate_sources": candidates, "provider_limit": 20,
                         "providers_requested": ["duckduckgo", "bing", "brave", "google"],
                         "evidence_scope": "search_results", "pages_crawled": 0},
        })

    def _provider_batches(self, kind: str, query: str, backends: tuple[str, ...]) -> list[list[dict]]:
        def retrieve(backend):
            try:
                search = getattr(DDGS(timeout=_TIMEOUT, verify=True), kind)
                options = {"safesearch": "on"} if kind == "images" else {}
                return list(search(query, backend=backend, max_results=20, **options))[:20]
            except Exception as error:
                logger.warning(f"Search unavailable | kind={kind} provider={backend} error={type(error).__name__}")
                return None

        with ThreadPoolExecutor(max_workers=len(backends)) as executor:
            batches = list(executor.map(retrieve, backends))
        if kind == "text" and all(batch is None for batch in batches):
            raise RuntimeError("All search providers failed")
        return [batch or [] for batch in batches]

    def _search_images(self, query: str, sources: list[dict], relevance_query: str | None = None) -> list[dict]:
        if not sources:
            return []
        images = {}
        for rows in self._provider_batches("images", query, ("duckduckgo", "bing")):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                page, thumbnail, title = row.get("url"), row.get("thumbnail"), row.get("title")
                if not all(isinstance(value, str) for value in (page, thumbnail, title)):
                    continue
                try:
                    valid = (len(page) <= 2048 and len(thumbnail) <= 2048
                             and check_url(page, UrlPolicy(allow_domains=frozenset({urllib.parse.urlsplit(page).hostname or ""}))).allowed
                             and allowed_thumbnail(thumbnail)
                             and image_matches_source(page, title, sources, relevance_query or query))
                except ValueError:
                    continue
                if not valid:
                    continue
                relevance = relevance_score(relevance_query or query, _clean(title)[:200])
                if thumbnail not in images or relevance["score"] > images[thumbnail]["relevance"]["score"]:
                    images[thumbnail] = {"url": page, "image_url": thumbnail, "title": _clean(title)[:200],
                                         "relevance": relevance}
        return sorted(images.values(), key=lambda image: -image["relevance"]["score"])[:3]

    def _search_structured(self, query: str, relevance_query: str | None = None):
        """Preserve provider URLs; never infer citations from titles or model prose."""
        batches = self._provider_batches("text", query, ("duckduckgo", "bing", "brave", "google"))
        rows = [row for pair in zip_longest(*batches) for row in pair if row is not None]
        results = {}
        phrases = re.findall(r'"([^"\n]+)"', (relevance_query or query).casefold())
        for row in rows:
            if not isinstance(row, dict):
                continue
            url, title, snippet = row.get("href"), row.get("title"), row.get("body")
            if not all(isinstance(value, str) for value in (url, title, snippet)):
                continue
            try:
                parsed = urllib.parse.urlsplit(url)
                valid_url = parsed.scheme in {"https", "http"} and parsed.hostname and not parsed.username and not parsed.password
            except ValueError:
                continue
            identity = urllib.parse.urldefrag(url)[0]
            if not valid_url or len(url) > 2048 or not _clean(snippet):
                continue
            text = _clean(f"{title} {snippet}").casefold()
            if any(_clean(phrase) not in text for phrase in phrases):
                continue
            relevance = relevance_score(relevance_query or query, _clean(title)[:200], _clean(snippet)[:1600])
            if identity not in results or relevance["score"] > results[identity]["relevance"]["score"]:
                results[identity] = {"title": _clean(title)[:200], "url": url,
                                     "snippet": _clean(snippet)[:1600], "source": "web_search", "relevance": relevance}
        ranked = sorted(results.values(), key=lambda result: -result["relevance"]["score"])
        domains, ranks = {}, {}
        for result in ranked:
            domain = urllib.parse.urlsplit(result["url"]).hostname.removeprefix("www.")
            ranks[result["url"]] = domains.get(domain, 0)
            domains[domain] = ranks[result["url"]] + 1
        return None, sorted(ranked, key=lambda result: (-result["relevance"]["score"], ranks[result["url"]]))
