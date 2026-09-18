"""Bounded public HTTPS retrieval with DNS pinning and robots enforcement."""

from __future__ import annotations

import asyncio
import socket
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from lxml import html

from services.agent_runtime.policy.url_policy import UrlPolicy, check_ip, check_url
from services.tools.base import Tool, ToolResult


MAX_BYTES = 524288
MAX_TEXT = 3000
USER_AGENT = "NOVAResearchBot"


def extract_page(content: bytes) -> dict:
    document = html.fromstring(content, parser=html.HTMLParser(no_network=True))
    title = " ".join(document.xpath("//title/text()"))[:200]
    for element in document.xpath("//script|//style|//nav|//header|//footer|//aside|//form|//noscript|//template"):
        element.drop_tree()
    main = document.xpath("//main|//article")
    text = " ".join((main[0] if main else document).text_content().split())
    return {"title": " ".join(title.split()), "text": text[:MAX_TEXT], "truncated": len(text) > MAX_TEXT}


class WebPageTool(Tool):
    SUPPORTS_STRUCTURED_ARGS = True
    PROVIDES_CAPABILITIES = frozenset({"web.read", "net.egress"})
    USES_URL_POLICY = True
    ARG_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["url"],
                  "properties": {"url": {"type": "string", "minLength": 1, "maxLength": 2048}}}

    @property
    def name(self):
        return "web_page"

    def can_handle(self, message):
        return False

    def execute(self, message):
        return {"success": False, "response": "Page reads require a governed research task."}

    async def _resolve(self, hostname):
        records = await asyncio.to_thread(socket.getaddrinfo, hostname, 443, type=socket.SOCK_STREAM)
        return list(dict.fromkeys(record[4][0] for record in records))

    @staticmethod
    def _host(url):
        if not isinstance(url, str) or len(url) > 2048 or "\\" in url or any(ord(char) <= 32 for char in url):
            raise ValueError("PAGE_URL_DENIED")
        parts = urlsplit(url)
        host = parts.hostname or ""
        policy = UrlPolicy(allow_domains=frozenset({host}), allowed_schemes=frozenset({"https"}))
        if parts.port not in {None, 443} or not check_url(url, policy).allowed:
            raise ValueError("PAGE_URL_DENIED")
        return host

    async def _request(self, client, url, *, robots=False):
        host = self._host(url)
        addresses = await self._resolve(host)
        if not addresses or any(not check_ip(address).allowed for address in addresses):
            raise ValueError("PAGE_ADDRESS_DENIED")
        original = httpx.URL(url)
        pinned = original.copy_with(host=addresses[0])
        client.cookies.clear()
        async with client.stream("GET", pinned, headers={"Host": original.netloc.decode("ascii"),
                "User-Agent": USER_AGENT, "Accept-Encoding": "identity",
                "Accept": "text/plain" if robots else "text/html,application/xhtml+xml"},
                extensions={"sni_hostname": host}) as response:
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise ValueError("PAGE_ENCODING_DENIED")
            content = bytearray()
            if response.status_code == 200:
                mime = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if not robots and mime not in {"text/html", "application/xhtml+xml"}:
                    raise ValueError("PAGE_TYPE_DENIED")
                limit = 65536 if robots else MAX_BYTES
                if int(response.headers.get("content-length", "0")) > limit:
                    raise ValueError("PAGE_TOO_LARGE")
                async for chunk in response.aiter_raw():
                    if len(content) + len(chunk) > limit:
                        raise ValueError("PAGE_TOO_LARGE")
                    content.extend(chunk)
            return response.status_code, response.headers.get("location"), bytes(content)

    async def invoke(self, *, url):
        try:
            async with asyncio.timeout(12):
                return await self._read(url)
        except asyncio.CancelledError:
            raise
        except Exception:
            return ToolResult(ok=False, error="PAGE_UNAVAILABLE_OR_DENIED")

    async def _read(self, url):
        host = self._host(url)
        original = urldefrag(url)[0]
        robots_url = f"https://{host}/robots.txt"
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=5) as client:
            status, _, content = await self._request(client, robots_url, robots=True)
            policy = RobotFileParser()
            if status == 404:
                policy.parse([])
            elif status == 200:
                policy.parse(content.decode("utf-8", errors="replace").splitlines())
            else:
                raise ValueError("ROBOTS_UNAVAILABLE")
            if policy.crawl_delay(USER_AGENT) or policy.request_rate(USER_AGENT):
                raise ValueError("ROBOTS_RATE_REQUIRES_SCHEDULER")
            current, visited = original, set()
            for redirect in range(4):
                if self._host(current) != host or current in visited or not policy.can_fetch(USER_AGENT, current):
                    raise ValueError("PAGE_SCOPE_DENIED")
                visited.add(current)
                status, location, content = await self._request(client, current)
                if status in {301, 302, 303, 307, 308} and location and redirect < 3:
                    current = urldefrag(urljoin(current, location))[0]
                    continue
                if status != 200:
                    raise ValueError("PAGE_HTTP_FAILURE")
                page = await asyncio.to_thread(extract_page, content)
                if not page["text"]:
                    raise ValueError("PAGE_EMPTY")
                return ToolResult(ok=True, data={"page": {**page, "url": current,
                    "requested_url": original, "bytes": len(content)}})
        raise ValueError("PAGE_REDIRECT_LIMIT")