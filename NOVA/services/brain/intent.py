"""
Intent Detection Engine

Detects user intent from natural language with
priority-ordered pattern matching.
"""

from enum import Enum
import re
from dataclasses import dataclass, field
from typing import List


class Intent(str, Enum):
    CHAT = "chat"
    MEMORY_STORE = "memory_store"
    MEMORY_RECALL = "memory_recall"
    CREATE_TASK = "create_task"
    LIST_TASKS = "list_tasks"
    SECURITY_SCAN = "security_scan"
    SYSTEM_QUERY = "system_query"
    VISION_QUERY = "vision_query"
    AUTOMATION_QUERY = "automation_query"
    WEATHER_QUERY = "weather_query"
    LOCATION_QUERY = "location_query"
    TIME_QUERY = "time_query"
    CODE_HELP = "code_help"
    FILE_OPERATION = "file_operation"
    REMINDER = "reminder"
    CALCULATION = "calculation"
    WEB_SEARCH = "web_search"
    COMMAND_RUN = "command_run"
    APP_LAUNCH = "app_launch"
    CLIPBOARD = "clipboard"
    UNKNOWN = "unknown"


@dataclass
class DetectedIntent:
    intent: Intent
    confidence: float = 1.0
    matched_patterns: List[str] = field(default_factory=list)


# Ordered patterns: more specific first
_PATTERNS: List[tuple] = [
    # Memory store — must come before recall to catch "my name is X"
    (
        Intent.MEMORY_STORE,
        [
            r"\b(remember|save|store|note that|keep in mind)\b",
            r"\bmy name is\b",
            r"\bi am\s+\d+ years old\b",
            r"\bi live in\b",
            r"\bmy birthday is\b",
            r"\bmy birth year is\b",
            r"\bmy favourite\b",
            r"\bi work at\b",
            r"\bi am a\b",
            r"\bi own a\b",
        ],
    ),
    # Memory recall
    (
        Intent.MEMORY_RECALL,
        [
            r"\b(recall|retrieve|what do you know about me|tell me about myself)\b",
            r"\bdo you (know|remember) my\b",
            r"\bwhat('?s| is) my (name|age|birthday|city|job|profession|language|colour|color|vehicle|car)\b",
            r"\bwhere do i live\b",
            r"\bwho am i\b",
        ],
    ),
    # Time / date
    (
        Intent.TIME_QUERY,
        [
            r"\bwhat('?s| is) (the )?(current )?(time|date|day|month|year)\b",
            r"\bwhat time is it\b",
            r"\btoday('?s)? date\b",
            r"\bwhat day is (it|today)\b",
        ],
    ),
    # Weather
    (
        Intent.WEATHER_QUERY,
        [
            r"\bweather\b",
            r"\btemperature\b",
            r"\b(is it|will it) (rain|sunny|cloudy|hot|cold|warm|windy)\b",
            r"\bforecast\b",
            r"\bhumidity\b",
        ],
    ),
    # Location (must come before system query)
    (
        Intent.LOCATION_QUERY,
        [
            r"\b(where am i|where are we)\b",
            r"\b(my|current) location\b",
            r"\bwhich city am i\b",
            r"\bwhat('?s| is) my current location\b",
        ],
    ),
    # System queries
    (
        Intent.SYSTEM_QUERY,
        [
            r"\b(cpu|processor|ram|memory usage|disk|storage|battery|gpu|graphics)\b",
            r"\b(system information|system details|device information|computer information)\b",
            r"\b(system|hardware|device|machine|laptop|macbook|mac|windows) (info|spec|status|usage)\b",
            r"\bhow much (ram|memory|disk|storage|battery)\b",
            r"\bwhat('?s| is) (my|the) (system|device|computer) (information|details|status)\b",
            r"\bwhat('?s| is) (my|the) (os|operating system|python version|ip address|network)\b",
            r"\bwhat('?s| is) my ip(address)?\b",
            r"\bshow (me )?(my )?ip(address)?\b",
            r"\b(bluetooth|paired devices|connected devices)\b",
            r"\b(is|are) (my )?bluetooth devices connected\b",
            r"\b(pairing|discoverable)\b",
            r"\b(available for pairing|devices for pairing|pairable devices)\b",
            r"\b(pair with|pair to|connect to|connect with)\s+.+\b",
            r"\b(conect to|conect with)\s+.+\b",
            r"^\s*connected\??\s*$",
            r"\bis it connected\??\b",
            r"\bis\s+.+\s+connected\??\b",
            r"\bdisconnect (my )?(bluetooth )?device\b",
            r"\b(turn on|turn off|enable|disable) bluetooth\b",
            r"\bdisconnect\b.*\b(buds|airpods|earbuds|airdopes|headset|speaker|keyboard|mouse|device)\b",
            r"\buptime\b",
        ],
    ),
    # Vision / OCR
    (
        Intent.VISION_QUERY,
        [
            r"\b(ocr|extract text|read text from image|scan image text)\b",
            r"\b(analyze image|describe image|what am i looking at|understand this image)\b",
            r"\b(screenshot|screen capture|capture screen)\b",
            r"\b(camera capture|take photo|capture from camera|webcam capture)\b",
            r"\b(read text from screenshot|ocr screenshot|screen ocr)\b",
        ],
    ),
    # Browser automation
    (
        Intent.AUTOMATION_QUERY,
        [
            r"\b(open website|open url|browse to|navigate to)\b",
            r"\b(automate browser|run browser automation|web automation)\b",
            r"\b(search web for|automate search for)\b",
            r"\b(playwright)\b",
        ],
    ),
    # Security scan
    (
        Intent.SECURITY_SCAN,
        [
            r"\b(scan|audit|check) (for )?(security|vulnerability|vulnerabilities|threats|malware)\b",
            r"\bsecurity (scan|audit|check|report)\b",
            r"\bvulnerability scan\b",
        ],
    ),
    # Code help
    (
        Intent.CODE_HELP,
        [
            # Allow optional language qualifier: "write a python script", "create a JS function"
            r"\b(write|create|generate|fix|debug|refactor|explain|review) (a |an |the )?(\w+ )?(code|function|class|script|program|method|snippet|bug)\b",
            r"\bhow (do i|to) (code|implement|write|program)\b",
            r"\bcode (for|to|that)\b",
            r"\b(python|javascript|typescript|rust|golang|java|c\+\+|sql|bash|shell|swift|kotlin|ruby|php|cpp) (code|script|function|program|snippet)\b",
            # "write code to ...", "a program to ..."
            r"\b(write|create|generate) (code|a program|a script|a function) (to|that|which)\b",
            # "code that reverses", "program that prints"
            r"\b(script|program|function|code) (to|that|which) \w+\b",
        ],
    ),
    # App launch
    (
        Intent.APP_LAUNCH,
        [
            r"\b(open|launch|start)\s+(the\s+)?(\w+\s+)?(app|application)\b",
            r"\b(open|launch|start)\s+(safari|chrome|finder|terminal|music|spotify|slack|discord|zoom|vscode|code|xcode|notes|photos|calendar|mail|messages|facetime|maps|preview|settings|system preferences)\b",
        ],
    ),
    # Clipboard
    (
        Intent.CLIPBOARD,
        [
            r"\bclipboard\b",
            r"\bwhat('?s| is) in my clipboard\b",
            r"\bcopy that\b",
            r"\bpaste (that|it|this)\b",
        ],
    ),
    # Run command / shell
    (
        Intent.COMMAND_RUN,
        [
            r"\b(run|execute|launch|start|open|kill|stop) (the )?(command|script|program|process|terminal)\b",
            r"\brun\s+`[^`]+`",
            r"\bterminal command\b",
            r"\bexecute\s+in (terminal|shell|bash|zsh)\b",
        ],
    ),
    # File operations
    (
        Intent.FILE_OPERATION,
        [
            r"\b(open|read|write|create|delete|rename|move|copy|list) (a |the |this )?(file|folder|directory|document)\b",
            r"\blist (the )?(files|folders|directory)\b",
            r"\bshow (me )?(the )?(contents|files|folders)\b",
            r"\blist (files|folders|directory)\b",
            r"\bfind (a |the )?file\b",
            r"\bsearch (for )?(a |the )?file\b",
            r"\bfile named\b",
            r"\blist all files (in|under)\b",
            r"\b(download|downloads) folder\b",
        ],
    ),
    # Reminders
    (
        Intent.REMINDER,
        [
            r"\b(remind me|set a reminder|set an alarm|alert me)\b",
            r"\bremind me (to|about|at|in)\b",
        ],
    ),
    # Calculations
    (
        Intent.CALCULATION,
        [
            r"\b(calculate|compute|what is|how much is)\s+[\d\s\+\-\*\/\^\(\)]+",
            r"\bwhat('?s| is)\s+\d+\s*[\+\-\*\/\^]\s*\d+\b",
            r"\b(convert|how many)\s+\d+",
        ],
    ),
    # Web search
    (
        Intent.WEB_SEARCH,
        [
            r"\b(search (for|about|the web for)|google|look up|find online)\b",
            r"\bwhat('?s| is) (on|in) (the )?internet\b",
        ],
    ),
    # Task creation
    (
        Intent.CREATE_TASK,
        [
            r"\b(create|add|make|set up|start) (a |new )?(task|todo|goal|project|plan)\b",
            r"\bi need to\b",
            r"\badd to (my )?(todo|task list|goals)\b",
        ],
    ),
    # List tasks
    (
        Intent.LIST_TASKS,
        [
            r"\b(list|show|what are) (my )?(tasks|todos|goals|plans)\b",
            r"\bwhat('?s| is) (on my|my) (todo|task) list\b",
        ],
    ),
]


class IntentEngine:
    """
    Priority-ordered intent detection using pattern matching.
    Returns the first matching intent with confidence scoring.
    """

    def detect(self, message: str) -> Intent:
        return self.detect_with_confidence(message).intent

    def detect_with_confidence(self, message: str) -> DetectedIntent:
        text = message.lower().strip()

        for intent, patterns in _PATTERNS:
            matched = []
            for pattern in patterns:
                if re.search(pattern, text):
                    matched.append(pattern)

            if matched:
                # Confidence increases with more matched patterns
                confidence = min(0.6 + (len(matched) * 0.15), 1.0)
                return DetectedIntent(
                    intent=intent,
                    confidence=confidence,
                    matched_patterns=matched,
                )

        return DetectedIntent(intent=Intent.CHAT, confidence=0.5)