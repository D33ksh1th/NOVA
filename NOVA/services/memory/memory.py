"""
Memory Service

Public interface for NOVA Memory.
"""

from services.memory.repository import MemoryRepository


class Memory:
    """Main Memory Service."""

    def __init__(self):
        self.repository = MemoryRepository()

    def remember(self, key: str, value: str) -> bool:
        return self.repository.save(key, value)

    def recall(self, key: str):
        return self.repository.get(key)

    def recall_all(self):
        return self.repository.get_all()