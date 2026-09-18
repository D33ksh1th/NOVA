"""
Global application settings.

Every service imports this file.

Nothing should ever read environment variables directly.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --------------------------------------------------
    # Application
    # --------------------------------------------------

    APP_NAME: str = "NOVA"

    VERSION: str = "0.1.0"

    ENVIRONMENT: str = "development"

    DEBUG: bool = True

    LOG_LEVEL: str = "INFO"

    API_HOST: str = "127.0.0.1"

    API_PORT: int = 8000

    # --------------------------------------------------
    # Database
    # --------------------------------------------------

    DATABASE_URL: str = "sqlite:///nova.db"

    # --------------------------------------------------
    # LLM Configuration
    # --------------------------------------------------

    LLM_PROVIDER: str = "ollama"

    OLLAMA_HOST: str = "http://localhost:11434"

    CHAT_MODEL: str = "gemma3:12b"

    CODE_MODEL: str = "qwen3:8b"

    AGENT_RUNTIME_ENABLED: bool = True
    AGENT_RUNTIME_MODEL: str = "qwen3:8b"
    AGENT_RUNTIME_MODEL_URL: str = "http://127.0.0.1:11434"
    AGENT_RUNTIME_MODEL_DIGEST: str = "500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41"
    AGENT_RUNTIME_TOKENIZER_PATH: str = "models/qwen3-8b-tokenizer"
    AGENT_RUNTIME_AUDIT_PATH: str = "data/agent_runtime/audit.jsonl"
    AGENT_RUNTIME_REPORTS_PATH: str = "data/agent_runtime/reports.sqlite3"
    AGENT_RUNTIME_REPOSITORY_ENABLED: bool = True
    AGENT_RUNTIME_READ_PAGES: bool = True

    REASONING_MODEL: str = "deepseek-r1:latest"

    VISION_MODEL: str = "qwen2.5-vl:latest"

    VISION_MODEL_NAME: str = "qwen2.5-vl:latest"

    EMBEDDING_MODEL: str = "nomic-embed-text"

    STT_PROVIDER: str = "whisper.cpp"

    WHISPER_CPP_BINARY: str = ""

    WHISPER_CPP_MODEL: str = ""

    WHISPER_CPP_ARGS: str = ""

    WHISPER_MODEL_SIZE: str = "tiny.en"

    VAD_PROVIDER: str = "silero-vad"

    SILERO_VAD_MODEL_PATH: str = ""

    SILERO_VAD_THRESHOLD: float = 0.5

    SILERO_VAD_MIN_SPEECH_MS: int = 250

    TTS_PROVIDER: str = "kokoro"

    KOKORO_TTS_COMMAND: str = ""  # legacy CLI mode — ignored when kokoro-onnx is available

    KOKORO_VOICE: str = "bm_george"  # British male, authoritative — JARVIS voice

    KOKORO_SPEED: float = 1.0  # natural pace for clear delivery

    PIPER_TTS_COMMAND: str = ""

    WAKEWORD_PROVIDER: str = "openwakeword"

    OPENWAKEWORD_MODEL_PATH: str = ""

    OPENWAKEWORD_THRESHOLD: float = 0.5

    OPENWAKEWORD_WAKEWORD_NAME: str = "hey_nova"

    SPEAKER_PROVIDER: str = "speechbrain+resemblyzer"

    SPEAKER_SIMILARITY_THRESHOLD: float = 0.60

    # When False, skip the speaker identity gate — allow all input through.
    # Enable after enrollment is confirmed working with real voice samples.
    VOICE_RECOGNITION_GATE: bool = True

    EMOTION_PROVIDER: str = "wav2vec2-emotion"

    EMOTION_MODEL_NAME: str = "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"

    FACE_IDENTITY_THRESHOLD: float = 0.58

    OCR_PROVIDER: str = "paddleocr"

    AUTOMATION_PROVIDER: str = "open-interpreter+playwright"

    AUTOMATION_HEADLESS: bool = True

    VECTOR_DB_PROVIDER: str = "qdrant"

    KNOWLEDGE_GRAPH_PROVIDER: str = "neo4j"

    PHASE2_CURRENT_PHASE: str = "A"

    TEMPERATURE: float = 0.7

    MAX_TOKENS: int = 4096

    # --------------------------------------------------
    # Voice
    # --------------------------------------------------

    WAKE_WORD: str = "Nova"

    VOICE_LANGUAGE: str = "en"

    # Preferred output voice (platform/provider dependent).
    # For Piper, this maps to keys like english_lessac.
    VOICE_NAME: str = "english_lessac"

    VOICE_RATE: int = 180

    VOICE_PITCH: int = 50

    VOICE_CONTINUOUS_LISTENING: bool = False

    # If enabled, block non-neural talkback engines (browser/say/espeak/text).
    # Use Kokoro or Piper for spoken output.
    TTS_NEURAL_ONLY: bool = True

    # --------------------------------------------------
    # Security
    # --------------------------------------------------

    ENABLE_SECURITY_SCAN: bool = True

    ENABLE_SECURITY_CENTER: bool = True

    SECURITY_CENTER_SEED_DEMO: bool = False

    SECURITY_AGENT_INGEST_ENABLED: bool = True

    SECURITY_AGENT_PULL_ENABLED: bool = True

    SECURITY_AGENT_SHARED_TOKEN: str = ""

    SECURITY_AGENT_SIGNATURE_REQUIRED: bool = True

    SECURITY_AGENT_PUBLIC_KEY_PATH: str = ""

    # --------------------------------------------------
    # Memory
    # --------------------------------------------------

    ENABLE_LONG_TERM_MEMORY: bool = True

    MEMORY_LIMIT: int = 10000

    # --------------------------------------------------
    # Planner
    # --------------------------------------------------

    ENABLE_PLANNER: bool = True

    # --------------------------------------------------
    # Future Features
    # --------------------------------------------------

    ENABLE_VOICE: bool = True

    ENABLE_VISION: bool = False

    VISION_CAMERA_INDEX: int = 0

    VISION_CAMERA_CANDIDATE_INDICES: str = "0,1,2"

    VISION_CAMERA_WARMUP_FRAMES: int = 8

    ENABLE_ROBOTICS: bool = False

    ENABLE_WEB_SEARCH: bool = False

    ENABLE_AUTOMATION: bool = False

    # --------------------------------------------------
    # macOS music automation
    # --------------------------------------------------

    MUSIC_APP_PREFERENCE: str = "spotify"

    MUSIC_FAVORITE_PLAYLIST: str = "Favorites"

    # --------------------------------------------------
    # API / Cross Platform Access
    # --------------------------------------------------

    CORS_ALLOW_ORIGINS: str = "*"

    CORS_ALLOW_CREDENTIALS: bool = True

    CORS_ALLOW_METHODS: str = "*"

    CORS_ALLOW_HEADERS: str = "*"

    # --------------------------------------------------
    # Cache / Redis
    # --------------------------------------------------

    REDIS_ENABLED: bool = False

    REDIS_URL: str = "redis://127.0.0.1:6379/0"

    REDIS_KEY_PREFIX: str = "nova"

    SECURITY_CACHE_TTL: int = 20

    SECURITY_STATE_CACHE_TTL: int = 86400

    GMAIL_CACHE_TTL: int = 30

    # --------------------------------------------------
    # Gmail Integration
    # --------------------------------------------------

    GMAIL_CREDENTIALS_PATH: str = "~/.nova/gmail_credentials.json"

    GMAIL_TOKEN_PATH: str = "~/.nova/gmail_token.json"

    # How often (seconds) to poll for new mail when push is unavailable.
    GMAIL_POLL_INTERVAL: int = 60

    # Maximum unread messages to fetch per poll cycle.
    GMAIL_MAX_RESULTS: int = 10

    # Enable/disable the Gmail monitor background task entirely.
    GMAIL_MONITOR_ENABLED: bool = False

    # Labels to monitor (comma-separated). Empty = INBOX only.
    GMAIL_LABELS: str = "INBOX"

    # Optional custom CA bundle path for Gmail OAuth/API HTTPS calls.
    GMAIL_CA_BUNDLE_PATH: str = ""

    # Emergency fallback: disable SSL verification for Gmail OAuth/API calls.
    # Keep this false in normal environments.
    GMAIL_INSECURE_SSL: bool = False

    # --------------------------------------------------
    # Pydantic
    # --------------------------------------------------

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()