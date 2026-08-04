"""
Memory Retriever

Responsible for finding relevant memories
based on the user's message.
"""

from packages.common import logger


class MemoryRetriever:

    def __init__(self, memory):

        logger.info("Memory Retriever Initialized")

        self.memory = memory
    
    

    def search(self, message: str):

        text = message.lower()

        # ----------------------------
        # All Memories
        # ----------------------------

        if any(
            phrase in text
            for phrase in [
                "what do you know about me",
                "what do you remember about me",
                "tell me about me",
                "everything you know about me",
            ]
        ):

            memories = self.memory.recall_all()

            if not memories:
                return None

            return "\n".join(
                f"{memory.key}: {memory.value}"
                for memory in memories
            )

        # ----------------------------
        # Personal Information
        # ----------------------------

        if any(word in text for word in [
            "my name",
            "what is my name",
            "what's my name",
            "who am i",
        ]):
            return self.memory.recall("name")

        if any(word in text for word in [
            "where do i live",
            "my city",
            "my location",
        ]):
            return self.memory.recall("city")

            
        if any(word in text for word in [
            "birth year",
            "what is my birth year",
            "what's my birth year",
            "when was i born",
        ]):
            return self.memory.recall("birth_year")

        if any(word in text for word in [
            "favorite language",
            "favourite language",
            "preferred language",
        ]):
            return self.memory.recall("language")

        

        # No relevant memory
        return None