"""
Entity Extraction Engine

Extracts structured personal facts from natural language.
Designed to feed NOVA's memory system automatically.
"""

import re
from dataclasses import dataclass
from typing import List


@dataclass
class ExtractedEntity:
    type: str
    key: str
    value: str


# (pattern, entity_type, key)
_EXTRACTION_PATTERNS = [
    # --- Profile ---
    (r"\bmy name is\s+([a-zA-Z ]+?)(?=\s+and\b|,|\.|$)", "profile", "name"),
    (r"\bcall me\s+([a-zA-Z]+)\b", "profile", "name"),
    (r"\bi am\s+(\d{1,3})\s+years old\b", "profile", "age"),
    (r"\bmy age is\s+(\d{1,3})\b", "profile", "age"),
    (r"\bi live in\s+([a-zA-Z ,]+?)(?=\s+and\b|,|\.|$)", "profile", "city"),
    (r"\bmy (home|current) city is\s+([a-zA-Z ]+?)(?=\s+and\b|,|\.|$)", "profile", "city"),
    (r"\bi('m| am) from\s+([a-zA-Z ]+?)(?=\s+and\b|,|\.|$)", "profile", "hometown"),
    (r"\bmy birth year is\s+(\d{4})\b", "profile", "birth_year"),
    (r"\bborn in\s+(\d{4})\b", "profile", "birth_year"),
    (r"\bmy birthday is\s+(.+?)(?=\s+and\b|,|\.|$)", "profile", "birthday"),
    (r"\bmy (gender|pronouns?) (is|are)\s+([a-zA-Z/ ]+?)(?=\s+and\b|,|\.|$)", "profile", "gender"),

    # --- Career ---
    (r"\bi work at\s+(.+?)(?=\s+and\b|,|\.|$)", "career", "company"),
    (r"\bmy company is\s+(.+?)(?=\s+and\b|,|\.|$)", "career", "company"),
    (r"\bi am a\s+([a-zA-Z ]+?)(?=\s+and\b|,|\.|$)", "career", "profession"),
    (r"\bmy (job|role|position|title) is\s+(.+?)(?=\s+and\b|,|\.|$)", "career", "job_title"),
    (r"\bi work as (a |an )?(.+?)(?=\s+and\b|,|\.|$)", "career", "profession"),
    (r"\bi('ve| have) been (working|doing) (.+?) for (\d+) years?\b", "career", "experience"),

    # --- Preferences ---
    (r"\bmy fav(ou?rite)? (programming )?language is\s+([a-zA-Z+# ]+?)(?=\s+and\b|,|\.|$)", "preference", "favorite_language"),
    (r"\bi (prefer|use|love|like) (programming in |coding in )?([a-zA-Z+#]+) (for coding|as my language)\b", "preference", "favorite_language"),
    (r"\bmy fav(ou?rite)? colou?r is\s+([a-zA-Z ]+?)(?=\s+and\b|,|\.|$)", "preference", "favorite_colour"),
    (r"\bmy fav(ou?rite)? food is\s+([a-zA-Z ]+?)(?=\s+and\b|,|\.|$)", "preference", "favorite_food"),
    (r"\bmy fav(ou?rite)? (music|song|band|artist) is\s+(.+?)(?=\s+and\b|,|\.|$)", "preference", "favorite_music"),
    (r"\bmy fav(ou?rite)? (movie|film|show|series) is\s+(.+?)(?=\s+and\b|,|\.|$)", "preference", "favorite_movie"),
    (r"\bmy fav(ou?rite)? sport is\s+([a-zA-Z ]+?)(?=\s+and\b|,|\.|$)", "preference", "favorite_sport"),

    # --- Ownership & possessions ---
    (r"\bi own a\s+(.+?)(?=\s+and\b|,|\.|$)", "ownership", "vehicle"),
    (r"\bmy (car|vehicle|bike|motorcycle) is (a |an )?(.+?)(?=\s+and\b|,|\.|$)", "ownership", "vehicle"),
    (r"\bi have a\s+(dog|cat|pet)\s+(named|called)?\s*([a-zA-Z]*)", "ownership", "pet"),

    # --- Relationships ---
    (r"\bmy (wife|husband|partner|spouse)(?:'?s name)? is\s+([a-zA-Z]+)", "relationship", "partner"),
    (r"\bmy (son|daughter|child|kid)(?:'?s name)? is\s+([a-zA-Z]+)", "relationship", "child"),
    (r"\bmy (mother|mom|father|dad|brother|sister)(?:'?s name)? is\s+([a-zA-Z]+)", "relationship", "family"),

    # --- Goals & interests ---
    (r"\bmy goal is\s+(.+?)(?=\s+and\b|,|\.|$)", "goal", "goal"),
    (r"\bi('m| am) learning\s+([a-zA-Z ]+?)(?=\s+and\b|,|\.|$)", "goal", "learning"),
    (r"\bmy hobby is\s+([a-zA-Z ]+?)(?=\s+and\b|,|\.|$)", "interest", "hobby"),
    (r"\bi (enjoy|love|like) (playing |doing |watching )?([a-zA-Z ]+?) (in my free time|as a hobby)\b", "interest", "hobby"),
]


def _get_last_group(match) -> str:
    """Return the last non-None capture group."""
    groups = [g for g in match.groups() if g is not None]
    return groups[-1].strip() if groups else ""


class EntityEngine:
    """
    Extracts structured entities from user messages and
    stores them in NOVA's memory for future recall.
    """

    def extract(self, message: str) -> List[ExtractedEntity]:
        text = message.lower().strip()
        entities: List[ExtractedEntity] = []
        seen_keys: set = set()

        for pattern, entity_type, key in _EXTRACTION_PATTERNS:
            for match in re.finditer(pattern, text):
                value = _get_last_group(match).strip()
                if value and key not in seen_keys:
                    entities.append(
                        ExtractedEntity(
                            type=entity_type,
                            key=key,
                            value=value,
                        )
                    )
                    seen_keys.add(key)

        return entities
