"""
Knowledge Manager
"""

from services.knowledge.sources.memory import MemoryKnowledgeSource
from services.knowledge.retrieval.retriever import KnowledgeRetriever
from services.knowledge.retrieval.ranking import KnowledgeRanker


class KnowledgeManager:

    def __init__(self, memory):

        self.memory = MemoryKnowledgeSource(memory)

        self.retriever = KnowledgeRetriever()

        self.ranker = KnowledgeRanker()

    def collect(self, query: str):

        knowledge = []

        knowledge.extend(
            self.memory.search(query)
        )

        retrieved = self.retriever.retrieve(
            query,
            knowledge
        )

        ranked = self.ranker.rank(
            retrieved
        )

        return ranked