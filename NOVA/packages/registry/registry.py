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

        self.gmail_monitor = GmailMonitor()

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