"""
Reasoning Engine

Implements a lightweight chain-of-thought reasoning layer
that analyses the user's message + context to determine:
  - What the user *actually* wants (true goal)
  - What context is relevant
  - What response strategy to use
  - Whether tools / memory / knowledge are needed
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

from services.brain.intent import Intent


class ResponseStrategy(str, Enum):
    DIRECT_ANSWER = "direct_answer"       # Answer from knowledge/context
    TOOL_CALL = "tool_call"               # Must use a tool
    MEMORY_RECALL = "memory_recall"       # Pull from memory
    MEMORY_STORE = "memory_store"         # Store to memory
    LLM_GENERATE = "llm_generate"        # Let the LLM answer
    TASK_CREATE = "task_create"           # Create a task/goal
    CLARIFY = "clarify"                   # Need more information


@dataclass
class ReasoningResult:
    true_goal: str = ""
    strategy: ResponseStrategy = ResponseStrategy.LLM_GENERATE
    needs_tool: bool = False
    suggested_tool: Optional[str] = None
    needs_memory: bool = True
    needs_context: bool = True
    confidence: float = 0.5
    reasoning_steps: List[str] = field(default_factory=list)
    follow_up_hints: List[str] = field(default_factory=list)


# Maps intent → strategy
_INTENT_STRATEGY_MAP = {
    Intent.MEMORY_STORE: ResponseStrategy.MEMORY_STORE,
    Intent.MEMORY_RECALL: ResponseStrategy.MEMORY_RECALL,
    Intent.CREATE_TASK: ResponseStrategy.TASK_CREATE,
    Intent.LIST_TASKS: ResponseStrategy.TOOL_CALL,
    Intent.SYSTEM_QUERY: ResponseStrategy.TOOL_CALL,
    Intent.WEATHER_QUERY: ResponseStrategy.TOOL_CALL,
    Intent.TIME_QUERY: ResponseStrategy.TOOL_CALL,
    Intent.FILE_OPERATION: ResponseStrategy.TOOL_CALL,
    Intent.COMMAND_RUN: ResponseStrategy.TOOL_CALL,
    Intent.CALCULATION: ResponseStrategy.DIRECT_ANSWER,
    Intent.CODE_HELP: ResponseStrategy.LLM_GENERATE,
    Intent.WEB_SEARCH: ResponseStrategy.TOOL_CALL,
    Intent.SECURITY_SCAN: ResponseStrategy.TOOL_CALL,
    Intent.CHAT: ResponseStrategy.LLM_GENERATE,
    Intent.REMINDER: ResponseStrategy.TASK_CREATE,
    Intent.UNKNOWN: ResponseStrategy.LLM_GENERATE,
}

# Tool suggestions per intent
_INTENT_TOOL_MAP = {
    Intent.SYSTEM_QUERY: "SystemInfoTool",
    Intent.WEATHER_QUERY: "WeatherTool",
    Intent.TIME_QUERY: "DateTimeTool",
    Intent.FILE_OPERATION: "FilesystemTool",
    Intent.COMMAND_RUN: "TerminalTool",
    Intent.WEB_SEARCH: "WebSearchTool",
    Intent.SECURITY_SCAN: "SecurityScanTool",
    Intent.LIST_TASKS: "TaskListTool",
}


class ReasoningEngine:
    """
    Lightweight chain-of-thought reasoner.

    Usage:
        result = ReasoningEngine().reason(message, intent, context)
    """

    def reason(
        self,
        message: str,
        intent: Intent,
        memory: Optional[dict] = None,
        context: Optional[dict] = None,
    ) -> ReasoningResult:

        steps: List[str] = []
        result = ReasoningResult()

        # --- Step 1: Determine the true goal ---
        steps.append(f"User said: '{message}'")
        steps.append(f"Detected intent: {intent.value}")
        result.true_goal = self._derive_goal(message, intent)
        steps.append(f"True goal: {result.true_goal}")

        # --- Step 2: Select response strategy ---
        result.strategy = _INTENT_STRATEGY_MAP.get(
            intent, ResponseStrategy.LLM_GENERATE
        )
        steps.append(f"Strategy selected: {result.strategy.value}")

        # --- Step 3: Identify required tools ---
        if result.strategy == ResponseStrategy.TOOL_CALL:
            result.needs_tool = True
            result.suggested_tool = _INTENT_TOOL_MAP.get(intent)
            steps.append(
                f"Tool required: {result.suggested_tool or 'unknown'}"
            )

        # --- Step 4: Determine if memory is useful ---
        memory_intents = {Intent.MEMORY_RECALL, Intent.MEMORY_STORE}
        result.needs_memory = (
            intent in memory_intents
            or self._message_references_user(message)
        )
        steps.append(
            f"Memory needed: {result.needs_memory}"
        )

        # --- Step 5: Context relevance ---
        result.needs_context = intent not in {
            Intent.CALCULATION,
            Intent.WEB_SEARCH,
        }

        # --- Step 6: Confidence ---
        result.confidence = self._estimate_confidence(message, intent)
        steps.append(f"Confidence: {result.confidence:.2f}")

        # --- Step 7: Proactive follow-up hints ---
        result.follow_up_hints = self._generate_hints(intent, memory)

        result.reasoning_steps = steps
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _derive_goal(self, message: str, intent: Intent) -> str:
        goal_map = {
            Intent.MEMORY_STORE: "Store personal information",
            Intent.MEMORY_RECALL: "Recall personal information",
            Intent.SYSTEM_QUERY: "Retrieve system/hardware status",
            Intent.WEATHER_QUERY: "Get current weather conditions",
            Intent.TIME_QUERY: "Get current date/time",
            Intent.CODE_HELP: "Provide coding assistance",
            Intent.FILE_OPERATION: "Perform a file system operation",
            Intent.COMMAND_RUN: "Execute a terminal command",
            Intent.CREATE_TASK: "Create a new task or goal",
            Intent.LIST_TASKS: "Show existing tasks",
            Intent.REMINDER: "Set a reminder",
            Intent.CALCULATION: "Perform a calculation",
            Intent.WEB_SEARCH: "Search the web",
            Intent.SECURITY_SCAN: "Run a security audit",
            Intent.CHAT: "Engage in conversation",
        }
        return goal_map.get(intent, "Respond to user request")

    def _message_references_user(self, message: str) -> bool:
        """Check if message references personal info even without explicit memory intent."""
        text = message.lower()
        personal_keywords = [
            "my name", "my age", "my city", "where i live",
            "my job", "who am i", "my birthday", "i am", "i have",
        ]
        return any(kw in text for kw in personal_keywords)

    def _estimate_confidence(self, message: str, intent: Intent) -> float:
        """Simple confidence heuristic based on message length and intent clarity."""
        if intent == Intent.UNKNOWN:
            return 0.3
        if intent == Intent.CHAT:
            return 0.5
        # Longer messages with clear intent patterns → higher confidence
        length_bonus = min(len(message.split()) * 0.02, 0.3)
        return min(0.65 + length_bonus, 1.0)

    def _generate_hints(
        self,
        intent: Intent,
        memory: Optional[dict],
    ) -> List[str]:
        """Generate proactive hints NOVA might add to the response."""
        hints = []

        if intent == Intent.WEATHER_QUERY and memory and "city" in memory:
            hints.append(
                f"User is in {memory['city']} — use that for weather context"
            )

        if intent == Intent.CODE_HELP:
            if memory and "favorite_language" in memory:
                hints.append(
                    f"User prefers {memory['favorite_language']} — default to it"
                )

        if intent == Intent.SYSTEM_QUERY:
            hints.append("Include actionable insight, not just raw numbers")

        return hints
