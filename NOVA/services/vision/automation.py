"""Browser automation adapter (Playwright)."""

from __future__ import annotations

from dataclasses import dataclass

from packages.common import logger


@dataclass
class AutomationResult:
    success: bool
    response: str
    backend: str = "none"
    title: str = ""
    url: str = ""
    error: str = ""


class BrowserAutomationService:
    def open_and_describe(self, url: str, headless: bool = True) -> AutomationResult:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError:
            return AutomationResult(
                success=False,
                response="Playwright is not installed. Run: pip install playwright && playwright install chromium",
                backend="playwright",
                url=url,
                error="playwright missing",
            )

        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"https://{url}"

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=headless)
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                title = (page.title() or "").strip()
                final_url = page.url
                browser.close()

            msg = f"Opened {final_url}. Page title: {title or 'Untitled'}"
            return AutomationResult(success=True, response=msg, backend="playwright", title=title, url=final_url)
        except Exception as ex:
            logger.error(f"BrowserAutomationService error -> {ex}")
            return AutomationResult(
                success=False,
                response=f"Automation failed: {ex}",
                backend="playwright",
                url=url,
                error=str(ex),
            )

    def search_web(self, query: str, headless: bool = True) -> AutomationResult:
        if not query.strip():
            return AutomationResult(success=False, response="Provide a search query.", backend="playwright")
        safe_q = query.strip().replace(" ", "+")
        url = f"https://duckduckgo.com/?q={safe_q}"
        result = self.open_and_describe(url, headless=headless)
        if result.success:
            result.response = f"Searched web for '{query}'. {result.response}"
        return result
