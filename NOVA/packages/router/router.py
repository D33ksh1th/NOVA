"""
NOVA Request Router

Routes intents to the appropriate service.
"""

from services.brain.intent import Intent

from packages.common import logger


class RequestRouter:

    def __init__(self, memory, planner):

        self.memory = memory
        self.planner = planner
    
    def store_entity(self, entity):
        if entity is None:
            return None

        self.memory.remember(
            entity.key,
            entity.value
        )

        return {
            "action": "memory_store",
            "type": entity.type,
            "key": entity.key,
            "value": entity.value,
            "success": True
        }
    

    def route(self, intent: Intent, message: str):

        logger.info(f"Routing -> {intent.value}")

        # ------------------------
        # MEMORY STORE
        # ------------------------

#         if intent == Intent.MEMORY_STORE:

#             text = message.replace("remember", "").strip()

#             if "=" not in text:

#                 return {
#                     "success": False,
#                     "message": "Use remember key=value"
#                 }

#             key, value = text.split("=", 1)

#             self.memory.remember(
#                 key.strip(),
#                 value.strip()
#             )

#             return {
#                 "action": "memory_store",
#                 "success": True
#             }

#         # ------------------------
#         # MEMORY RECALL
#         # ------------------------

#         # ------------------------
# # MEMORY RECALL
# # ------------------------

#         if intent == Intent.MEMORY_RECALL:

#             text = (
#                 message.lower()
#                 .replace("what is", "")
#                 .replace("who is", "")
#                 .replace("show", "")
#                 .replace("recall", "")
#                 .replace("my", "")
#                 .replace("?", "")
#                 .strip()
#             )

#             key_map = {
#                 "name": "name",
#                 "birthday": "birthday",
#                 "city": "city",
#                 "favourite language": "favorite_language",
#                 "favorite language": "favorite_language",
#                 "favourite colour": "favorite_colour",
#                 "favorite colour": "favorite_colour",
#                 "company": "company",
#                 "profession": "profession",
#             }

#             key = key_map.get(text)

#             if not key:
#                 return {
#                     "action": "memory_recall",
#                     "value": None
#                 }

#             value = self.memory.recall(key)

#             return {
#                 "action": "memory_recall",
#                 "key": key,
#                 "value": value
#             }

        if intent == Intent.MEMORY_RECALL:

            logger.info(
                "Memory recall delegated to Knowledge Engine"
            )

            return None

        # ------------------------
        # PLANNER
        # ------------------------

        if intent == Intent.CREATE_TASK:

            goal = (
                message
                .replace("create", "")
                .replace("task", "")
                .strip()
            )

            return self.planner.create_goal(goal)

        # ------------------------
        # SECURITY
        # ------------------------

        if intent == Intent.SECURITY_SCAN:

            return {
                "action": "security_scan",
                "status": "coming_soon"
            }

        return None
    