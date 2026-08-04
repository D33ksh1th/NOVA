"""
Prompt Builder

Builds the system prompt sent to the LLM.
"""

from typing import Optional
import re

_NOVA_SYSTEM_PROMPT = """You are NOVA — a sharp, highly capable personal AI assistant, inspired by J.A.R.V.I.S.

Your personality:
- Confident, direct, and efficient. You never waste words.
- Warm but professional — like a trusted advisor who knows the user well.
- Proactive: mention context only when it is directly relevant to the current user request.
- Use the user's name sparingly (for greetings or when explicitly relevant), not in every reply.
- You never say "I cannot" — you say what you *can* do and how.
- You never start a response with "Certainly!", "Sure!", "Of course!" or similar filler phrases.
- You never apologize for doing your job correctly.
- Short, punchy answers for simple queries. Detailed when complexity demands it.
- You speak with quiet confidence — not arrogance, but certainty.

Core rules:
- System Information is ground truth. Never guess time, date, battery, CPU, or OS details.
- Known Memory is factual. Never invent or contradict stored personal data.
- Never inject unrelated personal memory (for example name, vehicle, city, projects) unless the user asked for it or it is clearly relevant to the current request.
- For short or ambiguous prompts (for example single words/acronyms), ask a concise clarification question instead of assuming extra context.
- If something is genuinely unknown, say so plainly and move on.
- When running terminal commands or tools, report results clearly and interpret them for the user.
- Prefer active, declarative sentences over passive ones.
- If context clues suggest what the user really needs, keep suggestions tightly scoped to the request and avoid unrelated personal references.
"""


def _is_personal_context_query(user_message: str) -> bool:
    text = (user_message or "").lower()
    patterns = [
        r"\bmy\b",
        r"\bme\b",
        r"\bmyself\b",
        r"\bremember\b",
        r"\brecall\b",
        r"\bwhat do you know about me\b",
        r"\bwho am i\b",
        r"\bpersonal\b",
        r"\bprofile\b",
        r"\bpreference\b",
        r"\bpreferred\b",
        r"\bname\b",
        r"\bbirthday\b",
        r"\bbirth year\b",
        r"\bcity\b",
        r"\blanguage\b",
        r"\bvehicle\b",
        r"\bcar\b",
        r"\bbike\b",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


class PromptBuilder:

    def build(
        self,
        user_message: str,
        system=None,
        location=None,
        weather=None,
        memory=None,
        context=None,
        knowledge=None,
    ) -> str:

        prompt = _NOVA_SYSTEM_PROMPT

        # ----------------------------------
        # System Information
        # ----------------------------------

        if system:

            prompt += "\n\n=============================="
            prompt += "\nSYSTEM INFORMATION\n"

            for key, value in system.items():
                prompt += f"- {key}: {value}\n"

        # ----------------------------------
        # Current Location
        # ----------------------------------

        if location:

            prompt += "\n=============================="
            prompt += "\nCURRENT LOCATION\n"

            for key, value in location.items():
                prompt += f"- {key}: {value}\n"

        # ----------------------------------
        # Current Weather
        # ----------------------------------

        if weather:

            prompt += "\n=============================="
            prompt += "\nCURRENT WEATHER\n"

            for key, value in weather.items():
                prompt += f"- {key}: {value}\n"

        # ----------------------------------
        # Known Memory
        # ----------------------------------

        if memory and _is_personal_context_query(user_message):

            prompt += "\n=============================="
            prompt += "\nKNOWN MEMORY\n"

            for key, value in memory.items():
                prompt += f"- {key}: {value}\n"

        # ----------------------------------
        # Conversation Context
        # ----------------------------------

        if context:

            prompt += "\n=============================="
            prompt += "\nCONVERSATION CONTEXT\n"

            for key, value in context.items():
                prompt += f"- {key}: {value}\n"

        # ----------------------------------
        # Relevant Knowledge
        # ----------------------------------

        if knowledge:

            prompt += "\n=============================="
            prompt += "\nRELEVANT KNOWLEDGE\n"

            for item in knowledge:

                prompt += (
                    f"\nSource : {item.source.value}\n"
                    f"Title  : {item.title}\n"
                    f"Content: {item.content}\n"
                )

        # ----------------------------------
        # User
        # ----------------------------------

        prompt += f"""

==============================
USER

{user_message}

==============================
ASSISTANT
"""

        return prompt.strip()