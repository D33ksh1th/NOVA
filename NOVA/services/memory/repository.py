"""
Memory Repository
"""

from packages.common import logger

from services.memory.database import get_session
from services.memory.models import MemoryModel


class MemoryRepository:

    def __init__(self):
        logger.info("Memory Repository Initialized")

    def save(self, key: str, value: str):

        session = get_session()

        try:

            memory = (
                session.query(MemoryModel)
                .filter_by(key=key)
                .first()
            )

            if memory:

                memory.value = value

            else:

                memory = MemoryModel(
                    key=key,
                    value=value
                )

                session.add(memory)

            session.commit()

            return True

        finally:

            session.close()

    def get(self, key: str):

        session = get_session()

        try:

            memory = (
                session.query(MemoryModel)
                .filter_by(key=key)
                .first()
            )

            if memory:
                return memory.value

            return None

        finally:

            session.close()
            
    def get_all(self):

        session = get_session()

        try:

            memories = session.query(MemoryModel).all()

            return memories

        finally:

            session.close()