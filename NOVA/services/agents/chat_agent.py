"""
Chat Agent
"""

from services.agents.base import Agent

from packages.common import logger


class ChatAgent(Agent):

    def __init__(
        self,
        container,
        knowledge,
        model_manager,
    ):

        self.container = container
        self.knowledge = knowledge
        self.model_manager = model_manager

    @property
    def name(self):

        return "chat"

    def can_handle(
        self,
        message,
        intent,
    ):

        # Fallback agent
        return True

    def execute(
        self,
        message,
        context,
    ):

        logger.info("Chat Agent Executing")

        system = self.container.system_context.build()

        location = self.container.location_context.build()

        weather = self.container.weather_context.build(
            location.get("latitude"),
            location.get("longitude"),
        )

        memory = self.container.memory_context.build()

        knowledge = self.knowledge.search(message)

        prompt = self.container.prompt_builder.build(
            user_message=message,
            system=system,
            location=location,
            weather=weather,
            memory=memory,
            context=context,
            knowledge=knowledge,
        )

        response = self.model_manager.generate(
            message=message,
            prompt=prompt,
        )

        return {
            "action": "chat",
            "response": response.text,
        }