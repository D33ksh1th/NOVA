"""
Conversation Application Service

Coordinates Brain, Memory, Planner and future services.
"""

from packages.common import logger


class ConversationService:

    def __init__(self, brain, initiative_engine=None):
        self.brain = brain
        self.initiative_engine = initiative_engine

    def handle(self, message: str):
        logger.info(f"Conversation Started -> {message}")

        result = self.brain.process(message)

        if self.initiative_engine is None:
            return result

        initiative = self.initiative_engine.evaluate(
            message=message,
            brain_result=result if isinstance(result, dict) else {"response": str(result)},
            conversation_history=self._conversation_history(),
        )

        if initiative:
            if isinstance(result, dict):
                result = dict(result)
                result["initiative"] = initiative
                return result

            return {
                "response": str(result),
                "initiative": initiative,
            }

        return result

    def _conversation_history(self):
        conversation = getattr(self.brain, "conversation", None)
        if conversation is None:
            engine = getattr(self.brain, "engine", None)
            conversation = getattr(engine, "conversation", None) if engine is not None else None

        if conversation is None:
            return []

        try:
            return conversation.as_list()
        except Exception:
            return []