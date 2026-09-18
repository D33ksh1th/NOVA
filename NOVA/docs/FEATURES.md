# NOVA — Feature Reference

> Personal AI Sentinel · JARVIS-class · All features available via voice or chat

---

## Voice & Persona

| Feature | Command | Description |
|---|---|---|
| Wake word | "Hey Matrix" / "Hey Nova" | Activates voice conversation mode |
| JARVIS voice | "switch to jarvis" | British male voice, addresses you as "sir" |
| FRIDAY voice | "switch to friday" | British female voice, addresses you as "boss" |
| DEVI voice | "switch to devi" | Indian female voice, addresses you as "sir" |
| Voice enrollment | "enroll my voice" | Multi-step voice profile enrollment via chat |
| Quick enroll | "enroll me as Deekshith" | One-step instant enrollment |
| Barge-in | Speak while Nova talks | Interrupts Nova mid-sentence, switches to listening |
| Enrolled users | "list enrolled voices" | Shows all enrolled voice profiles |
| Echo suppression | Automatic | Nova doesn't hear/transcribe its own TTS output |

## Greetings & Awareness

| Feature | Command | Description |
|---|---|---|
| Time-aware greeting | Automatic on first interaction | "Good morning, sir" / "Good evening, sir" based on time |
| Admin recognition | Automatic when gate enabled | Greets admin by name with "sir"/"boss" prefix |
| Capabilities | "what can you do" | Lists all Nova features instantly |
| System status | "system status" / "system vitals" | CPU, RAM, disk, battery, LLM, voice, security status |
| Who are you | "who are you" | Nova introduces itself |

## Chat & Intelligence

| Feature | Command | Description |
|---|---|---|
| General chat | Any question | Routes to gemma4:12b LLM for reasoning |
| Brevity budget | Automatic | Spoken: max 2 sentences. Long answers shown in chat only |
| Conclusion-first | Automatic | Leads with the answer, then the reasoning |
| Code help | "write a python script for..." | Routes to LLM with coding prompt |
| Calculator | "what is 245 * 18" | Instant math without LLM |

## Knowledge & Memory

| Feature | Command | Description |
|---|---|---|
| Remember facts | "remember that the DB rotates on Fridays" | Stores in persistent semantic memory |
| Recall facts | "what do you know about deployment" | Searches stored notes |
| List notes | "show my notes" | Lists all stored memories |
| Forget | "forget about the old API key" | Deletes matching stored notes |

## Clipboard Intelligence

| Feature | Command | Description |
|---|---|---|
| Read clipboard | "what did I copy" | Shows clipboard content and type |
| Error analysis | "explain this error" | Analyzes error in clipboard, explains fix via LLM |
| Code review (clipboard) | "review this code" | Reviews clipboard code for issues via LLM |
| URL detection | Auto | Detects URLs in clipboard |
| Long text summary | Auto | Summarizes long clipboard text via LLM |

## Screen Awareness

| Feature | Command | Description |
|---|---|---|
| Screen capture | "what's on my screen" | Captures screen, analyzes with VLM (qwen2.5-vl) |
| Error detection | "what error is showing" | Focuses analysis on errors visible on screen |
| Screen summary | "summarize my screen" | Brief 2-3 sentence screen summary |
| Read screen | "read my screen" | Transcribes main text content from screen |

*Requires Screen Recording permission in System Settings*

## Code Review (Git)

| Feature | Command | Description |
|---|---|---|
| Review commit | "review my last commit" | Gets git diff, LLM reviews for bugs/security |
| Show changes | "what did I change" | Shows recent git changes |
| Check diff | "check my changes" | Same as review |

## Security

| Feature | Command | Description |
|---|---|---|
| Security scan | "run a security scan" | Triggers local host security scan |
| Security status | "security status" | Shows findings, agents, assets count |
| Anomaly detection | Automatic (background) | Layer 1: EWMA statistical baseline, Layer 2: Isolation Forest ML, Layer 3: LLM triage |
| Finding dedup | Automatic | Fingerprint-based, auto-suppresses after 2 repeats |
| Host telemetry | Automatic (every 5 min) | CPU, memory, processes, ports, connections, packages |
| Network discovery | Configurable | ARP + TCP probe for subnet asset discovery |
| SBOM/CBOM/HBOM | Automatic | Software, cryptographic, and hardware bill of materials |

## Face Recognition

| Feature | Command | Description |
|---|---|---|
| Recognize face | "recognize me" | Captures camera, identifies via InsightFace |
| Face enrollment | Via Vision page | Enroll face profile with guided framing |
| Identity linking | Automatic | Links face and voice profiles by name |
| Presence detection | Auto (Vision page) | Detects admin presence, gates sensitive actions |

*Requires camera permission and Vision page open*

## Email (Gmail)

| Feature | Command | Description |
|---|---|---|
| Gmail status | "gmail status" | Shows authentication and inbox status |
| Read inbox | "check my email" | Lists recent unread messages |
| Read message | "read message [id]" | Shows full email content |
| Send email | "send email to..." | Composes and sends via Gmail |
| Mail monitoring | Automatic (background) | Polls Gmail every 60s, notifies on new messages |

*Requires Gmail OAuth setup*

## System & Device

| Feature | Command | Description |
|---|---|---|
| Time | "what time is it" | Current time (instant, no LLM) |
| Weather | "what's the weather" | Current weather for your location |
| Location | "where am I" | Current geolocation |
| System info | "battery status" / "cpu usage" | Device metrics |
| Connected devices | Automatic polling | Shows Bluetooth/wired devices |
| Music control | "play music" | Controls macOS Music app |

## Shell & Files

| Feature | Command | Description |
|---|---|---|
| Run command | "run ls -la" | Executes shell command (Tier 2: requires confirmation) |
| File operations | "list files in Downloads" | File system operations (Tier 1: announced) |
| Terminal tool | Via brain routing | Direct shell access with action gate |

## Reminders

| Feature | Command | Description |
|---|---|---|
| Set reminder | "remind me in 30 minutes to check the build" | Timed reminder with TTS notification |
| Web search | "search for kubernetes best practices" | Web search via configured provider |

## Proactive Features

| Feature | When | Description |
|---|---|---|
| Morning brief | 6-10 AM (once/day) | System health + unread emails + security findings |
| Evening summary | 6-9 PM (once/day) | Day's activity: voice interactions, mail, security events |
| Notification batching | Automatic | Groups low-priority notifications into one summary |
| DND mode | "do not disturb" or API | Suppresses non-critical notifications (default 11 PM–7 AM) |
| Presence gating | Automatic | Only speaks when admin face is detected at desk |
| Interruption limiting | Automatic | Max 8 interruptions per hour |

## App Context

| Feature | When | Description |
|---|---|---|
| App tracking | Background (every 5s) | Detects which app is in foreground (VS Code, Terminal, browser, etc.) |
| Context events | Automatic | Publishes app-switch events on the bus |

*Requires Accessibility permission in System Settings*

## Architecture

| Component | Technology |
|---|---|
| Backend | FastAPI + Python 3.12 |
| LLM | Ollama (gemma4:12b local) |
| TTS | Kokoro-ONNX (24kHz → 48kHz resampled) |
| STT | faster-whisper (local) |
| Speaker ID | SpeechBrain ECAPA-TDNN (192-dim) |
| Face ID | InsightFace |
| Event bus | SQLite-backed persistent bus with subject wildcards |
| State store | SQLite (entities, episodic/semantic/procedural memory, audit log) |
| Desktop app | Tauri + React + TypeScript |
| Anomaly detection | EWMA + Isolation Forest + LLM triage |
| Action gate | 3-tier (auto / announce / confirm) with blocked command list |

## API Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Health check |
| `GET /system` | Service health |
| `POST /chat` | Chat (text) |
| `POST /voice/text` | Voice pipeline (text + optional audio) |
| `POST /voice/speak` | TTS playback |
| `POST /voice/stop` | Stop speaking |
| `POST /voice/persona?persona=jarvis` | Switch voice persona |
| `GET /voice/persona` | Current persona |
| `GET /voice/status` | Voice engine status |
| `GET /voice/speakers` | Enrolled speakers |
| `GET /security/status` | Security center status |
| `POST /security/scan` | Trigger security scan |
| `GET /security/findings` | Current findings |
| `GET /events/replay` | Replay bus events |
| `GET /events/stats` | Event bus statistics |
| `GET /notifications` | Recent notifications |
| `GET /notifications/stats` | Notification policy stats |
| `POST /notifications/dnd` | Toggle DND |
| `GET /actions/pending` | Pending Tier 2 actions |
| `POST /actions/confirm/{id}` | Confirm action |
| `GET /actions/tools` | Tool registry schemas |
| `GET /actions/audit` | Action audit trail |
| `GET /state/entities` | Entity store |
| `GET /state/episodes` | Episodic memory |
| `GET /state/audit` | Full audit log |
| `GET /mobile` | Mobile chat UI |

## Settings (.env)

| Key | Default | Description |
|---|---|---|
| `CHAT_MODEL` | gemma4:12b | Ollama chat model |
| `KOKORO_VOICE` | bm_lewis | Default TTS voice |
| `KOKORO_SPEED` | 0.94 | TTS playback speed |
| `WAKE_WORD` | Nova | Wake word trigger |
| `VOICE_RECOGNITION_GATE` | True | Block unrecognized voices |
| `ENABLE_VISION` | True | Enable camera/face features |
| `MAX_TOKENS` | 256 | LLM response length limit |
| `TEMPERATURE` | 0.5 | LLM creativity |
| `API_HOST` | 0.0.0.0 | Server bind address |
| `API_PORT` | 8000 | Server port |
