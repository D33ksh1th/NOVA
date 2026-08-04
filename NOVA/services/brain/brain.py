"""
Brain Service

Public interface for NOVA Brain.
"""

from services.brain.engine import BrainEngine


class Brain:

    def __init__(
        self,
        memory,
        planner,
        llm,
        knowledge,
        container,
        model_manager,
        tool_manager,
        agent_manager,
        reflection_engine=None,
    ):

        self.engine = BrainEngine(
            memory=memory,
            planner=planner,
            llm=llm,
            knowledge=knowledge,
            container=container,
            model_manager=model_manager,
            tool_manager=tool_manager,
            agent_manager=agent_manager,
            reflection_engine=reflection_engine,
        )

    def process(self, message: str):
        return self.engine.process(message)

    @property
    def conversation(self):
        return self.engine.conversation