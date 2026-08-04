"""
Memory Manager

Provides a high-level interface for storing
and retrieving memories.
"""

from packages.common import logger


class MemoryManager:

    def __init__(self, memory):

        logger.info("Memory Manager Initialized")

        self.memory = memory

    # ----------------------------
    # Store
    # ----------------------------

    def remember(self, key: str, value: str):

        return self.memory.remember(
            key,
            value,
        )

    # ----------------------------
    # Recall
    # ----------------------------

    def recall(self, key: str):

        return self.memory.recall(key)

    # ----------------------------
    # Recall All
    # ----------------------------

    def recall_all(self):

        return self.memory.recall_all()

    # ----------------------------
    # Search
    # ----------------------------

    def search(self, message: str):

        text = message.lower()

        memory_map = {

            "name": [
                "name",
                "who am i",
            ],

            "birth_year": [
                "birth year",
                "born",
            ],

            "birthday": [
                "birthday",
            ],

            "city": [
                "city",
                "where do i live",
                "location",
            ],

            "favorite_language": [
                "language",
                "programming language",
            ],

            "vehicle": [
                "bike",
                "car",
                "vehicle",
            ],

        }

        # Return all memories

        if any(
            phrase in text
            for phrase in [

                "what do you know about me",

                "what do you remember about me",

                "tell me about me",

                "everything you know about me",

            ]
        ):

            memories = self.recall_all()

            if not memories:
                return None

            return "\n".join(
                f"{memory.key}: {memory.value}"
                for memory in memories
            )

        # Find matching key

        for key, phrases in memory_map.items():

            if any(
                phrase in text
                for phrase in phrases
            ):

                return self.recall(key)

        return None