"""
NOVA Logger

Central logging service.

Every module should import logger from here.
"""

import logging
import sys


class Logger:

    def _format(self, message: str, **fields) -> str:

        if not fields:
            return message

        kv = " ".join(f"{key}={repr(value)}" for key, value in fields.items())
        return f"{message} | {kv}"

    def __init__(self):

        self.logger = logging.getLogger("NOVA")

        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:

            handler = logging.StreamHandler(sys.stdout)

            formatter = logging.Formatter(
                "[%(asctime)s] %(levelname)-8s %(message)s",
                "%H:%M:%S"
            )

            handler.setFormatter(formatter)

            self.logger.addHandler(handler)

    def info(self, message: str, **fields):

        self.logger.info(self._format(message, **fields))

    def warning(self, message: str, **fields):

        self.logger.warning(self._format(message, **fields))

    def error(self, message: str, **fields):

        self.logger.error(self._format(message, **fields))

    def debug(self, message: str, **fields):

        self.logger.debug(self._format(message, **fields))


logger = Logger()