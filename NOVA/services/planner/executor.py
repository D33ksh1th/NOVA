"""
Plan Executor

Takes an ExecutionPlan produced by TaskPlanner and executes
each sub-task sequentially through the LLM (or tools).

Results from earlier tasks are fed as context into later tasks,
enabling genuine chain-of-thought execution.
"""

from __future__ import annotations

import re
from typing import Optional

from packages.common import logger
from services.planner.task_planner import ExecutionPlan, PlannedTask, PlanResult


_TASK_PROMPT = """You are NOVA, an expert AI assistant executing one step of a larger plan.

Overall goal: {goal}

Plan ({total} steps total):
{plan_summary}

You are now executing step {step_num} of {total}:
→ {task_description}

{prior_context}

Instructions:
- Focus ONLY on this step. Do not jump ahead.
- Be thorough and concrete.
- If this is a code step, write complete, runnable code.
- Do not repeat what was covered in earlier steps.
- End with a clear, concise summary of what was accomplished in this step.
"""

_FINAL_PROMPT = """You are NOVA. You have just completed a {total}-step plan to achieve the following goal:

GOAL: {goal}

Here is what was produced at each step:

{steps_summary}

Now write a clean, unified final answer that:
1. Synthesises all steps into a coherent response.
2. Removes any repetition.
3. Keeps all code blocks, commands, and key details.
4. Ends with clear "Next Steps" or a brief closing statement.

Respond directly — no preamble.
"""


class PlanExecutor:
    """
    Executes each task in an ExecutionPlan one by one.

    Results are accumulated and fed back as context for subsequent tasks,
    simulating true chain-of-thought execution.
    """

    def __init__(self, model_manager):
        self._model = model_manager
        logger.info("PlanExecutor initialized")

    def execute(
        self,
        plan: ExecutionPlan,
        personality: Optional[str] = None,
        memory: Optional[dict] = None,
    ) -> PlanResult:

        logger.info(
            f"PlanExecutor → executing plan {plan.plan_id} "
            f"({plan.task_count()} tasks)"
        )

        # For simple single-task plans skip the overhead
        if plan.is_simple():
            return self._execute_simple(plan, personality, memory)

        return self._execute_multi(plan, personality, memory)

    # ──────────────────────────────────────────────────────────────────
    # Simple path: single task → direct LLM call
    # ──────────────────────────────────────────────────────────────────

    def _execute_simple(
        self,
        plan: ExecutionPlan,
        personality: Optional[str],
        memory: Optional[dict],
    ) -> PlanResult:

        task = plan.tasks[0]
        logger.info(f"PlanExecutor → simple task: {task.description!r}")

        prompt = self._build_simple_prompt(task.description, personality, memory)
        response = self._generate(task.description, prompt)

        task.result = response
        task.completed = True

        return PlanResult(
            goal=plan.goal,
            plan_id=plan.plan_id,
            tasks_executed=1,
            response=response,
            steps=[{"step": 1, "task": task.description, "result": response}],
            is_simple=True,
        )

    # ──────────────────────────────────────────────────────────────────
    # Complex path: multi-task chain-of-thought
    # ──────────────────────────────────────────────────────────────────

    def _execute_multi(
        self,
        plan: ExecutionPlan,
        personality: Optional[str],
        memory: Optional[dict],
    ) -> PlanResult:

        total = plan.task_count()
        plan_summary = "\n".join(
            f"  {i+1}. {t.description}" for i, t in enumerate(plan.tasks)
        )
        accumulated: list[dict] = []

        for task in plan.tasks:
            step_num = task.index + 1
            logger.info(
                f"PlanExecutor → step {step_num}/{total}: {task.description!r}"
            )

            prior_context = self._format_prior_context(accumulated)

            prompt = _TASK_PROMPT.format(
                goal=plan.goal,
                total=total,
                plan_summary=plan_summary,
                step_num=step_num,
                task_description=task.description,
                prior_context=prior_context,
            )

            # Prepend personality block if provided
            if personality:
                prompt = f"{personality}\n\n{prompt}"

            result = self._generate(task.description, prompt)

            task.result = result
            task.completed = True

            accumulated.append({
                "step": step_num,
                "task": task.description,
                "result": result,
            })

            logger.info(f"PlanExecutor → step {step_num} complete")

        # Synthesise all results into one clean final answer
        final_response = self._synthesise(plan.goal, accumulated, total)

        return PlanResult(
            goal=plan.goal,
            plan_id=plan.plan_id,
            tasks_executed=total,
            response=final_response,
            steps=accumulated,
            is_simple=False,
        )

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    def _generate(self, message: str, prompt: str) -> str:
        response = self._model.generate(message=message, prompt=prompt)
        if hasattr(response, "text"):
            return self._clean(response.text)
        if isinstance(response, dict):
            return self._clean(response.get("response") or response.get("text", ""))
        return self._clean(str(response))

    @staticmethod
    def _clean(text: str) -> str:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        return text.strip()

    @staticmethod
    def _format_prior_context(accumulated: list[dict]) -> str:
        if not accumulated:
            return ""
        lines = ["Prior steps completed:"]
        for entry in accumulated:
            # Only include a short excerpt to avoid ballooning context
            excerpt = entry["result"][:600].strip()
            if len(entry["result"]) > 600:
                excerpt += "\n  [... truncated ...]"
            lines.append(f"\n--- Step {entry['step']}: {entry['task']} ---\n{excerpt}")
        return "\n".join(lines)

    def _synthesise(self, goal: str, steps: list[dict], total: int) -> str:
        steps_summary = "\n\n".join(
            f"=== Step {s['step']}: {s['task']} ===\n{s['result']}"
            for s in steps
        )
        prompt = _FINAL_PROMPT.format(
            total=total,
            goal=goal,
            steps_summary=steps_summary,
        )
        logger.info("PlanExecutor → synthesising final response")
        return self._generate(goal, prompt)

    @staticmethod
    def _build_simple_prompt(
        task: str,
        personality: Optional[str],
        memory: Optional[dict],
    ) -> str:
        sections = []
        if personality:
            sections.append(personality)
        if memory:
            mem_lines = "\n".join(f"  {k}: {v}" for k, v in memory.items())
            sections.append(f"[WHAT I KNOW ABOUT YOU]\n{mem_lines}")
        sections.append(f"[USER]\n{task}")
        sections.append("[NOVA] Respond directly and confidently.")
        return "\n\n".join(sections)
