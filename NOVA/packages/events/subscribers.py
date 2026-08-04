"""
Register all application subscribers here.

Later every module will register itself.
"""

from packages.common import logger
from packages.events.bus import bus
from packages.events.events import Event


def startup_listener(data):

    logger.info("Application Started")


bus.subscribe(Event.APP_STARTED, startup_listener)