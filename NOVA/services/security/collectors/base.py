from __future__ import annotations

from datetime import datetime, timezone

from services.security.types import SecurityCollectorStatus


class BaseSecurityCollector:
    name = "collector"
    description = ""
    coverage = []

    def status(self) -> SecurityCollectorStatus:
        return SecurityCollectorStatus(
            name=self.name,
            state="ready",
            description=self.description,
            coverage=list(self.coverage),
            last_heartbeat=datetime.now(timezone.utc).isoformat(),
        )
