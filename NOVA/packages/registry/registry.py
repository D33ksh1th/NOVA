"""
NOVA Service Registry

Creates and manages singleton instances of all services.
"""

from packages.common import logger
from packages.config import settings

from services.memory import Memory
from services.planner import Planner
from services.brain import Brain
from services.llm import LLMClient
from services.knowledge import KnowledgeService
from services.models import ModelManager
from services.reflection import ReflectionEngine
from services.voice import VoiceEngine
from services.avatar import AvatarEventStream
from services.security import SecurityCenter

from packages.application import ConversationService
from packages.container import ApplicationContainer
from services.initiative import InitiativeEngine

from services.skills import (
    SkillRegistry,
    SkillManager,
    MemorySkill,
    PlannerSkill,
)
from services.skills import (
    ChatSkill,
    WeatherSkill,
    TimeSkill,
    SecuritySkill,
    SystemSkill,
    LocationSkill,
    CalculatorSkill,
    CodingSkill,
    ShellSkill,
    FileSkill,
    VisionSkill,
    VoiceIdentitySkill,
    GmailSkill,
)
from services.skills.capabilities import CapabilitiesSkill
from services.skills.nova_status import NovaStatusSkill
from services.skills.screen_awareness import ScreenAwarenessSkill
from services.skills.clipboard import ClipboardSkill
from services.skills.knowledge_store import KnowledgeStoreSkill
from services.skills.code_review import CodeReviewSkill

from services.tools import (
    ToolRegistry,
    ToolManager,
    TimeTool,
    DateTool,
    LocationTool,
    WeatherTool,
    FileSystemTool,
    TerminalTool,
    SystemInfoTool,
    VisionTool,
)
from services.tools.gmail_tool import GmailTool
from services.tools.reminder_tool import ReminderTool
from services.tools.web_search_tool import WebSearchTool
from services.tools.mac_tool import MacTool
from services.skills.reminder import ReminderSkill
from services.skills.web_search import WebSearchSkill
from services.skills.mac import MacSkill
from services.initiative.gmail_monitor import GmailMonitor

from services.agents import (
    AgentRegistry,
    AgentManager,
    SystemAgent,
    ChatAgent,
    CodingAgent,
)


    


class ServiceRegistry:

    def __init__(self):

        logger.info("Creating Service Registry...")

        # ----------------------------------
        # Core Services
        # ----------------------------------

        self.memory = Memory()

        self.planner = Planner()

        self.llm = LLMClient()

        self.knowledge = KnowledgeService(
            memory=self.memory
        )

        # ----------------------------------
        # Shared Infrastructure
        # ----------------------------------

        self.container = ApplicationContainer(
            self.memory
        )

        self.model_manager = ModelManager()
        self.reflection_engine = ReflectionEngine(self.model_manager)

        

        # ----------------------------------
        # Skills
        # ----------------------------------

        self.skill_registry = SkillRegistry()

        self.skill_registry.register(
            MemorySkill(self.memory)
        )

        self.skill_registry.register(
            PlannerSkill(self.planner)
        )

        self.skill_manager = SkillManager(
            self.skill_registry
        )

        self.tool_registry = ToolRegistry()

        self.tool_registry.register(
            TimeTool()
        )

        self.tool_manager = ToolManager(
            self.tool_registry
        )

        self.tool_registry.register(
            DateTool()
        )

        self.tool_registry.register(
            LocationTool(
                self.container.location_context
            )
        )

        self.tool_registry.register(
            WeatherTool(
                self.container.location_context,
                self.container.weather_context,
            )
        )
        self.tool_registry.register(
            SystemInfoTool()
        )

        self.tool_registry.register(
            TerminalTool()
        )

        self.tool_registry.register(
            FileSystemTool()
        )

        self.tool_registry.register(
            VisionTool()
        )

        self.gmail_tool = GmailTool()
        self.tool_registry.register(self.gmail_tool)

        self.reminder_tool = ReminderTool()
        self.tool_registry.register(self.reminder_tool)

        self.tool_registry.register(WebSearchTool())

        self.tool_registry.register(MacTool())

        self.gmail_monitor = GmailMonitor()

        self.security_center = SecurityCenter()

        self.planner = Planner(
            tool_registry=self.tool_registry,
            model_manager=self.model_manager,
        )

        self.agent_registry = AgentRegistry()

        self.agent_registry.register(

            SystemAgent(
                self.tool_manager
            )

        )

        self.agent_registry.register(
            CodingAgent(
                self.tool_manager
            )
        )

        self.agent_registry.register(
            ChatAgent(
                container=self.container,
                knowledge=self.knowledge,
                model_manager=self.model_manager,
            )
        )

        self.agent_manager = AgentManager(
            self.agent_registry
        )

        # ----------------------------------
        # Brain
        # ----------------------------------

        self.brain = Brain(
            memory=self.memory,
            planner=self.planner,
            llm=self.llm,
            knowledge=self.knowledge,
            container=self.container,
            model_manager=self.model_manager,
            tool_manager=self.tool_manager,
            agent_manager=self.agent_manager,
            reflection_engine=self.reflection_engine,
        )

        # ----------------------------------
        # Skill System  (registered after tools so skills can wrap them)
        # ----------------------------------

        _time_tool    = self.tool_registry.find_by_name("TimeTool")
        _location_tool = self.tool_registry.find_by_name("LocationTool")
        _weather_tool  = self.tool_registry.find_by_name("WeatherTool")
        _system_tool   = self.tool_registry.find_by_name("SystemInfoTool")
        _terminal_tool = self.tool_registry.find_by_name("TerminalTool")
        _fs_tool       = self.tool_registry.find_by_name("FileSystemTool")
        _vision_tool   = self.tool_registry.find_by_name("VisionTool")

        self.skill_registry = SkillRegistry()

        # Priority order matters — more specific skills first
        self.skill_registry.register(TimeSkill(_time_tool))
        self.skill_registry.register(SecuritySkill())
        self.skill_registry.register(SystemSkill(_system_tool))
        self.skill_registry.register(LocationSkill(_location_tool))
        self.skill_registry.register(WeatherSkill(_weather_tool))
        self.skill_registry.register(CalculatorSkill())
        self.skill_registry.register(CodingSkill(self.model_manager))
        self.skill_registry.register(ShellSkill(_terminal_tool))
        self.skill_registry.register(FileSkill(_fs_tool))
        self.skill_registry.register(VisionSkill(_vision_tool))
        self.skill_registry.register(MemorySkill(self.memory))
        self.skill_registry.register(PlannerSkill(self.planner))
        # GmailSkill registered before ChatSkill (fallback) so it intercepts email commands
        self.skill_registry.register(GmailSkill())
        # Deterministic automation skills — before ChatSkill fallback
        _reminder_tool   = self.tool_registry.find_by_name("ReminderTool")
        _web_search_tool = self.tool_registry.find_by_name("WebSearchTool")
        _mac_tool        = self.tool_registry.find_by_name("MacTool")
        self.skill_registry.register(ReminderSkill(_reminder_tool))
        self.skill_registry.register(WebSearchSkill(_web_search_tool))
        self.skill_registry.register(MacSkill(_mac_tool))
        self.skill_registry.register(CapabilitiesSkill())
        self.skill_registry.register(NovaStatusSkill())
        self.skill_registry.register(ScreenAwarenessSkill())
        self.skill_registry.register(ClipboardSkill())
        self.skill_registry.register(KnowledgeStoreSkill())
        self.skill_registry.register(CodeReviewSkill())
        # ----------------------------------
        # Conversation
        # ----------------------------------

        self.initiative_engine = InitiativeEngine(
            memory=self.memory,
            system_context=self.container.system_context,
        )

        self.conversation = ConversationService(
            brain=self.brain,
            initiative_engine=self.initiative_engine,
        )

        self.voice_engine = VoiceEngine(
            conversation_service=self.conversation,
            enabled=settings.ENABLE_VOICE,
        )

        # Wire reminder TTS callback so fired reminders are spoken aloud.
        if hasattr(self, "reminder_tool") and self.reminder_tool is not None:
            self.reminder_tool.set_speak_callback(
                lambda text: self.voice_engine.synthesizer.speak(text, play=True)
            )

        # Register voice identity skill only after voice engine is initialized.
        self.skill_registry.register(VoiceIdentitySkill(
            speaker_registry=self.voice_engine.pipeline.speaker_registry,
            voice_recognition_enabled_fn=lambda: getattr(self.voice_engine, "recognition_enabled", True),
        ))

        # ChatSkill is the fallback — register last
        self.skill_registry.register(ChatSkill(
            llm=self.llm,
            prompt_builder=self.container.prompt_builder,
            knowledge=self.knowledge,
            memory_context=self.container.memory_context,
            context_engine=self.container.context_engine,
        ))

        self.skill_manager = SkillManager(self.skill_registry)

        # Inject SkillManager into BrainEngine (Brain is a thin wrapper)
        self.brain.engine.skill_manager = self.skill_manager

        self.avatar_stream = AvatarEventStream()
        self.avatar_stream.register_bridge()

        # Proactive subsystem
        from services.initiative.notification_policy import NotificationPolicy
        from services.initiative.proactive_daemon import ProactiveDaemon

        def _is_present():
            try:
                from services.gateway.routes import _active_face_is_admin
                return _active_face_is_admin()
            except Exception:
                return True

        def _speak(text):
            try:
                self.voice_engine.synthesizer.speak(text, play=True)
            except Exception:
                pass

        self.notification_policy = NotificationPolicy(
            presence_fn=_is_present,
            speak_fn=_speak,
        )
        self.proactive_daemon = ProactiveDaemon(
            presence_fn=_is_present,
            speak_fn=_speak,
        )
        self.proactive_daemon.start()

        # Action gate (Phase 7)
        from services.tools.action_gate import ActionGate
        self.action_gate = ActionGate(speak_fn=_speak)

        # App context watcher
        from services.context.app_watcher import AppContextWatcher
        self.app_watcher = AppContextWatcher()
        self.app_watcher.start()

        logger.info("Service Registry Ready")

    def health(self):

        return {
            "brain": "online",
            "memory": "online",
            "planner": "online",
            "knowledge": "online",
            "llm": "online",
            "voice": "online" if self.voice_engine.enabled else "disabled",
        }


registry = ServiceRegistry()