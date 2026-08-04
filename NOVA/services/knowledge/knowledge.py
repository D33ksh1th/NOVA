"""
Knowledge Service
"""

from services.knowledge.manager import (
    KnowledgeManager,
)


class KnowledgeService:

    def __init__(self, memory):

        self.manager = KnowledgeManager(
            memory
        )

    def search(self, query):

        return self.manager.collect(query)