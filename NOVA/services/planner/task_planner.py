"""
Chain-of-Thought Task Planner

Breaks a user's goal into an ordered list of sub-tasks,
then executes each one through the LLM and combines the
results into a single structured response.

Flow
----
  User Goal
      ↓
  TaskPlanner.plan()        ← asks LLM to decompose the goal
      ↓
  List[PlannedTask]         ← ordered sub-tasks with tool hints
      ↓
  PlanExecutor.execute()    ← runs each task through LLM / tools
      ↓
  PlanResult                ← combined answer + execution trace
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional
from uuid import uuid4

from packages.common import logger


# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PlannedTask:
    """A single step inside an execution plan."""
    id: str = field(default_factory=lambda: str(uuid4())[:8])
    index: int = 0
    description: str = ""
    tool: Optional[str] = None          # e.g. "llm", "web", "terminal", "pdf_reader"
    depends_on: List[str] = field(default_factory=list)
    result: Optional[str] = None
    completed: bool = False


@dataclass
class ExecutionPlan:
    """A decomposed plan for a user goal."""
    goal: str
    tasks: List[PlannedTask]
    plan_id: str = field(default_factory=lambda: str(uuid4())[:12])

    def is_simple(self) -> bool:
        return len(self.tasks) == 1

    def task_count(self) -> int:
        return len(self.tasks)

    def summary(self) -> List[str]:
        return [t.description for t in self.tasks]


@dataclass
class PlanResult:
    """Final output after all tasks are executed."""
    goal: str
    plan_id: str
    tasks_executed: int
    response: str
    steps: List[dict] = field(default_factory=list)
    is_simple: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Complexity classifier  (no LLM call — pure heuristic, fast)
# ─────────────────────────────────────────────────────────────────────────────

_SIMPLE_PATTERNS = re.compile(
    r"^(what|who|when|where|why|how (much|many|long|old)|is |are |"
    r"tell me|explain briefly|define |meaning of|difference between|"
    r"what is|what are|show me|list )",
    re.IGNORECASE,
)

_COMPLEX_KEYWORDS = [
    "build", "create", "implement", "develop", "write", "design",
    "teach me", "explain.*from scratch", "step.by.step", "tutorial",
    "full.*course", "complete guide", "end.to.end", "project",
    "application", "system", "architecture", "roadmap", "plan",
    "how to make", "how to build", "help me learn", "walk me through",
]

_COMPLEX_RE = re.compile("|".join(_COMPLEX_KEYWORDS), re.IGNORECASE)


def _estimate_complexity(goal: str) -> str:
    """Return 'simple' or 'complex' without calling the LLM."""
    if _SIMPLE_PATTERNS.match(goal.strip()):
        return "simple"
    if _COMPLEX_RE.search(goal):
        return "complex"
    # Word-count heuristic: long sentences are often complex
    if len(goal.split()) > 10:
        return "complex"
    return "simple"


# ─────────────────────────────────────────────────────────────────────────────
# LLM-based decomposer
# ─────────────────────────────────────────────────────────────────────────────

_DECOMPOSE_PROMPT = """You are a task planning assistant.

The user wants to accomplish the following goal:

GOAL: {goal}

Break this goal into an ordered list of concrete sub-tasks.
Each sub-task should be self-contained and executable one at a time.

Rules:
- Simple goals (one factual question) → return exactly 1 task.
- Medium goals (e.g. "explain X") → 2–4 tasks.
- Complex goals (e.g. "build a full application") → 4–8 tasks maximum.
- Never exceed 8 tasks.
- Tasks must be logical and sequential.
- Use short, action-oriented descriptions (e.g. "Set up project structure").

Respond ONLY with a valid JSON array of strings. No explanation. No markdown.

Example output for "Build a REST API with authentication":
["Create project structure", "Design database schema", "Implement authentication", "Create middleware", "Implement routes", "Write tests"]

Example output for "What is Python?":
["Explain what Python is and its main use cases"]

Your JSON array:"""


class TaskPlanner:
    """
    Decomposes a user goal into an ordered list of sub-tasks using the LLM.

    Usage:
        planner = TaskPlanner(model_manager)
        plan = planner.plan("Build a weather app with FastAPI")
        # plan.tasks → [PlannedTask(...), PlannedTask(...), ...]
    """

    def __init__(self, model_manager):
        self._model = model_manager
        logger.info("TaskPlanner initialized")

    def plan(self, goal: str) -> ExecutionPlan:
        """Decompose a goal into an ExecutionPlan."""
        logger.info(f"TaskPlanner → planning: {goal!r}")

        complexity = _estimate_complexity(goal)
        logger.info(f"TaskPlanner → complexity estimate: {complexity}")

        if complexity == "simple":
            tasks = [PlannedTask(index=0, description=goal, tool="llm")]
            logger.info("TaskPlanner → single-task plan (simple goal)")
        else:
            tasks = self._decompose_via_llm(goal)

        plan = ExecutionPlan(goal=goal, tasks=tasks)
        logger.info(
            f"TaskPlanner → plan ready: {plan.plan_id} | {plan.task_count()} tasks"
        )
        for i, t in enumerate(plan.tasks):
            logger.info(f"  [{i+1}] {t.description}")

        return plan

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _decompose_via_llm(self, goal: str) -> List[PlannedTask]:
        """Call the LLM to break the goal into sub-tasks."""
        prompt = _DECOMPOSE_PROMPT.format(goal=goal)
        response = self._model.generate(message=goal, prompt=prompt)

        # model_manager returns LLMResponse(text=...) or a dict
        raw_text = response.text if hasattr(response, "text") else str(response)

        steps = self._parse_task_list(raw_text)

        if not steps:
            logger.warning("TaskPlanner → LLM returned no parseable tasks; falling back")
            steps = [goal]

        # Cap at 8 tasks
        steps = steps[:8]

        return [
            PlannedTask(index=i, description=step, tool="llm")
            for i, step in enumerate(steps)
        ]

    @staticmethod
    def _parse_task_list(raw: str) -> List[str]:
        """Extract a JSON array of strings from LLM output."""
        # Strip <think> blocks if present
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)

        # Try to find a JSON array anywhere in the text
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, list):
                    return [str(item).strip() for item in data if str(item).strip()]
            except json.JSONDecodeError:
                pass

        # Fallback: numbered list  "1. Do X"
        lines = re.findall(r"^\s*\d+[\.\)]\s*(.+)$", raw, re.MULTILINE)
        if lines:
            return [l.strip() for l in lines]

        # Fallback: bullet list  "- Do X"
        lines = re.findall(r"^\s*[-•*]\s*(.+)$", raw, re.MULTILINE)
        if lines:
            return [l.strip() for l in lines]

        return []
