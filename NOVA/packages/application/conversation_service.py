"""
Conversation Application Service

Coordinates Brain, Memory, Planner and future services.
"""

from packages.common import logger
from services.games.developer_quiz import DeveloperQuiz


class ConversationService:

    def __init__(self, brain, initiative_engine=None, agent_runtime=None):
        self.brain = brain
        self.initiative_engine = initiative_engine
        self.agent_runtime = agent_runtime
        self.game = DeveloperQuiz()

    def handle(self, message: str):
        game_result = self.game.handle(message)
        if game_result is not None:
            return game_result
        if self.agent_runtime is not None:
            agent_result = self.agent_runtime.handle(message)
            if agent_result is not None:
                return agent_result
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