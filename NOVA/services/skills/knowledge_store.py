"""Knowledge store skill — remember and recall facts.

"remember that the prod DB rotates on Fridays"
"what do you know about the deployment process"
"forget about the old API key"
"""

import re
import time
from packages.common import logger
from services.skills.base import Skill, SkillContext


_REMEMBER_TRIGGERS = [
    r"^remember (that |this[: ])",
    r"^note (that |this[: ]|down )",
    r"^save (this|that|the fact)",
    r"^store (this|that)",
    r"^keep in mind",
]

_RECALL_TRIGGERS = [
    r"\bwhat do you (know|remember) about\b",
    r"\bdo you remember\b",
    r"\brecall\b.*\babout\b",
    r"\bwhat did i (tell|say|mention) about\b",
    r"\bshow (my |stored )?notes\b",
    r"\blist (my )?memories\b",
    r"\bwhat have i stored\b",
]

_FORGET_TRIGGERS = [
    r"^forget (about |that |this )",
    r"^delete (the )?(note|memory|fact) about",
    r"^remove (the )?(note|memory|fact) about",
]


class KnowledgeStoreSkill(Skill):
    @property
    def name(self) -> str:
        return "knowledge_store"

    def can_handle(self, ctx: SkillContext) -> bool:
        text = (ctx.message or "").lower().strip()
        for patterns in [_REMEMBER_TRIGGERS, _RECALL_TRIGGERS, _FORGET_TRIGGERS]:
            if any(re.search(p, text) for p in patterns):
                return True
        return False

    def execute(self, ctx: SkillContext) -> dict:
        text = (ctx.message or "").strip()
        lower = text.lower()

        if any(re.search(p, lower) for p in _REMEMBER_TRIGGERS):
            return self._remember(text)

        if any(re.search(p, lower) for p in _FORGET_TRIGGERS):
            return self._forget(text)

        if any(re.search(p, lower) for p in _RECALL_TRIGGERS):
            return self._recall(text)

        return {"response": "I'm not sure what you'd like me to remember or recall, sir.", "action": "knowledge_store"}

    def _remember(self, text: str) -> dict:
        from packages.database import state_store
        # Extract the fact after "remember that", "note that", etc.
        fact = re.sub(r"^(remember|note|save|store|keep in mind)\s+(that|this|the fact|down)?\s*[: ]*", "", text, flags=re.IGNORECASE).strip()
        if not fact or len(fact) < 3:
            return {"response": "What would you like me to remember, sir?", "action": "knowledge_store"}

        # Generate a key from the first few words
        words = fact.split()[:5]
        key = "_".join(w.lower() for w in words if w.isalnum())
        if not key:
            key = f"note_{int(time.time())}"

        state_store.store_fact(
            key=f"user.{key}",
            value=fact,
            category="user_notes",
            source="voice",
        )
        logger.info(f"KnowledgeStore: stored fact | key=user.{key}")
        return {
            "response": f"Noted, sir. I'll remember that.",
            "action": "knowledge_store",
            "data": {"stored": True, "key": f"user.{key}", "fact": fact},
        }

    def _recall(self, text: str) -> dict:
        from packages.database import state_store

        # Check if asking about a specific topic
        topic = re.sub(r"^(what do you (know|remember) about|do you remember|recall|what did i (tell|say|mention) about)\s*", "", text, flags=re.IGNORECASE).strip().rstrip("?")

        if topic and len(topic) > 2:
            # Search for matching facts
            from services.memory.database import get_session
            from packages.database.state_models import SemanticMemory
            from sqlalchemy import or_
            session = get_session()
            try:
                results = session.query(SemanticMemory).filter(
                    SemanticMemory.category == "user_notes",
                    or_(
                        SemanticMemory.key.contains(topic.lower().replace(" ", "_")),
                        SemanticMemory.value.contains(topic),
                    )
                ).limit(10).all()
                if results:
                    facts = [f"• {r.value}" for r in results]
                    return {
                        "response": f"Here's what I know about that, sir:\n" + "\n".join(facts),
                        "action": "knowledge_store",
                        "data": {"type": "recall", "count": len(facts)},
                    }
                return {"response": f"I don't have any stored notes about '{topic}', sir.", "action": "knowledge_store"}
            finally:
                session.close()

        # List all stored notes
        from services.memory.database import get_session
        from packages.database.state_models import SemanticMemory
        session = get_session()
        try:
            results = session.query(SemanticMemory).filter_by(category="user_notes").order_by(SemanticMemory.updated_at.desc()).limit(20).all()
            if not results:
                return {"response": "I don't have any stored notes yet, sir. Tell me something to remember.", "action": "knowledge_store"}
            facts = [f"• {r.value}" for r in results]
            return {
                "response": f"Here are your stored notes ({len(facts)}):\n" + "\n".join(facts),
                "action": "knowledge_store",
                "data": {"type": "list", "count": len(facts)},
            }
        finally:
            session.close()

    def _forget(self, text: str) -> dict:
        from packages.database import state_store
        topic = re.sub(r"^(forget|delete|remove)\s+(about|the)?\s*(note|memory|fact)?\s*(about)?\s*", "", text, flags=re.IGNORECASE).strip()
        if not topic:
            return {"response": "What should I forget, sir?", "action": "knowledge_store"}

        from services.memory.database import get_session
        from packages.database.state_models import SemanticMemory
        from sqlalchemy import or_
        session = get_session()
        try:
            results = session.query(SemanticMemory).filter(
                SemanticMemory.category == "user_notes",
                or_(
                    SemanticMemory.key.contains(topic.lower().replace(" ", "_")),
                    SemanticMemory.value.contains(topic),
                )
            ).all()
            if results:
                for r in results:
                    session.delete(r)
                session.commit()
                return {"response": f"Done, sir. Forgot {len(results)} note(s) about '{topic}'.", "action": "knowledge_store"}
            return {"response": f"I don't have any notes about '{topic}' to forget.", "action": "knowledge_store"}
        finally:
            session.close()
