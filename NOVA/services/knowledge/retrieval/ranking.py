"""
Knowledge Ranking
"""

from services.knowledge.models import Knowledge


class KnowledgeRanker:

    def rank(self, knowledge: list[Knowledge]):

        return sorted(
            knowledge,
            key=lambda item: item.score,
            reverse=True,
        )