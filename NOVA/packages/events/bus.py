"""
Simple Event Bus

This module allows services to communicate
without directly depending on each other.
"""

from collections import defaultdict
from typing import Callable, Dict, List

from packages.common import logger


class EventBus:

    def __init__(self):

        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)

    def subscribe(self, event: str, callback: Callable):

        self._subscribers[event].append(callback)

        logger.info(f"Subscribed -> {event}")

    def publish(self, event: str, data=None):

        logger.info(f"Publishing -> {event}")

        callbacks = self._subscribers.get(event, [])

        for callback in callbacks:

            callback(data)


bus = EventBus()