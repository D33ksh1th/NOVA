import subprocess

from services.voice.stt import SpeechRecognizer


class _Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_stt_keeps_text_mode_for_non_file_source():
    recognizer = SpeechRecognizer(language="en")

    result = recognizer.recognize("  hello   nova  ")

    assert result.backend == "text"
    assert result.text == "hello nova"
    assert result.error == ""


def test_stt_audio_requires_whisper_configuration(tmp_path):
    audio = tmp_path / "sample.wav"
    audio.write_text("dummy")

    recognizer = SpeechRecognizer(language="en")
    result = recognizer.recognize(str(audio))

    assert result.backend == "audio"
    assert result.text == ""
    assert "binary" in result.error.lower()


def test_stt_whisper_reads_generated_text_file(tmp_path, monkeypatch):
    audio = tmp_path / "sample.wav"
    audio.write_text("dummy")

    captured = {}

    def fake_run(cmd, capture_output, text, timeout):
        captured["cmd"] = cmd
        output_prefix = cmd[cmd.index("-of") + 1]
        with open(f"{output_prefix}.txt", "w", encoding="utf-8") as fh:
            fh.write("hello from whisper")
        return _Completed(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    recognizer = SpeechRecognizer(
        language="en",
        whisper_binary="/usr/local/bin/whisper-cli",
        whisper_model="/models/ggml-base.en.bin",
        whisper_args="--threads 4",
    )
    result = recognizer.recognize(str(audio))

    assert result.backend == "whisper.cpp"
    assert result.text == "hello from whisper"
    assert result.error == ""
    assert "-m" in captured["cmd"]
    assert "/models/ggml-base.en.bin" in captured["cmd"]


def test_stt_whisper_falls_back_to_legacy_command(tmp_path, monkeypatch):
    audio = tmp_path / "sample.wav"
    audio.write_text("dummy")

    calls = []

    def fake_run(cmd, capture_output, text, timeout):
        calls.append(cmd)
        if len(calls) == 1:
            return _Completed(returncode=2, stdout="", stderr="unknown argument")
        return _Completed(returncode=0, stdout="hello from legacy mode", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    recognizer = SpeechRecognizer(
        language="en",
        whisper_binary="/usr/local/bin/whisper-cli",
        whisper_model="/models/ggml-base.en.bin",
    )
    result = recognizer.recognize(str(audio))

    assert len(calls) == 2
    assert "--language" in calls[1]
    assert result.backend == "whisper.cpp"
    assert result.text == "hello from legacy mode"
