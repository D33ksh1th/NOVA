from unittest.mock import Mock

import numpy as np
import pytest

from services.voice.tts import KokoroSpeechSynthesizer
from services.voice.speech_planner import SpeechPlanner
from services.voice.speech_text import prepare_speech_text


@pytest.mark.parametrize("voice,language", [("bm_george", "en-gb"), ("bf_emma", "en-gb"), ("af_heart", "en-us"), ("hf_alpha", "hi")])
@pytest.mark.parametrize("sequence", [False, True])
def test_neural_pronunciation_matches_voice(monkeypatch, voice, language, sequence):
    model = Mock()
    model.create.return_value = (np.zeros(240, dtype=np.float32), 24000)
    synthesizer = KokoroSpeechSynthesizer(kokoro_voice=voice, kokoro_speed=1.0)
    monkeypatch.setattr(synthesizer, "_get_kokoro", lambda *args: model)
    if sequence:
        result = synthesizer.speak_sequence(["All systems ready.", "What shall we tackle?"], play=False)
    else:
        result = synthesizer.speak("All systems ready.", play=False)
    assert result.backend == "kokoro" and not result.error
    assert model.create.call_args.kwargs["lang"] == language
    assert model.create.call_args.kwargs["voice"] == voice
    model.create.assert_called_once()


def test_speech_cleanup_preserves_values_and_removes_display_markup():
    text = "## Status\n- **Battery:** 87.5%\n- Meeting at 10:30; budget $1,500.\n\nRead [the report](https://example.com/report).\n```python\nprint('private code')\n```"
    spoken = prepare_speech_text(text)
    assert spoken == "Status. Battery: 87.5%. Meeting at 10:30; budget $1,500. Read the report."
    assert SpeechPlanner()._normalize_text(text) == spoken
    assert prepare_speech_text(spoken) == spoken


def test_audio_resampling_preserves_duration_and_softens_boundaries():
    original = np.ones(24000, dtype=np.float32) * 1.1
    audio, rate = KokoroSpeechSynthesizer._prepare_audio(original, 24000)
    assert rate == 48000 and len(audio) == 48000
    assert audio[0] == audio[-1] == 0
    assert np.max(np.abs(audio)) <= 0.980001
    assert np.isfinite(audio).all()
    assert np.all(original == np.float32(1.1))


@pytest.mark.parametrize("samples,rate", [([], 24000), ([float("nan")], 24000), ([1.0], 0)])
def test_invalid_audio_is_rejected(samples, rate):
    with pytest.raises(ValueError, match="Invalid neural speech audio"):
        KokoroSpeechSynthesizer._prepare_audio(samples, rate)


def test_voice_and_pace_controls_are_honored_without_compounded_slowdown():
    synthesizer = KokoroSpeechSynthesizer(kokoro_voice="bm_george", kokoro_speed=1.0)
    voice, speed = synthesizer._resolve_voice_and_speed("calm", "english_jarvis", 180)
    assert voice == "bm_george" and speed == pytest.approx(0.98)
    assert synthesizer._severity_speed(speed, 0) == speed
    assert synthesizer._resolve_voice_and_speed("warm", "english_friday", 180)[0] == "bf_emma"
    assert synthesizer._resolve_voice_and_speed("natural", None, 160)[1] < synthesizer._resolve_voice_and_speed("natural", None, 200)[1]
    assert synthesizer._resolve_voice_and_speed("excited", None, 999)[1] == 1.2
    assert synthesizer._resolve_voice_and_speed("calm", None, 1)[1] == 0.85
    assert synthesizer._resolve_voice_and_speed(voice="unknown")[0] == "bm_george"


def test_personality_keeps_wit_optional_and_results_truthful():
    from services.llm.prompts import PromptBuilder
    from services.personality.engine import PersonalityEngine

    prompt = PromptBuilder().build("How is the research going?")
    assert "Never force a joke" in prompt
    assert "No jokes during distress" in prompt
    assert "tool result confirms it" in prompt
    assert 'Do not routinely call the user "sir" or "boss"' in prompt
    context = PersonalityEngine().build_context()
    assert "Occasional dry humour" in context and "Avoid jokes during distress" in context
    assert "without its result confirming success" in context


def test_explicit_voice_preferences_override_model_defaults():
    from services.voice.engine import VoiceEngine

    engine = VoiceEngine.__new__(VoiceEngine)
    engine._voice_preferences = {"voice_mode": "human", "accent_profile": "english_jarvis", "voice": "nova", "style": "calm", "rate": 170, "pitch": 46}
    engine._voice_mode_defaults = {"human": {"style": "calm", "rate": 170, "pitch": 46}}
    engine._accent_profiles = {"english_jarvis": {"style": "calm", "rate": 166, "pitch": 44}}
    engine._voice_model_presets = {"nova": {"style": "natural", "rate": 174, "pitch": 46}}
    preferences = engine.resolve_voice_preferences({"voice": "nova", "style": "warm", "rate": 190, "pitch": 52})
    assert preferences["rate"] == 190 and preferences["style"] == "warm" and preferences["pitch"] == 52


def test_jarvis_persona_replaces_female_accent_preferences(monkeypatch):
    from services.gateway import routes

    engine = Mock()
    engine.synthesizer = KokoroSpeechSynthesizer(kokoro_voice="bf_emma")
    monkeypatch.setattr(routes.registry, "voice_engine", engine)
    monkeypatch.setattr(KokoroSpeechSynthesizer, "_active_persona", "friday")

    result = routes.set_voice_persona("jarvis")

    assert result["voice"] == "bm_george"
    preferences = engine.set_voice_preferences.call_args.args[0]
    assert preferences["accent_profile"] == "english_jarvis"
    assert preferences["voice_mode"] == "human"
    assert engine.synthesizer._resolve_voice_and_speed(voice=preferences["accent_profile"])[0] == "bm_george"


def test_default_synthesizer_uses_british_male_voice():
    assert KokoroSpeechSynthesizer()._resolve_voice_and_speed()[0] == "bm_george"


@pytest.mark.parametrize("requested,expected", [("english_lessac", "bm_george"), ("english_jarvis", "bm_george"), ("bm_george", "bm_george"), ("english_amy", "bf_emma"), ("english_friday", "bf_emma")])
def test_explicit_voice_selection_does_not_use_configured_fallback(monkeypatch, requested, expected):
    model = Mock()
    model.create.return_value = (np.zeros(240, dtype=np.float32), 24000)
    synthesizer = KokoroSpeechSynthesizer(kokoro_voice="bf_emma")
    monkeypatch.setattr(synthesizer, "_get_kokoro", lambda *args: model)
    result = synthesizer.speak_sequence(["Your report is ready."], play=False, voice=requested)
    assert not result.error
    assert model.create.call_args.kwargs["voice"] == expected
    assert model.create.call_args.kwargs["lang"] == "en-gb"


@pytest.mark.parametrize("first_response", [True, False])
def test_normal_voice_answer_does_not_gain_a_greeting(first_response):
    from services.voice.pipeline import VoicePipeline

    pipeline = VoicePipeline.__new__(VoicePipeline)
    assert pipeline._with_admin_intro("The meeting starts at ten.", first_response) == "The meeting starts at ten."
    assert not pipeline._is_simple_greeting("What time is my meeting?")
    assert pipeline._is_simple_greeting("Good evening!")


def test_runtime_starts_with_jarvis_accent():
    from services.voice.engine import VoiceEngine

    factory = Mock()
    engine = VoiceEngine(conversation_service=Mock(), component_factory=factory)
    assert engine.get_voice_preferences()["accent_profile"] == "english_jarvis"


def test_thinking_tone_does_not_replace_global_speech_playback(monkeypatch):
    import sys
    from services.voice import earcon

    device = Mock()
    output = Mock()
    device.OutputStream.return_value.__enter__ = Mock(return_value=output)
    device.OutputStream.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setitem(sys.modules, "sounddevice", device)
    monkeypatch.setattr(earcon, "_get_earcon_audio", lambda: (np.zeros(240), 24000))
    earcon.play_thinking_earcon()
    output.write.assert_called_once()
    device.play.assert_not_called()
    device.stop.assert_not_called()


def test_cancelled_thinking_callback_cannot_start_after_response(monkeypatch):
    from services.voice import earcon

    play = Mock()
    monkeypatch.setattr(earcon, "play_thinking_earcon", play)
    monkeypatch.setattr(earcon.threading, "Timer", Mock())
    timer = earcon.ThinkingEarconTimer()
    timer.start()
    generation = timer._generation
    timer.cancel()
    timer._play(generation)
    play.assert_not_called()


def test_playback_uses_high_latency_and_never_replays_after_output_failure(monkeypatch):
    import sys

    device = Mock()
    device.wait.side_effect = RuntimeError("device lost after playback started")
    monkeypatch.setitem(sys.modules, "sounddevice", device)
    synth = KokoroSpeechSynthesizer()
    fallback = Mock()
    monkeypatch.setattr(synth, "_play_audio", fallback)
    with pytest.raises(RuntimeError, match="device lost"):
        synth._play_samples(np.zeros(240), 48000, 0)
    assert device.play.call_args.kwargs["latency"] == "high"
    fallback.assert_not_called()


@pytest.mark.parametrize("question,is_greeting", [("What time is my meeting?", False), ("Check tomorrow too", False), ("Hello", True)])
def test_pipeline_greets_only_greetings_and_sends_selected_accent(monkeypatch, question, is_greeting):
    import threading
    from types import SimpleNamespace
    from services.voice import pipeline as module
    from services.voice.models import SpeakerRecognitionResult, VoiceInputFrame
    from services.voice.state import VoiceSession
    from services.voice.wakeword import WakeWordDetector

    conversation = Mock()
    conversation.handle.return_value = {"response": "The meeting starts at ten."}
    recognizer = Mock()
    recognizer.recognize.return_value = SimpleNamespace(text=question, backend="fake", confidence=1.0, error="")
    synthesizer = Mock(rate=180, pitch=50, is_speaking=False)
    synthesizer.speak_sequence.return_value = SimpleNamespace(backend="fake")
    profiles = Mock()
    profiles.all_profiles.return_value = []
    monkeypatch.setattr(module, "bus", Mock())
    monkeypatch.setattr(module, "logger", Mock())
    monkeypatch.setattr(module, "ThinkingEarconTimer", Mock())
    monkeypatch.setattr(module, "_admin_greeting", lambda: "Good evening.")
    monkeypatch.setattr(threading, "Thread", lambda target, **kwargs: SimpleNamespace(start=target))
    pipeline = module.VoicePipeline(conversation, recognizer, synthesizer, WakeWordDetector(), Mock(), speaker_registry=profiles, device_manager=Mock())
    pipeline.speaker_recognizer = Mock()
    pipeline.speaker_recognizer.recognize.return_value = SpeakerRecognitionResult(speaker="Test", role="admin", recognized=True)
    frame = VoiceInputFrame(source=question, speak=True, force_wake=True, metadata={"voice_preferences": {"voice": "english_amy", "accent_profile": "english_jarvis"}})
    result = pipeline.process(frame, VoiceSession())
    assert result["response"] == ("Good evening." if is_greeting else "The meeting starts at ten.")
    assert synthesizer.speak_sequence.call_args.kwargs["voice"] == "english_jarvis"
    assert conversation.handle.call_count == (0 if is_greeting else 1)


def test_concurrent_speech_does_not_replace_an_active_buffer(monkeypatch):
    import sys
    import threading
    from concurrent.futures import ThreadPoolExecutor

    first_started = threading.Event()
    second_waiting = threading.Event()
    finish_first = threading.Event()
    output_lock = threading.Lock()
    class ObservedLock:
        def __enter__(self):
            if first_started.is_set():
                second_waiting.set()
            output_lock.acquire()
        def __exit__(self, *args):
            output_lock.release()
    device = Mock()
    device.play.side_effect = lambda *args, **kwargs: first_started.set()
    def wait():
        assert finish_first.wait(3)
        return None
    device.wait.side_effect = wait
    monkeypatch.setitem(sys.modules, "sounddevice", device)
    synth = KokoroSpeechSynthesizer()
    synth._output_lock = ObservedLock()
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(synth._play_samples, np.zeros(240), 48000, 0)
        try:
            assert first_started.wait(3)
            second = executor.submit(synth._play_samples, np.zeros(240), 48000, 0)
            assert second_waiting.wait(3)
            assert device.play.call_count == 1
        finally:
            finish_first.set()
        first.result(timeout=3)
        second.result(timeout=3)
    assert device.play.call_count == 2