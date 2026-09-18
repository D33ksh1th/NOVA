from __future__ import annotations

from .base import BaseSecurityCollector


class IdentityGuardianCollector(BaseSecurityCollector):
    name = "identity_guardian"
    description = "Phase 3 identity collector for account changes, login anomalies, MFA gaps, and session abuse signals."
    coverage = [
        "login_events",
        "mfa_state",
        "credential_changes",
        "session_anomalies",
    ]
