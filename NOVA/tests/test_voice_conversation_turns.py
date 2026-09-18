import pytest

from services.voice.wakeword import WakeWordDetector
from services.voice.stream import detect_wake_word, strip_wake_word
from services.voice.stream import is_playback_echo


@pytest.mark.parametrize("prefix", ["Nova", "Hey Nova", "Hi Novah", "Hello Nowa", "Hey No va", "Hey N ova", "HeyNova"])
def test_nova_wake_variants_preserve_command(prefix):
    text = f"{prefix}, check my calendar"
    assert WakeWordDetector().matches(text)
    assert detect_wake_word(text)
    assert strip_wake_word(text) == "check my calendar"


@pytest.mark.parametrize("text", ["never mind", "hey never", "hey over", "innovation", "novacaine", "I read about Nova", "now a meeting", "matrix"])
def test_wake_does_not_match_background_words(text):
    assert not detect_wake_word(text)


def test_interruption_discards_audio_still_being_synthesized(monkeypatch):
    from unittest.mock import Mock
    from services.voice.tts import KokoroSpeechSynthesizer

    synthesizer = KokoroSpeechSynthesizer()
    model = Mock()
    def interrupt_during_synthesis(*args, **kwargs):
        synthesizer._playback_generation += 1
        return [0.0], 24000
    model.create.side_effect = interrupt_during_synthesis
    with pytest.raises(InterruptedError):
        synthesizer._synthesize(model, "Old response", "bm_george", 1.0)


def test_playback_state_is_a_single_property(monkeypatch):
    import sys
    from types import SimpleNamespace
    from services.voice.tts import KokoroSpeechSynthesizer

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(get_stream=lambda: SimpleNamespace(active=True)))
    assert KokoroSpeechSynthesizer().is_speaking is True


def test_echo_rejection_keeps_distinct_follow_up():
    reply = "The meeting is scheduled for tomorrow morning at ten."
    assert is_playback_echo("scheduled for tomorrow morning", reply)
    assert not is_playback_echo("Actually move it to Friday", reply)
    assert not is_playback_echo("Wait include the other project", reply)
    assert not is_playback_echo("", reply)
    assert not is_playback_echo("wait", "Wait a moment while I check.")
    assert not is_playback_echo("yes", "Yes, that is available.")


def test_continuous_speech_is_bounded():
    import numpy as np
    from services.voice.stream import AudioBuffer

    buffer = AudioBuffer()
    audio = np.full(buffer.SAMPLE_RATE * buffer.MAX_UTTERANCE_SEC, 2000, dtype=np.int16)
    assert buffer.add_chunk(audio.tobytes()) is not None
    assert buffer.total_samples == 0


def test_cancel_after_audio_preparation_never_starts_playback(monkeypatch):
    import sys
    from types import SimpleNamespace
    from unittest.mock import Mock
    import numpy as np
    from services.voice.tts import KokoroSpeechSynthesizer

    synthesizer = KokoroSpeechSynthesizer()
    playback = Mock()
    monkeypatch.setitem(sys.modules, "sounddevice", playback)
    monkeypatch.setattr(synthesizer, "_get_kokoro", lambda *args: SimpleNamespace(create=lambda *args, **kwargs: (np.zeros(20), 24000)))
    def prepare(*args):
        synthesizer.interrupt()
        return np.zeros(20), 48000
    monkeypatch.setattr(synthesizer, "_prepare_audio", prepare)
    result = synthesizer.speak_sequence(["Old reply"])
    assert not result.spoken
    assert result.error == "interrupted"
    playback.play.assert_not_called()


def test_cancel_during_model_load_never_synthesizes(monkeypatch):
    from unittest.mock import Mock
    from services.voice.tts import KokoroSpeechSynthesizer

    synthesizer = KokoroSpeechSynthesizer()
    model = Mock()
    def load(*args):
        synthesizer._playback_generation += 1
        return model
    monkeypatch.setattr(synthesizer, "_get_kokoro", load)
    result = synthesizer.speak_sequence(["Old reply"])
    assert result.error == "interrupted"
    model.create.assert_not_called()


def test_interrupt_stops_inflight_playback_without_restarting_it(monkeypatch):
    import sys
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    from unittest.mock import Mock
    import numpy as np
    from services.voice.tts import KokoroSpeechSynthesizer

    started = threading.Event()
    stopped = threading.Event()
    def wait_for_stop():
        stopped.wait(2)
    sounddevice = SimpleNamespace(play=Mock(side_effect=lambda *args, **kwargs: started.set()), wait=wait_for_stop, stop=stopped.set)
    monkeypatch.setitem(sys.modules, "sounddevice", sounddevice)
    synthesizer = KokoroSpeechSynthesizer()
    monkeypatch.setattr(synthesizer, "_prepare_audio", lambda samples, rate: (samples, rate))
    monkeypatch.setattr(synthesizer, "_get_kokoro", lambda *args: SimpleNamespace(create=lambda *args, **kwargs: (np.zeros(20), 24000)))
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(synthesizer.speak_sequence, ["Original reply"])
        assert started.wait(2)
        synthesizer.interrupt()
        result = pending.result(timeout=2)
    assert result.error == "interrupted"
    assert not result.spoken
    sounddevice.play.assert_called_once()


def test_interrupt_only_terminates_owned_fallback_process(monkeypatch):
    import sys
    from unittest.mock import Mock
    from services.voice.tts import KokoroSpeechSynthesizer

    monkeypatch.setitem(sys.modules, "sounddevice", Mock())
    synthesizer = KokoroSpeechSynthesizer()
    process = Mock()
    process.poll.return_value = None
    synthesizer._playback_process = process
    monkeypatch.setattr(synthesizer, "stop", Mock(side_effect=AssertionError("Must not use broad process-name stop")))
    assert synthesizer.interrupt()
    process.terminate.assert_called_once()
    process.wait.assert_called_once_with(timeout=0.5)


def test_duplex_echo_is_ignored_and_follow_up_stops_before_delivery(monkeypatch):
    import asyncio
    import json
    import sys
    from types import SimpleNamespace
    import numpy as np
    from services.voice import stream

    order = []
    engine = SimpleNamespace(
        session=SimpleNamespace(state=SimpleNamespace(value="speaking")),
        synthesizer=SimpleNamespace(is_speaking=True),
        stop_speaking=lambda: order.append("stopped"),
        has_active_enrollment_session=lambda: False,
    )
    monkeypatch.setitem(sys.modules, "packages.registry", SimpleNamespace(registry=SimpleNamespace(voice_engine=engine)))
    async def preload():
        return None
    transcripts = iter(["scheduled for tomorrow morning", "Actually include Friday too"])
    async def transcribe(*args):
        return next(transcripts)
    monkeypatch.setattr(stream, "_get_whisper", preload)
    monkeypatch.setattr(stream, "transcribe_audio", transcribe)
    monkeypatch.setattr(stream.AudioBuffer, "add_chunk", lambda *args: np.ones(20, dtype=np.int16))
    def control(kind, **kwargs):
        return {"text": json.dumps({"type": kind, **kwargs})}
    messages = iter([
        control("config", duplex=True), control("start_conversation"),
        control("playback_started", text="The meeting is scheduled for tomorrow morning."),
        {"bytes": b"audio"}, {"bytes": b"audio"}, {"type": "websocket.disconnect"},
    ])
    class Socket:
        async def accept(self):
            pass
        async def receive(self):
            return next(messages)
        async def send_json(self, event):
            order.append(event)
    asyncio.run(stream.handle_voice_stream(Socket()))
    delivered = [event for event in order if isinstance(event, dict) and event["type"] == "transcript"]
    assert len(delivered) == 1
    assert delivered[0]["text"] == "Actually include Friday too"
    assert order.index("stopped") < order.index({"type": "barge_in"}) < order.index(delivered[0])


@pytest.mark.parametrize("cancelled", [False, True])
def test_speech_route_waits_and_reports_actual_completion(monkeypatch, cancelled):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from services.gateway import routes
    from services.voice.tts import SpeechSynthesisResult

    engine = Mock()
    engine._speech_generation = 0
    engine.resolve_voice_preferences.return_value = {}
    completed = []
    def speak(*args, **kwargs):
        completed.append(True)
        if cancelled:
            engine._speech_generation += 1
        return SpeechSynthesisResult(text="Reply", backend="fake", spoken=not cancelled)
    engine.synthesizer.speak_sequence.side_effect = speak
    monkeypatch.setattr(routes, "registry", SimpleNamespace(voice_engine=engine))
    monkeypatch.setattr(routes, "bus", Mock())
    result = routes.voice_speak(routes.VoiceSpeakRequest(text="Reply", speak=True))
    assert completed == [True]
    assert result["spoken"] is not cancelled
    assert result["success"] is not cancelled
    assert result["backend"] == "fake"
    assert engine.session.touch.call_count == (1 if cancelled else 2)


@pytest.mark.parametrize("success,playback_state", [(True, "playing"), (True, "paused"), (False, "unknown")])
def test_voice_text_preserves_music_outcome(monkeypatch, success, playback_state):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from starlette.requests import Request
    from services.gateway import routes

    engine = Mock()
    engine.resolve_voice_preferences.return_value = {}
    engine.handle_text.return_value = {
        "enabled": True, "state": "idle", "response": "Playback result",
        "action": "music_playback", "success": success, "playback_state": playback_state,
    }
    monkeypatch.setattr(routes, "registry", SimpleNamespace(voice_engine=engine))
    monkeypatch.setattr(routes, "logger", Mock())
    monkeypatch.setattr(routes, "_should_block_sensitive_request", lambda text: False)
    request = Request({"type": "http", "method": "POST", "path": "/voice/text", "headers": []})
    result = routes.voice_text(routes.VoiceTextRequest(text="Play music", speak=False), request)
    payload = routes.VoiceResponse.model_validate(result.model_dump()).model_dump()
    assert payload["success"] is success
    assert payload["playback_state"] == playback_state