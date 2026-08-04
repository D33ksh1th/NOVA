"""
Brain Engine
"""

import re
import subprocess
import time

from packages.common import logger

from services.brain.intent import IntentEngine
from services.brain.decision import DecisionEngine
from services.brain.entity import EntityEngine
from services.brain.reasoning import ReasoningEngine
from services.brain.conversation import ConversationMemory

from packages.router import RequestRouter
from services.memory.retriever import MemoryRetriever
from services.memory.manager import MemoryManager
from services.personality import PersonalityEngine
from services.skills.base import SkillContext
from services.reflection import ReflectionEngine


class BrainEngine:

    _ALLOWED_INSTALLERS = {"brew"}
    _ALLOWED_INSTALL_PACKAGES = {"blueutil"}
    _INSTALL_CONFIRM_TTL_SECONDS = 30

    def __init__(
        self,
        memory,
        planner,
        llm,
        knowledge,
        container,
        model_manager,
        tool_manager,
        agent_manager,
        skill_manager=None,
        reflection_engine=None,
    ):

        logger.info("Brain Engine Initialized")

        self.memory = memory

        self.memory_manager = MemoryManager(
            self.memory
        )

        self.planner = planner
        self.llm = llm
        self.knowledge = knowledge

        self.container = container
        self.model_manager = model_manager
        self.tool_manager = tool_manager
        self.agent_manager = agent_manager
        self.skill_manager = skill_manager
        self.reflection_engine = reflection_engine

        # Core Brain Components
        self.intent = IntentEngine()
        self.decision = DecisionEngine()
        self.entity = EntityEngine()
        self.reasoning = ReasoningEngine()
        self.conversation = ConversationMemory(max_turns=10)

        self.router = RequestRouter(
            memory=self.memory,
            planner=self.planner,
        )

        self.personality = PersonalityEngine()
        self.pending_install_request = None

        # Pre-load user name into personality if already stored in memory
        try:
            existing_name = self.memory.recall("name")
            if existing_name:
                self.personality.set_user_name(existing_name)
        except Exception:
            pass

    def process(self, message: str):

        logger.info(f"Incoming Message -> {message}")

        # -----------------------------------
        # Track user turn
        # -----------------------------------

        self.conversation.add_user(message)

        # -----------------------------------
        # Conversation Context
        # -----------------------------------

        context = self.container.context_engine.build(message)

        # Inject recent conversation history into context
        if not self.conversation.is_empty():
            context["conversation_history"] = self.conversation.as_text()

        # -----------------------------------
        # Pending Install Confirmation Flow
        # -----------------------------------

        install_followup = self._handle_pending_install_confirmation(message)
        if install_followup is not None:
            self.conversation.add_nova(install_followup.get("response", ""))
            return install_followup

        # -----------------------------------
        # Intent Detection
        # -----------------------------------

        detected = self.intent.detect_with_confidence(message)
        intent = detected.intent

        logger.info(f"Intent -> {intent} (confidence={detected.confidence:.2f})")

        # -----------------------------------
        # Entity Extraction
        # -----------------------------------

        entities = self.entity.extract(message)

        logger.info(f"Extracted Entities -> {entities}")

        # -----------------------------------
        # Automatic Memory Storage
        # -----------------------------------

        stored = None

        for entity in entities:

            result = self.router.store_entity(entity)

            # Sync user name into personality engine for personalised greetings
            if entity.key == "name":
                self.personality.set_user_name(entity.value)

            if result:
                stored = result

        if stored:
            response_text = f"Got it — I've noted your {stored.get('key', 'information')}."
            self.conversation.add_nova(response_text)
            stored["response"] = response_text
            return stored

        # -----------------------------------
        # Reasoning Step
        # -----------------------------------

        all_memory = self.memory_manager.recall_all() or {}
        reasoning = self.reasoning.reason(
            message=message,
            intent=intent,
            memory=all_memory,
            context=context,
        )

        logger.info(f"Reasoning -> strategy={reasoning.strategy.value}, tool={reasoning.suggested_tool}")
        for step in reasoning.reasoning_steps:
            logger.info(f"  • {step}")

        # -----------------------------------
        # Planner
        # -----------------------------------

        # -----------------------------------
        # Skill Manager  (primary dispatch)
        # -----------------------------------

        if self.skill_manager is not None:
            skill_ctx = SkillContext(
                message=message,
                intent=intent,
                memory=all_memory,
                context=context,
                personality=self.personality.build_context(),
            )
            skill_result = self.skill_manager.dispatch(skill_ctx)
            if skill_result is not None:
                install_prompt = self._capture_install_request(skill_result)
                if install_prompt is not None:
                    self.conversation.add_nova(install_prompt.get("response", ""))
                    install_prompt.setdefault("intent", intent.value)
                    return install_prompt

                # Keep deterministic tool outputs intact for factual operations.
                action_name = skill_result.get("action") if isinstance(skill_result, dict) else None
                if action_name not in {"filesystem", "system_info"}:
                    skill_result = self._reflect_result(
                        message=message,
                        result=skill_result,
                        intent=intent,
                        memory=all_memory,
                        context=context,
                    )
                response_text = skill_result.get("response", "")
                self.conversation.add_nova(response_text)
                skill_result.setdefault("intent", intent.value)
                return skill_result

        decision = self.planner.decide(message)

        logger.info(f"Planner Decision -> {decision}")

        # -----------------------------------
        # Memory
        # -----------------------------------

        memory_result = None

        if decision.use_memory:

            logger.info("Searching Memory...")

            memory_result = self.memory_manager.search(message)

            logger.info(f"Memory Retrieved -> {memory_result}")

        # -----------------------------------
        # Tool Execution
        # -----------------------------------

        tool_result = None

        if decision.use_tool:

            tool_result = self.planner.runtime.execute(
                decision,
                message,
            )

        # If the tool returned a complete response (time, date, weather,
        # system info) — return it directly without passing it to the LLM.
        # The LLM would only corrupt or contradict factual tool output.
        if isinstance(tool_result, dict) and tool_result.get("response"):
            response_text = tool_result["response"]
            self.conversation.add_nova(response_text)
            return {
                "action": tool_result.get("action", "tool"),
                "intent": intent.value,
                "response": response_text,
            }

        personality = self.personality.build_context()

        # Enrich prompt with reasoning hints
        if reasoning.follow_up_hints:
            personality = (personality or "") + "\n\nContext hints:\n" + "\n".join(
                f"- {h}" for h in reasoning.follow_up_hints
            )

        # -----------------------------------
        # Chain-of-Thought Task Planning
        # -----------------------------------
        # For complex goals (build, teach, explain from scratch, etc.)
        # use the TaskPlanner → PlanExecutor pipeline instead of a
        # direct single LLM call.

        if (
            self.planner.task_planner is not None
            and not decision.use_tool          # tools handle their own flow
            and not decision.answer_directly   # simple direct answers skip planning
        ):
            from services.planner.task_planner import _estimate_complexity  # local import to avoid cycles
            complexity = _estimate_complexity(message)

            if complexity == "complex":
                logger.info("BrainEngine → delegating to TaskPlanner (complex goal)")

                plan = self.planner.task_planner.plan(message)
                plan_result = self.planner.plan_executor.execute(
                    plan=plan,
                    personality=personality,
                    memory=memory_result,
                )

                plan_payload = {
                    "action": "plan",
                    "intent": intent.value,
                    "plan_id": plan_result.plan_id,
                    "tasks_executed": plan_result.tasks_executed,
                    "steps": [
                        {"step": s["step"], "task": s["task"]}
                        for s in plan_result.steps
                    ],
                    "response": plan_result.response,
                }

                plan_payload = self._reflect_result(
                    message=message,
                    result=plan_payload,
                    intent=intent,
                    memory=all_memory,
                    context=context,
                    plan_result=plan_payload,
                )

                self.conversation.add_nova(plan_payload["response"])

                return plan_payload

        # -----------------------------------
        # Prompt Builder  (simple / tool-augmented path)
        # -----------------------------------

        prompt = self.planner.prompt_builder.build(
            message=message,
            personality=personality,
            memory=memory_result,
            tool_result=tool_result,
            conversation_history=context.get("conversation_history"),
        )

        result = self.model_manager.generate(
            message=message,
            prompt=prompt,
        )

        # Normalise: model_manager returns LLMResponse(text, model) or dict
        if hasattr(result, "text"):
            response_text = result.text
        elif isinstance(result, dict):
            response_text = result.get("response") or result.get("text", "")
        else:
            response_text = str(result)

        result_payload = {
            "action": "chat",
            "intent": intent.value,
            "response": response_text,
        }

        result_payload = self._reflect_result(
            message=message,
            result=result_payload,
            intent=intent,
            memory=all_memory,
            context=context,
        )

        # Track NOVA's response in conversation memory
        self.conversation.add_nova(result_payload["response"])

        return result_payload

    def _reflect_result(self, message, result, intent, memory, context, plan_result=None):
        if self.reflection_engine is None:
            return result

        action = result.get("action") if isinstance(result, dict) else None
        response_text = result.get("response", "") if isinstance(result, dict) else str(result)

        reflected = self.reflection_engine.reflect(
            message=message,
            draft=response_text,
            intent=intent.value if hasattr(intent, "value") else str(intent),
            action=action,
            memory=memory,
            context=context,
            tool_result=None,
            plan_result=plan_result,
        )

        if not isinstance(reflected, dict):
            return result

        if isinstance(result, dict):
            merged = dict(result)
            merged.update(reflected)
            merged.setdefault("response", response_text)
            return merged

        return reflected

    def _capture_install_request(self, skill_result: dict):
        if not isinstance(skill_result, dict):
            return None

        if not skill_result.get("needs_install"):
            return None

        package = skill_result.get("package")
        install_args = skill_result.get("install_args")
        purpose = skill_result.get("purpose")

        if not package or not isinstance(install_args, list) or not install_args:
            return None

        if not self._is_install_request_allowed(package, install_args):
            return {
                "action": "system_info",
                "intent": "system_query",
                "success": False,
                "needs_install": False,
                "response": (
                    f"Install blocked by security policy for package '{package}'. "
                    "Only approved packages can be installed through chat."
                ),
            }

        self.pending_install_request = {
            "package": package,
            "purpose": purpose,
            "install_args": install_args,
            "created_at": time.time(),
        }

        response_text = skill_result.get("response") or (
            f"{package} is required. Should I install it now? Reply exactly: 'yes install {package}' or 'no'."
        )

        payload = {
            "action": "system_info",
            "success": False,
            "needs_install": True,
            "package": package,
            "purpose": purpose,
            "install_args": install_args,
            "response": response_text,
        }
        return payload

    def _handle_pending_install_confirmation(self, message: str):
        if not self.pending_install_request:
            return None

        created_at = self.pending_install_request.get("created_at")
        now = time.time()
        if isinstance(created_at, (int, float)) and (now - created_at) > self._INSTALL_CONFIRM_TTL_SECONDS:
            package = self.pending_install_request.get("package", "the package")
            self.pending_install_request = None
            return {
                "action": "system_info",
                "intent": "system_query",
                "success": False,
                "response": (
                    f"Install request for {package} expired after {self._INSTALL_CONFIRM_TTL_SECONDS} seconds. "
                    "Ask again if you still want to install it."
                ),
            }

        text = (message or "").strip().lower()
        no_tokens = {
            "no",
            "n",
            "no install",
            "cancel",
            "not now",
            "skip",
        }

        if text in no_tokens:
            package = self.pending_install_request.get("package", "that package")
            self.pending_install_request = None
            return {
                "action": "system_info",
                "intent": "system_query",
                "success": True,
                "response": f"Okay, I will not install {package} right now.",
            }

        package = str(self.pending_install_request.get("package", "")).strip().lower()
        expected_confirm = f"yes install {package}" if package else ""
        allowed_confirm_forms = {
            expected_confirm,
            f"confirm install {package}" if package else "",
            f"install {package}" if package else "",
        }
        allowed_confirm_forms.discard("")

        if text not in allowed_confirm_forms:
            if "install" in text or text in {"yes", "y", "ok", "okay", "go ahead", "proceed", "do it"}:
                return {
                    "action": "system_info",
                    "intent": "system_query",
                    "success": False,
                    "response": (
                        f"Install pending for {package}. For security, reply exactly: "
                        f"'yes install {package}' to continue, or 'no' to cancel."
                    ),
                }
            return None

        install_args = self.pending_install_request.get("install_args") or []

        if not self._is_install_request_allowed(package, install_args):
            self.pending_install_request = None
            return {
                "action": "system_info",
                "intent": "system_query",
                "success": False,
                "response": (
                    f"Install blocked by security policy for package '{package}'. "
                    "No installation was performed."
                ),
            }

        try:
            result = subprocess.run(
                install_args,
                capture_output=True,
                text=True,
                timeout=900,
            )
        except Exception as ex:
            self.pending_install_request = None
            return {
                "action": "system_info",
                "intent": "system_query",
                "success": False,
                "response": f"Failed to install {package}: {ex}",
            }

        self.pending_install_request = None

        if result.returncode != 0:
            error_text = (result.stderr or result.stdout or "Unknown error").strip()
            return {
                "action": "system_info",
                "intent": "system_query",
                "success": False,
                "response": f"Installation failed for {package}: {error_text}",
            }

        output = (result.stdout or "").strip()
        tail = output[-250:] if output else "Installation completed successfully."
        return {
            "action": "system_info",
            "intent": "system_query",
            "success": True,
            "response": f"Installed {package} successfully. {tail}",
        }

    def _is_install_request_allowed(self, package: str, install_args: list) -> bool:
        if not package or not isinstance(install_args, list) or len(install_args) < 3:
            return False

        pkg = str(package).strip().lower()
        if not re.fullmatch(r"[a-z0-9@._+-]+", pkg):
            return False

        installer = str(install_args[0]).strip().lower()
        verb = str(install_args[1]).strip().lower()

        if installer not in self._ALLOWED_INSTALLERS:
            return False
        if verb != "install":
            return False
        if pkg not in self._ALLOWED_INSTALL_PACKAGES:
            return False

        # Enforce exact command shape for security.
        expected = [installer, "install", pkg]
        normalized_args = [str(a).strip().lower() for a in install_args]
        return normalized_args == expected

