from services.voice import VoiceEngine, VoiceState
from services.voice.tts import SpeechSynthesisResult, SpeechSynthesizer


class DummyConversationService:
    def handle(self, message: str):
        return {
            "action": "chat",
            "intent": "chat",
            "response": f"Handled: {message}",
        }


class SilentSynthesizer(SpeechSynthesizer):
    def speak(self, text: str, play: bool = True, style=None, rate=None, pitch=None, voice=None):
        return SpeechSynthesisResult(
            text=text,
            backend="test",
            spoken=False,
            command=f"style={style};rate={rate};pitch={pitch};voice={voice}",
        )


def build_engine() -> VoiceEngine:
    return VoiceEngine(
        conversation_service=DummyConversationService(),
        synthesizer=SilentSynthesizer(voice="Lekha", rate=180, pitch=50),
        enabled=True,
    )


def test_voice_status_reports_modular_components():
    engine = build_engine()
    engine.enroll_speaker("Deekshith", ["Hello NOVA", "Open my calendar"])

    status = engine.status()

    assert status["enabled"] is True
    assert status["modules"]["vad"] == "VoiceActivityDetector"
    assert status["modules"]["speaker"] == "SpeakerRecognizer"
    assert "Deekshith" in status["enrolled_speakers"]


def test_voice_pipeline_enriches_metadata_and_response():
    engine = build_engine()
    engine.enroll_speaker("Deekshith", ["Hello NOVA", "List my files"])

    result = engine.handle_text("Nova list my files!", speak=False, force=True)

    assert result["response"] == "Handled: list my files!"
    assert result["recognition_backend"] == "text"
    assert result["speaker"] == "Deekshith"
    assert result["emotion"] == "excited"
    assert result["language"] == "en"
    assert result["voice"]["metadata"]["wake_word"]["detected"] is True
    assert result["voice"]["metadata"]["speech_plan"]["style"] in {"excited", "personal"}


def test_voice_pipeline_marks_interruption_when_new_turn_arrives_mid_speech():
    engine = build_engine()
    engine.session.state = VoiceState.SPEAKING

    result = engine.handle_text("Nova stop and listen", speak=False, force=True)

    assert result["voice"]["metadata"]["conversation"]["interrupted"] is True
    assert result["voice"]["metadata"]["conversation"]["turn_count"] >= 1


def test_voice_pipeline_accepts_explicit_speaker_metadata():
    engine = build_engine()
    engine.enroll_speaker("Alice", ["Schedule my calendar", "Open my inbox"])

    result = engine.handle_text(
        "Nova what is on my calendar",
        speak=False,
        force=True,
        metadata={"speaker": "Alice"},
    )

    assert result["speaker"] == "Alice"
    assert result["voice"]["metadata"]["speaker"]["recognized"] is True


def test_voice_pipeline_handles_silence_without_calling_brain():
    engine = build_engine()

    result = engine.handle_text("   ", speak=False, force=True)

    assert result["response"] == ""
    assert result["message"] == "No speech activity detected."
    assert result["voice"]["state"] == "idle"


def test_voice_pipeline_ignores_input_without_wake_word_when_not_forced():
    engine = build_engine()

    result = engine.handle_text("what is the weather", speak=False, force=False)

    assert result["response"] == ""
    assert result["message"] == "Wake word not detected."
    assert result["voice"]["state"] == "idle"