"""
Planner Prompt Builder

Builds prompts for the LLM using
available context.
"""

from packages.common import logger


class PromptBuilder:

    def __init__(self):

        logger.info("Prompt Builder Initialized")

    def build(
        self,
        message: str,
        personality=None,
        tool_result=None,
        memory=None,
        knowledge=None,
        conversation_history=None,
    ) -> str:

        sections: list[str] = []

        if personality:
            sections.append(f"[PERSONA]\n{personality}")

        if memory:
            if isinstance(memory, dict):
                mem_lines = "\n".join(f"  {k}: {v}" for k, v in memory.items())
            else:
                mem_lines = str(memory)
            sections.append(f"[WHAT I KNOW ABOUT YOU]\n{mem_lines}")

        if knowledge:
            sections.append(f"[RELEVANT KNOWLEDGE]\n{knowledge}")

        if conversation_history:
            sections.append(f"[RECENT CONVERSATION]\n{conversation_history}")

        if tool_result:
            sections.append(f"[TOOL OUTPUT]\n{tool_result}")

        sections.append(f"[USER]\n{message}")
        sections.append(
            "[NOVA] Respond directly, confidently, and without filler phrases."
        )

        return "\n\n".join(sections)