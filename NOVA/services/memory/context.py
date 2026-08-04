"""
Memory Context Builder
"""

from services.memory import Memory


class MemoryContext:

    def __init__(self, memory: Memory):
        self.memory = memory

    def build(self):

        memory = {}

        keys = [
            "name",
            "birthday",
            "city",
            "favorite_language",
            "favorite_colour",
            "company",
            "profession",
        ]

        for key in keys:

            value = self.memory.recall(key)

            if value:

                memory[key] = value

        return memory