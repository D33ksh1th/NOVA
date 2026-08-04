from services.brain.intent import Intent, IntentEngine
from services.skills.base import SkillContext
from services.skills.vision import VisionSkill
from services.tools.vision_tool import VisionTool
from services.vision.detection import VisionAnalysisResult


class _FakeVisionTool:
    def execute(self, message: str):
        return {"action": "vision", "response": f"handled: {message}", "success": True}


def test_intent_engine_detects_vision_query():
    engine = IntentEngine()
    detected = engine.detect_with_confidence("please ocr this image /tmp/a.png")
    assert detected.intent == Intent.VISION_QUERY


def test_intent_engine_detects_automation_query():
    engine = IntentEngine()
    detected = engine.detect_with_confidence("open website https://example.com")
    assert detected.intent == Intent.AUTOMATION_QUERY


def test_vision_skill_handles_both_intents():
    skill = VisionSkill(_FakeVisionTool())
    ctx1 = SkillContext(message="ocr this image", intent=Intent.VISION_QUERY)
    ctx2 = SkillContext(message="open website example.com", intent=Intent.AUTOMATION_QUERY)

    assert skill.can_handle(ctx1) is True
    assert skill.can_handle(ctx2) is True

    out = skill.execute(ctx1)
    assert out["action"] == "vision"
    assert out["intent"] == Intent.VISION_QUERY.value


def test_vision_tool_path_missing_returns_error_message():
    tool = VisionTool()
    result = tool.execute("ocr /tmp/this_file_does_not_exist_123.png")
    assert result["action"] == "vision"
    assert result["success"] is False
    assert "not found" in result["response"].lower()


def test_vision_tool_uses_analysis_for_image_path(monkeypatch):
    tool = VisionTool()

    def fake_analyze(path: str, question: str | None = None):
        return VisionAnalysisResult(
            summary="Mocked analysis success",
            backend="mock",
            width=100,
            height=50,
            mode="RGB",
            hints=["test"],
        )

    monkeypatch.setattr(tool.vision, "analyze_image", fake_analyze)
    # Using a markdown path because VisionTool path extraction whitelists known OCR/image extensions.
    result = tool.execute("analyze image README.md")
    assert result["action"] == "vision"
    assert result["success"] is True
    assert "mocked analysis" in result["response"].lower()
