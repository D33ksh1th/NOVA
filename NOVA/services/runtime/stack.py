"""Phase 2 stack manifest for NOVA orchestration.

This module captures the recommended provider stack and the delivery order
for laptop-first implementation. The rest of the system can inspect this
manifest instead of hard-coding roadmap decisions in multiple places.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class StackComponent:
    category: str
    provider: str
    purpose: str
    offline: bool = True
    status: str = "planned"
    notes: str = ""


@dataclass(frozen=True)
class DeliveryStep:
    phase: str
    order: int
    title: str
    goal: str
    exit_criteria: list[str] = field(default_factory=list)
    manual_tests: list[str] = field(default_factory=list)


class NovaStackManifest:
    """Single source of truth for the Phase 2 stack and rollout order."""

    def __init__(self):
        self.components = [
            StackComponent("llm.chat", "Llama 3.x / Gemma 3", "general chat and fallback reasoning", notes="Current runtime already uses Ollama-compatible chat models."),
            StackComponent("llm.coding", "Qwen2.5-Coder / DeepSeek Coder", "coding and file-aware generation"),
            StackComponent("llm.reasoning", "DeepSeek-R1", "reflection and harder reasoning"),
            StackComponent("vision", "Qwen2.5-VL + Florence-2", "screen and document understanding"),
            StackComponent("stt", "Whisper.cpp + Silero VAD", "offline speech transcription with activity gating"),
            StackComponent("tts", "Kokoro TTS", "natural speech output"),
            StackComponent("wakeword", "OpenWakeWord", "local wake word activation"),
            StackComponent("speaker", "SpeechBrain + Resemblyzer", "speaker enrollment and identification"),
            StackComponent("emotion", "Wav2Vec2 emotion model", "voice emotion detection"),
            StackComponent("ocr", "PaddleOCR", "document and screen OCR"),
            StackComponent("automation", "Open Interpreter + Playwright", "desktop and browser automation"),
            StackComponent("memory.vector", "Qdrant", "vector search for RAG"),
            StackComponent("memory.graph", "Neo4j", "knowledge graph for user-project-task relations"),
        ]

        self.delivery_steps = [
            DeliveryStep(
                phase="A",
                order=1,
                title="Runtime and model orchestration",
                goal="Make all model/provider choices configurable from a central manifest before deeper integrations.",
                exit_criteria=[
                    "Model routing uses configured stack settings.",
                    "Roadmap and test gates are written in repo.",
                    "No feature implementation depends on hard-coded future provider names.",
                ],
                manual_tests=[
                    "Ask for general chat, coding, and security/reasoning tasks and inspect selected model logs.",
                    "Verify startup still succeeds with default settings.",
                ],
            ),
            DeliveryStep(
                phase="A",
                order=2,
                title="Offline voice core",
                goal="Integrate Whisper.cpp, Silero VAD, Kokoro/Piper TTS, and OpenWakeWord behind the modular voice pipeline.",
                exit_criteria=[
                    "Push-to-talk works with offline STT.",
                    "Wake word is optional and locally processed.",
                    "Three selectable speech styles sound materially different.",
                ],
                manual_tests=[
                    "Wake word: say 'Hey Nova' then a command.",
                    "Push-to-talk: dictate a command and verify transcript accuracy.",
                    "Switch voice style and confirm audible difference.",
                ],
            ),
            DeliveryStep(
                phase="B",
                order=3,
                title="Speaker and conversation intelligence",
                goal="Add speaker enrollment, identification, interruption handling, and emotion-aware delivery.",
                exit_criteria=[
                    "At least one enrolled speaker is recognized.",
                    "Interrupting speech stops output and resumes listening.",
                    "Emotion metadata influences speech planning.",
                ],
                manual_tests=[
                    "Enroll speaker then call /voice/text with speaker metadata.",
                    "Interrupt spoken response with a follow-up command.",
                    "Say urgent vs calm prompts and inspect emotion metadata.",
                ],
            ),
            DeliveryStep(
                phase="C",
                order=4,
                title="Vision, OCR, and desktop automation",
                goal="Add screen understanding, document parsing, and browser/desktop control at laptop scope.",
                exit_criteria=[
                    "NOVA can summarize a screenshot or document.",
                    "NOVA can run a safe browser automation flow.",
                    "OCR extracts text from PDFs/images with acceptable accuracy.",
                ],
                manual_tests=[
                    "Ask 'what am I looking at?' with a provided image/screenshot.",
                    "Run a browser search flow through automation.",
                    "Upload a PDF and request extracted summary.",
                ],
            ),
            DeliveryStep(
                phase="D",
                order=5,
                title="Memory, RAG, and cross-device validation",
                goal="Add durable vector/graph memory and validate all implemented features on laptop then iOS URL access.",
                exit_criteria=[
                    "User/project/task relationships are queryable.",
                    "RAG retrieval improves grounded answers.",
                    "Core flows are re-tested from iOS browser endpoint.",
                ],
                manual_tests=[
                    "Store and recall multi-step user/project memory.",
                    "Ask a document-grounded question and verify sourced answer.",
                    "Open the NOVA URL on iOS and re-run chat/voice-safe flows.",
                ],
            ),
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "components": [asdict(component) for component in self.components],
            "delivery_steps": [asdict(step) for step in self.delivery_steps],
        }


manifest = NovaStackManifest()