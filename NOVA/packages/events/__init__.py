from .persistent_bus import PersistentEventBus
from .events import Event
from .envelope import EventEnvelope

# Singleton — all modules share this instance
bus = PersistentEventBus()

__all__ = ["bus", "Event", "EventEnvelope", "PersistentEventBus"]