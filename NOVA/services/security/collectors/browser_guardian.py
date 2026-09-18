from __future__ import annotations

from .base import BaseSecurityCollector


class BrowserGuardianCollector(BaseSecurityCollector):
    name = "browser_guardian"
    description = "Phase 2 browser security collector for URLs, redirects, certificates, downloads, and prompt-injection cues."
    coverage = [
        "urls",
        "redirect_chains",
        "certificates",
        "downloads",
        "login_forms",
        "clipboard_access",
        "prompt_injection",
    ]
