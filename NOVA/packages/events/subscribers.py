"""
Register core application subscribers.
"""

from packages.common import logger
from packages.events import bus, Event


def startup_listener(envelope):
    logger.info("Application Started", event_id=envelope.id)


def security_listener(envelope):
    logger.info(
        f"Security event: {envelope.type}",
        severity=envelope.severity,
        source=envelope.source,
    )


bus.subscribe(Event.APP_STARTED, startup_listener)
bus.subscribe("nova.security.>", security_listener)