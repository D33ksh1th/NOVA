"""App context awareness — detect foreground app and adapt behavior.

Tracks which application is active (VS Code, Terminal, Safari, etc.)
and provides context-aware responses. Publishes app-switch events.
"""

from __future__ import annotations

import subprocess
import threading
import time
from typing import Any, Callable, Dict, Optional

from packages.common import logger
from packages.events import bus


def get_frontmost_app() -> Dict[str, str]:
    """Get the currently active macOS application."""
    try:
        script = 'tell application "System Events" to get {name, bundle identifier} of first application process whose frontmost is true'
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=3,
        )
        parts = result.stdout.strip().split(", ")
        if len(parts) >= 2:
            return {"name": parts[0].strip(), "bundle_id": parts[1].strip()}
        if parts:
            return {"name": parts[0].strip(), "bundle_id": ""}
    except Exception:
        pass
    return {"name": "unknown", "bundle_id": ""}


def get_active_window_title() -> str:
    """Get the title of the frontmost window."""
    try:
        script = '''
tell application "System Events"
    set fp to first application process whose frontmost is true
    tell fp
        if (count of windows) > 0 then
            return name of window 1
        end if
    end tell
end tell
return ""'''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=3,
        )
        return result.stdout.strip()
    except Exception:
        return ""


# App categories for context-aware responses
APP_CONTEXT = {
    "Code": {"category": "development", "hint": "User is coding"},
    "Visual Studio Code": {"category": "development", "hint": "User is coding"},
    "Terminal": {"category": "terminal", "hint": "User is in terminal"},
    "iTerm2": {"category": "terminal", "hint": "User is in terminal"},
    "Safari": {"category": "browser", "hint": "User is browsing"},
    "Google Chrome": {"category": "browser", "hint": "User is browsing"},
    "Firefox": {"category": "browser", "hint": "User is browsing"},
    "Slack": {"category": "communication", "hint": "User is in Slack"},
    "Microsoft Teams": {"category": "communication", "hint": "User is in a meeting app"},
    "Zoom": {"category": "meeting", "hint": "User may be in a video call"},
    "Finder": {"category": "files", "hint": "User is managing files"},
    "Mail": {"category": "email", "hint": "User is checking email"},
    "Notes": {"category": "writing", "hint": "User is writing notes"},
    "Music": {"category": "music", "hint": "User is playing music"},
}


class AppContextWatcher:
    """Monitors foreground app and publishes context-switch events."""

    def __init__(self, poll_interval: float = 5.0):
        self._interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._current_app = ""
        self._current_category = ""
        self._switch_count = 0
        self._history: list[Dict[str, Any]] = []

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="app-context-watcher")
        self._thread.start()
        logger.info("AppContextWatcher: started")

    def stop(self) -> None:
        self._running = False

    @property
    def current(self) -> Dict[str, Any]:
        return {
            "app": self._current_app,
            "category": self._current_category,
            "switch_count": self._switch_count,
        }

    def _loop(self) -> None:
        while self._running:
            try:
                info = get_frontmost_app()
                app_name = info["name"]
                if app_name and app_name != self._current_app:
                    old = self._current_app
                    self._current_app = app_name
                    ctx = APP_CONTEXT.get(app_name, {"category": "other", "hint": f"User is in {app_name}"})
                    self._current_category = ctx["category"]
                    self._switch_count += 1
                    self._history.append({
                        "from": old, "to": app_name,
                        "category": ctx["category"], "ts": time.time(),
                    })
                    if len(self._history) > 50:
                        self._history.pop(0)

                    bus.emit(
                        "nova.context.app_switch",
                        source="app-context-watcher",
                        payload={"from": old, "to": app_name, "category": ctx["category"]},
                        severity=0,
                    )
            except Exception:
                pass
            time.sleep(self._interval)

    def recent_switches(self, limit: int = 10) -> list[Dict[str, Any]]:
        return self._history[-limit:]
