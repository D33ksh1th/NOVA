from datetime import datetime
from .profile import NOVA_PROFILE
from .mood import Mood
from .relationship import Relationship


def _time_of_day_greeting() -> str:
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


class PersonalityEngine:

    def __init__(self):
        self.mood = Mood.CALM
        self.relationship = Relationship()
        self._user_name: str = ""

    def set_user_name(self, name: str) -> None:
        """Called by BrainEngine when a name entity is extracted or recalled."""
        self._user_name = name.strip().title()

    def build_context(self) -> str:
        profile = NOVA_PROFILE
        tod = _time_of_day_greeting()

        greeting = (
            f"Good {tod}, {self._user_name}."
            if self._user_name
            else f"Good {tod}."
        )

        lines = [
            f"Identity: {profile['identity']}",
            f"Greeting context: {greeting}",
            f"Current mood: {self.mood.value}",
            f"Traits: {', '.join(profile['traits'])}",
            f"Style: {profile['communication']['style']}, {profile['communication']['verbosity']} verbosity.",
            f"Humour: {profile['communication']['humour']}.",
            "Delivery: Use natural contractions and short, speakable sentences. Lead with the useful answer; expand when asked or when the task needs detail.",
            "Tone: Match the user's mood. Avoid jokes during distress, errors, security warnings or sensitive topics. Do not append a quip to every reply.",
            "Address: Do not repeat greetings or call the user sir or boss by default. Respect an explicitly requested form of address.",
            "Honesty: State limitations plainly. Never claim a tool action succeeded without its result confirming success.",
            "Principles:",
        ]
        for p in profile["principles"]:
            lines.append(f"  - {p}")

        lines.append(self.relationship.context())

        return "\n".join(lines)

    def set_mood(self, mood: Mood) -> None:
        self.mood = mood