## NOVA Phase 2 Roadmap

For the broader personal companion, delegated coding, endpoint fleet, BOM and MySQL vulnerability intelligence programme, see the [Companion and Security Platform Roadmap](COMPANION_PLATFORM_ROADMAP.md). The laptop-first milestones below remain the local implementation reference.

Principle: NOVA is the orchestrator. Best-of-breed components are plugins, not Brain internals.

### Scope Guard

This roadmap is laptop-first. Each phase must be implemented and tested on desktop before moving to the next phase.
After the laptop flow is stable, the same URL and critical user journeys will be tested from iOS.

### Delivery Order

1. Runtime and model orchestration
Goal: centralize stack configuration and remove hard-coded provider choices.
Exit criteria:
- model routing uses settings-driven names
- roadmap and provider stack are stored in repo
- current features still work with default models
Sample tests:
- ask a chat query and confirm the chat model is selected in logs
- ask a coding query and confirm the code model is selected
- ask a reflection/review query and confirm the reasoning model is selected

2. Offline voice core
Goal: integrate Whisper.cpp, Silero VAD, Kokoro/Piper TTS, and OpenWakeWord through the modular voice system.
Exit criteria:
- push-to-talk works with offline STT
- wake word stays local
- speech styles are selectable and audibly different
Sample tests:
- push-to-talk -> "Nova what is my IP address"
- wake word -> "Hey Nova open downloads"
- switch between Natural/Warm/Clear and compare output tone

3. Speaker and conversation intelligence
Goal: add enrollment, recognition, interruption, and emotion-aware response planning.
Exit criteria:
- at least one speaker can be enrolled and recognized
- speech can be interrupted cleanly
- emotional hints affect speech planning metadata
Sample tests:
- enroll a speaker via `/voice/speakers/enroll`
- call `/voice/text` with `speaker` set and verify recognition metadata
- interrupt a spoken reply and verify the system returns to listening

4. Vision, OCR, and desktop automation
Goal: add laptop-level screen understanding, OCR, and safe browser/desktop automation.
Exit criteria:
- image/screenshot explanation works
- OCR can summarize a PDF/image
- browser automation can complete a safe flow
Sample tests:
- ask "what am I looking at?" for a screenshot
- upload a PDF and request a summary
- run a safe browser search flow and verify output

5. Memory, RAG, and iOS verification
Goal: add durable vector/graph memory and re-test all critical flows from iOS.
Exit criteria:
- vector retrieval improves grounded responses
- graph memory stores user/project/task relationships
- core desktop flows pass again on iOS URL access
Sample tests:
- ask a document-grounded question after ingestion
- verify user/project/task relationship recall
- open the running app from iPhone and re-run chat/voice-safe flows

### Recommended Stack

| Category | Recommended Provider |
| --- | --- |
| LLM runtime | Ollama |
| Chat | Llama 3.x / Gemma 3 |
| Coding | Qwen2.5-Coder / DeepSeek Coder |
| Reasoning | DeepSeek-R1 |
| Vision | Qwen2.5-VL + Florence-2 |
| STT | Whisper.cpp |
| VAD | Silero VAD |
| TTS | Kokoro TTS |
| Wake word | OpenWakeWord |
| Speaker recognition | SpeechBrain + Resemblyzer |
| Emotion | Wav2Vec2-based emotion model |
| OCR | PaddleOCR |
| Desktop automation | Open Interpreter + Playwright |
| Vector DB | Qdrant |
| Knowledge graph | Neo4j |

### Rule For Progression

Do not begin the next phase until:

1. implementation is complete for current phase
2. desktop/manual tests are run and logged
3. any critical failures are fixed
4. user confirms moving to the next phase
