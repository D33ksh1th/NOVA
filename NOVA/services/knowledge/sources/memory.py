"""
Memory Knowledge Source
"""

from services.knowledge.models import (
    Knowledge,
    KnowledgeSource,
)


class MemoryKnowledgeSource:

    def __init__(self, memory):

        self.memory = memory

    def search(self, query: str):

        knowledge = []

        keys = [
            "name",
            "birthday",
            "city",
            "company",
            "profession",
            "favorite_language",
            "favorite_colour",
        ]

        query = query.lower()

        for key in keys:

            value = self.memory.recall(key)

            if value:

                knowledge.append(

                    Knowledge(

                        source=KnowledgeSource.MEMORY,

                        title=key,

                        content=value,

                        score=1.0,
                    )

                )

        return knowledge