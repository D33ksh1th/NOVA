"""
Planner Service

Responsible for:
- Goal Planning
- Task Management
- Runtime Decision Making
- Chain-of-Thought Task Planning (TaskPlanner + PlanExecutor)
"""

from packages.common import logger

from services.planner.tasks import TaskManager
from services.planner.decision import DecisionEngine
from services.planner.runtime import RuntimeEngine
from services.planner.prompt_builder import PromptBuilder
from services.planner.task_planner import TaskPlanner
from services.planner.executor import PlanExecutor


class Planner:

    def __init__(
        self,
        tool_registry=None,
        model_manager=None,
    ):

        self.tasks = TaskManager()

        self.decision = DecisionEngine()

        self.runtime = RuntimeEngine(
            tool_registry
        )

        self.prompt_builder = PromptBuilder()

        # Chain-of-Thought planning (optional — needs model_manager)
        self._model_manager = model_manager
        self.task_planner: TaskPlanner | None = None
        self.plan_executor: PlanExecutor | None = None

        if model_manager is not None:
            self.task_planner = TaskPlanner(model_manager)
            self.plan_executor = PlanExecutor(model_manager)

        logger.info("Planner Initialized")

    # ---------------------------------------------------
    # Goal Planning
    # ---------------------------------------------------

    def create_goal(self, goal: str):

        logger.info(f"New Goal -> {goal}")

        self.tasks.add_task(goal)

        return {

            "goal": goal,

            "status": "created"

        }

    def list_tasks(self):

        return self.tasks.list_tasks()

    # ---------------------------------------------------
    # Runtime Planning
    # ---------------------------------------------------

    def decide(self, message: str):

        logger.info(
            f"Planning Request -> {message}"
        )

        return self.decision.decide(
            message
        )

    def execute(self, message: str):

        decision = self.decide(
            message
        )

        logger.info(
            f"Planner Decision -> {decision}"
        )

        return self.runtime.execute(
            decision,
            message,
        )