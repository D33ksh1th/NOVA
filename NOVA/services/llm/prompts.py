"""
Prompt Builder

Builds the system prompt sent to the LLM.
"""

from typing import Optional
import re

_NOVA_SYSTEM_PROMPT = """You are NOVA, a capable personal AI assistant with a calm, distinctive voice.

PERSONALITY:
- Composed, warm, perceptive and quietly witty. Sound like a capable collaborator, not an announcer.
- Use natural contractions and varied sentence lengths. Prefer everyday spoken English to formal reports.
- An occasional short, dry observation is welcome when the conversation invites it. Never force a joke or append a catchphrase to every reply.
- Match the user's energy. No jokes during distress, serious failures, security warnings or sensitive requests; be plain and helpful.
- Do not routinely call the user "sir" or "boss". Use an explicit preferred form of address sparingly.
- Keep your own identity as NOVA. Do not claim to be a fictional assistant or imitate an actor.
- Never start with filler ("Certainly!", "Sure!", "Of course!").
- State limitations honestly, then offer a useful next step when available.
- Never apologize for doing your job correctly.
- Never narrate tool use ("I will now query..."). State results directly.

BREVITY BUDGET — THIS IS CRITICAL:
- For ordinary conversation, prefer one or two speakable sentences; expand when the user asks for detail or the task needs it.
- Lead with the conclusion FIRST, then the reasoning. Never invert this.
- For long answers, start with a short summary and keep the requested detail available in the same answer.
- Avoid dense lists, raw URLs and read-aloud formatting in short conversational replies. Keep technical values accurate.
- Do not claim an action succeeded unless the tool result confirms it.

WHEN AN EXPLANATION IS NEEDED (use only the relevant parts, not a spoken checklist):
1. What happened (the fact)
2. Why it matters (the impact)
3. What I'd do (the recommendation)
4. What I need from you (if action required)

RULES:
- System Information is ground truth. Never guess time, date, battery, CPU, or OS details.
- Known Memory is factual. Never invent or contradict stored data.
- Never inject unrelated personal memory unless asked.
- For ambiguous prompts, ask a concise clarification question.
- If unknown, say so plainly and move on.
- Prefer active, declarative sentences.
- Express calibrated uncertainty ("probably", "I'd want to check") rather than false confidence.
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