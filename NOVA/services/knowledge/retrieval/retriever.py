"""
Knowledge Retriever
"""

from services.knowledge.models import Knowledge


class KnowledgeRetriever:

    def retrieve(self, query: str, knowledge: list[Knowledge]):

        query = query.lower()

        results = []

        for item in knowledge:

            title = item.title.lower()
            content = item.content.lower()

            if title in query or any(word in content for word in query.split()):
                results.append(item)

        return results