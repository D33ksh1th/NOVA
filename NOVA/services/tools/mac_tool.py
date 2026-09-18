"""
Mac Tool

macOS automation: app launcher, clipboard read/write.
Uses only stdlib + macOS built-in binaries (open, pbpaste, pbcopy).
Works on macOS only; gracefully reports unavailable on other platforms.
"""

from __future__ import annotations

import platform
import re
import subprocess
from typing import Optional

from services.tools.base import Tool
from packages.common import logger
from packages.config.settings import settings
from services.tools.apple_music import apple_music, parse_music_request

_IS_MAC = platform.system().lower() == "darwin"

# Common app name aliases → real .app names
_APP_ALIASES: dict[str, str] = {
    "spotify": "Spotify",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "firefox": "Firefox",
    "safari": "Safari",
    "terminal": "Terminal",
    "iterm": "iTerm",
    "iterm2": "iTerm",
    "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "code": "Visual Studio Code",
    "notes": "Notes",
    "messages": "Messages",
    "mail": "Mail",
    "calendar": "Calendar",
    "finder": "Finder",
    "slack": "Slack",
    "zoom": "Zoom",
    "teams": "Microsoft Teams",
    "word": "Microsoft Word",
    "excel": "Microsoft Excel",
    "powerpoint": "Microsoft PowerPoint",
    "xcode": "Xcode",
    "figma": "Figma",
    "notion": "Notion",
    "obsidian": "Obsidian",
    "music": "Music",
    "vlc": "VLC",
    "photos": "Photos",
    "system preferences": "System Preferences",
    "system settings": "System Settings",
    "activity monitor": "Activity Monitor",
    "calculator": "Calculator",
    "preview": "Preview",
}


class MacTool(Tool):

    @property
    def name(self) -> str:
        return "mac"

    def can_handle(self, message: str) -> bool:
        if parse_music_request(message):
            return True
        text = message.lower()
        return any(k in text for k in [
            "open ", "launch ", "start ",
            "clipboard", "copy that", "what's in my clipboard",
            "paste ", "read clipboard",
            "play my favorite music", "play my favourite music", "play my favroute music",
            "start my playlist", "play my playlist",
        ])

    def execute(self, message: str) -> dict:
        music_request = parse_music_request(message)
        if music_request:
            return apple_music.run(**music_request)
        text = message.lower().strip()

        # ── Apple Music pause/stop playback ─────────────────────
        if self._is_pause_music_request(text):
            return self._pause_apple_music()

        # ── Apple Music resume playback ──────────────────────────
        if self._is_resume_music_request(text):
            return self._resume_apple_music()

        # ── Favorite music playback ─────────────────────────────
        if self._is_favorite_music_request(text):
            return self._play_favorite_music()

        # ── Clipboard read ────────────────────────────────────────
        if any(k in text for k in ["clipboard", "what's in my clipboard", "read clipboard"]):
            return self._clipboard_read()

        # ── Clipboard write ───────────────────────────────────────
        m = re.search(r"\bcopy\s+[\"']?(.+?)[\"']?\s*(to clipboard)?$", text)
        if m:
            return self._clipboard_write(m.group(1).strip())

        # ── App launcher ──────────────────────────────────────────
        app = self._extract_app(message)
        if app:
            return self._launch_app(app)

        return {
            "action": "mac",
            "success": False,
            "response": "I'm not sure what you want me to open or do. Try 'open Spotify' or 'what's in my clipboard'.",
        }

    def _is_resume_music_request(self, text: str) -> bool:
        return bool(
            re.search(r"\b(play|resume|start)\b[\s,]+(the[\s,]+)?(apple[\s,]+)?music\b", text)
        )

    def _is_pause_music_request(self, text: str) -> bool:
        return bool(
            re.search(r"\b(pause|stop)\b[\s,]+(the[\s,]+)?(apple[\s,]+)?music\b", text)
        )

    def _resume_apple_music(self) -> dict:
        if not _IS_MAC:
            return {
                "action": "music_playback",
                "success": False,
                "response": "Music playback automation is only available on macOS.",
            }

        if not self._is_app_installed("Music"):
            return {
                "action": "music_playback",
                "success": False,
                "response": "Apple Music app is not installed.",
            }

        # `play` resumes the last paused/open playback context when available.
        script = [
            'tell application "Music"',
            "activate",
            "play",
            "end tell",
        ]
        ok, stderr = self._run_osascript(script)
        if ok:
            return {
                "action": "music_playback",
                "success": True,
                "response": "Opening Apple Music and resuming your last playback.",
                "playback_state": "playing",
            }

        logger.warning(f"MacTool: apple music resume failed: {stderr}")
        return {
            "action": "music_playback",
            "success": False,
            "response": "I couldn't resume Apple Music playback right now.",
            "playback_state": "unknown",
        }

    def _pause_apple_music(self) -> dict:
        if not _IS_MAC:
            return {
                "action": "music_playback",
                "success": False,
                "response": "Music playback automation is only available on macOS.",
                "playback_state": "unknown",
            }

        if not self._is_app_installed("Music"):
            return {
                "action": "music_playback",
                "success": False,
                "response": "Apple Music app is not installed.",
                "playback_state": "unknown",
            }

        script = [
            'tell application "Music"',
            "pause",
            "end tell",
        ]
        ok, stderr = self._run_osascript(script)
        if ok:
            return {
                "action": "music_playback",
                "success": True,
                "response": "Paused Apple Music.",
                "playback_state": "paused",
            }

        logger.warning(f"MacTool: apple music pause failed: {stderr}")
        return {
            "action": "music_playback",
            "success": False,
            "response": "I couldn't pause Apple Music right now.",
            "playback_state": "unknown",
        }

    def _is_favorite_music_request(self, text: str) -> bool:
        if "playlist" in text and any(k in text for k in ["play", "start"]):
            return True

        if "music" not in text:
            return False

        if not any(k in text for k in ["play", "start"]):
            return False

        favorite_tokens = ["favorite", "favourite", "favroute", "favrite", "fav"]
        return any(token in text for token in favorite_tokens)

    def _play_favorite_music(self) -> dict:
        if not _IS_MAC:
            return {
                "action": "music_playback",
                "success": False,
                "response": "Music playback automation is only available on macOS.",
            }

        preferred_app = str(settings.MUSIC_APP_PREFERENCE or "spotify").strip().lower()
        playlist_name = str(settings.MUSIC_FAVORITE_PLAYLIST or "Favorites").strip()

        app_order = [preferred_app] if preferred_app in {"spotify", "music", "apple_music"} else []
        for candidate in ["spotify", "music"]:
            if candidate not in app_order:
                app_order.append(candidate)

        for app_key in app_order:
            if app_key == "spotify":
                result = self._play_spotify_playlist(playlist_name)
            else:
                result = self._play_apple_music_playlist(playlist_name)
            if result["success"]:
                return result

        return {
            "action": "music_playback",
            "success": False,
            "response": (
                "I could not start your favorite playlist. Install Spotify or Apple Music and "
                "set MUSIC_APP_PREFERENCE and MUSIC_FAVORITE_PLAYLIST in your env."
            ),
        }

    def _play_spotify_playlist(self, playlist_name: str) -> dict:
        if not self._is_app_installed("Spotify"):
            return {"success": False}

        script = [
            'tell application "Spotify"',
            "activate",
            f'set playlistName to "{self._escape_applescript(playlist_name)}"',
            "try",
            "set targetPlaylist to first playlist whose name is playlistName",
            "if (count of tracks of targetPlaylist) > 0 then",
            "play track 1 of targetPlaylist",
            "else",
            "play",
            "end if",
            "on error",
            "play",
            "end try",
            "end tell",
        ]
        ok, stderr = self._run_osascript(script)
        if ok:
            return {
                "action": "music_playback",
                "success": True,
                "response": f"Opening Spotify and playing your playlist '{playlist_name}'.",
            }

        logger.warning(f"MacTool: spotify playlist play failed: {stderr}")
        return {"success": False}

    def _play_apple_music_playlist(self, playlist_name: str) -> dict:
        if not self._is_app_installed("Music"):
            return {"success": False}

        script = [
            'tell application "Music"',
            "activate",
            f'set playlistName to "{self._escape_applescript(playlist_name)}"',
            "try",
            "play playlist playlistName",
            "on error",
            "play",
            "end try",
            "end tell",
        ]
        ok, stderr = self._run_osascript(script)
        if ok:
            return {
                "action": "music_playback",
                "success": True,
                "response": f"Opening Music and playing your playlist '{playlist_name}'.",
            }

        logger.warning(f"MacTool: apple music playlist play failed: {stderr}")
        return {"success": False}

    def _is_app_installed(self, app_name: str) -> bool:
        try:
            result = subprocess.run(["open", "-Ra", app_name], capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def _run_osascript(self, lines: list[str]) -> tuple[bool, str]:
        command = ["osascript"]
        for line in lines:
            command.extend(["-e", line])
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            return result.returncode == 0, (result.stderr or "").strip()
        except Exception as ex:
            return False, str(ex)

    def _escape_applescript(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    # ── Clipboard ─────────────────────────────────────────────────

    def _clipboard_read(self) -> dict:
        if not _IS_MAC:
            return {"action": "clipboard", "success": False, "response": "Clipboard access is only available on macOS."}
        try:
            result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
            content = (result.stdout or "").strip()
            if not content:
                return {"action": "clipboard", "success": True, "response": "Your clipboard is empty."}
            preview = content[:300] + ("…" if len(content) > 300 else "")
            return {"action": "clipboard", "success": True, "response": f"Your clipboard contains: {preview}"}
        except Exception as ex:
            logger.warning(f"MacTool: clipboard read error: {ex}")
            return {"action": "clipboard", "success": False, "response": f"Couldn't read clipboard: {ex}"}

    def _clipboard_write(self, text: str) -> dict:
        if not _IS_MAC:
            return {"action": "clipboard", "success": False, "response": "Clipboard access is only available on macOS."}
        try:
            proc = subprocess.run(["pbcopy"], input=text, text=True, timeout=5)
            if proc.returncode == 0:
                return {"action": "clipboard", "success": True, "response": f"Copied to clipboard: {text[:100]}"}
            return {"action": "clipboard", "success": False, "response": "Failed to copy to clipboard."}
        except Exception as ex:
            logger.warning(f"MacTool: clipboard write error: {ex}")
            return {"action": "clipboard", "success": False, "response": f"Couldn't write to clipboard: {ex}"}

    # ── App launcher ─────────────────────────────────────────────

    def _extract_app(self, message: str) -> Optional[str]:
        m = re.search(
            r"\b(?:open|launch|start|run)\s+(?:the\s+)?(?:app\s+)?(.+?)(?:\s+(?:app|application))?\s*$",
            message, re.IGNORECASE
        )
        if m:
            raw = m.group(1).strip().lower()
            return _APP_ALIASES.get(raw, m.group(1).strip())
        return None

    def _launch_app(self, app_name: str) -> dict:
        if not _IS_MAC:
            return {"action": "app_launch", "success": False, "response": "App launching is only available on macOS."}
        try:
            result = subprocess.run(
                ["open", "-a", app_name],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return {"action": "app_launch", "success": True, "response": f"Opening {app_name}."}
            err = (result.stderr or "").strip()
            logger.warning(f"MacTool: open -a '{app_name}' failed: {err}")
            return {
                "action": "app_launch",
                "success": False,
                "response": f"I couldn't find an app called '{app_name}'. Make sure it's installed.",
            }
        except Exception as ex:
            logger.warning(f"MacTool: launch error: {ex}")
            return {"action": "app_launch", "success": False, "response": f"Failed to open {app_name}: {ex}"}
