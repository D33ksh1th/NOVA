from __future__ import annotations

import base64
import json
import platform
import re
import subprocess
import threading


MUSIC_CHOICE_PROMPT = (
    "I couldn't find suitable music in your Apple Music library. Which song, artist, playlist, or genre would you like? "
    "Add it to your Music library first if it is only in the catalog."
)


_SCRIPT = r'''
function run(argv) {
    const music = Application('Music');
    const operation = argv[0];
    if (operation === 'status' && !music.running()) {
        return JSON.stringify({available: true, playback_state: 'stopped', track: null});
    }
    function snapshot() {
        const state = music.playerState();
        let track = null;
        if (state === 'playing' || state === 'paused') {
            const current = music.currentTrack;
            track = {id: current.persistentID(), title: current.name(), artist: current.artist(),
                album: current.album(), duration: current.duration()};
        }
        return {available: true, playback_state: state, track: track,
            position: track ? music.playerPosition() : 0};
    }
    if (operation === 'pause') music.pause();
    else if (operation === 'resume') {
        music.play();
        let result;
        for (let attempt = 0; attempt <= 12; attempt++) {
            try {
                result = snapshot();
            } catch (error) {
                result = {available: true, playback_state: 'unknown', track: null};
            }
            if (result.playback_state === 'playing' && result.track) {
                result.success = true;
                return JSON.stringify(result);
            }
            if (attempt < 12) delay(0.25);
        }
        result.success = false;
        result.reason = 'resume_not_started';
        return JSON.stringify(result);
    }
    else if (operation === 'next') music.nextTrack();
    else if (operation === 'previous') music.previousTrack();
    else if (operation === 'play') {
        const kind = argv[1], query = argv[2], artist = argv[3];
        const library = music.libraryPlaylists[0];
        let candidates = [];
        if (kind === 'soothing') {
            for (const genre of ['ambient', 'classical', 'meditation', 'relax']) {
                candidates = candidates.concat(library.tracks.whose({genre: {_contains: genre}})());
            }
            if (!candidates.length) {
                for (const name of ['soothing', 'calm', 'relax', 'ambient']) {
                    const lists = music.userPlaylists.whose({name: {_contains: name}})();
                    for (const playlist of lists) candidates = candidates.concat(playlist.tracks());
                }
            }
        } else if (kind === 'playlist') {
            const lists = music.userPlaylists.whose({name: {_equals: query}})();
            if (lists.length) candidates = lists[0].tracks();
        } else if (kind === 'artist') {
            candidates = library.tracks.whose({artist: {_contains: query}})();
        } else if (kind === 'genre') {
            candidates = library.tracks.whose({genre: {_contains: query}})();
        } else {
            candidates = library.tracks.whose({name: {_equals: query}})();
            const titleQuery = query.replace(/\s+song$/i, '');
            if (!candidates.length && titleQuery !== query) candidates = library.tracks.whose({name: {_equals: titleQuery}})();
            if (!candidates.length) candidates = library.tracks.whose({name: {_contains: titleQuery}})();
            if (artist) candidates = candidates.filter(candidate => candidate.artist().toLowerCase().includes(artist.toLowerCase()));
            if (!candidates.length && !artist) candidates = library.tracks.whose({artist: {_contains: titleQuery}})();
        }
        if (!candidates.length) {
            const result = snapshot();
            result.success = false;
            result.reason = 'not_found';
            return JSON.stringify(result);
        }
        const target = candidates[Math.floor(Math.random() * candidates.length)];
        music.play(target);
        const result = snapshot();
        result.success = result.playback_state === 'playing' && result.track && result.track.id === target.persistentID();
        return JSON.stringify(result);
    }
    const result = snapshot();
    result.success = operation === 'status' || (operation === 'pause' ? result.playback_state === 'paused' : result.playback_state === 'playing');
    return JSON.stringify(result);
}
'''


def parse_music_request(message: str) -> dict | None:
    text = re.sub(r"^(?:please\s+)", "", message.strip(), flags=re.I).rstrip(".!?")
    controls = {
        "pause": r"(?:pause|stop) (?:the |apple )?music",
        "resume": r"(?:play|start|resume|continue|put on) (?:the )?(?:apple )?music",
        "next": r"(?:next (?:song|track)|skip(?: (?:this|the))? (?:song|track))",
        "previous": r"previous (?:song|track)",
    }
    for operation, pattern in controls.items():
        if re.fullmatch(pattern, text, re.I):
            return {"operation": operation}
    match = re.fullmatch(r"(?:play|put on|start(?=\s+(?:(?:my|the)\s+)?(?:playlist|music)\b))\s+(.+)", text, re.I)
    if not match:
        return None
    query = match.group(1).strip()
    if re.match(r"(?:a |the )?(?:video|movie|game|app)\b", query, re.I):
        return None
    if re.fullmatch(r"(?:some |any |the )?(?:something(?: soothing| relaxing| calm)?|soothing|relaxing|calm|(?:soothing |relaxing |calm |apple )?music)", query, re.I):
        return {"operation": "play", "kind": "soothing", "query": "", "artist": ""}
    genre = re.fullmatch(r"(?:some )?(jazz|classical|ambient|pop|rock|instrumental|meditation|country|electronic|blues)(?: music| songs)?", query, re.I)
    if genre:
        return {"operation": "play", "kind": "genre", "query": genre.group(1).lower(), "artist": ""}
    if re.fullmatch(r"(?:my )?(?:favorite|favourite|favroute) music|my playlist", query, re.I):
        query = "playlist Favorites"
    playlist = re.fullmatch(r"(?:the |my )?playlist\s+(.+)", query, re.I)
    artist = re.fullmatch(r"(?:songs?|music) (?:by|from)\s+(.+)|(.+?)(?:(?:'s|’s)\s+songs?|\s+songs)", query, re.I)
    if playlist:
        return {"operation": "play", "kind": "playlist", "query": playlist.group(1), "artist": ""}
    if artist:
        return {"operation": "play", "kind": "artist", "query": artist.group(1) or artist.group(2), "artist": ""}
    query = re.sub(r"^(?:the )?song\s+", "", query, flags=re.I)
    parts = re.split(r"\s+by\s+", query, maxsplit=1, flags=re.I)
    return {"operation": "play", "kind": "song", "query": parts[0].strip('"'), "artist": parts[1] if len(parts) > 1 else ""}


def music_followup_message(message: str) -> str | None:
    text = message.strip()
    if not text or len(text) > 120 or re.match(
        r"^(?:no|nope|cancel|stop|never mind|nevermind|thanks|thank you|what|why|how|when|where|who|can|could|open|launch|search|tell|remind|send)\b", text, re.I
    ):
        return None
    return text if parse_music_request(text) else f"play {text}"


class AppleMusic:
    def __init__(self):
        self._lock = threading.Lock()
        self._artwork_id = None
        self._artwork = None

    def run(self, operation: str = "status", kind: str = "", query: str = "", artist: str = "") -> dict:
        if operation not in {"status", "play", "pause", "resume", "next", "previous"}:
            raise ValueError("Unsupported music operation")
        if platform.system() != "Darwin":
            return self._unavailable("Apple Music control requires macOS.")
        with self._lock:
            try:
                result = subprocess.run(
                    ["osascript", "-l", "JavaScript", "-e", _SCRIPT, operation, kind, query, artist],
                    capture_output=True, text=True, timeout=15,
                )
                if result.returncode:
                    return self._unavailable("Apple Music is unavailable. Check Music and macOS Automation permission for the backend terminal.")
                payload = json.loads(result.stdout)
                track = payload.get("track")
                if track:
                    track["artwork_url"] = self._get_artwork(track["id"])
                payload["action"] = "music_playback"
                if payload.get("reason") == "not_found":
                    payload["response"] = MUSIC_CHOICE_PROMPT
                elif payload.get("reason") == "resume_not_started":
                    state = payload.get("playback_state")
                    if state == "stopped":
                        payload["response"] = "I sent Resume, but Apple Music stayed stopped. Open a playable track in Music first, then pause it and ask me to resume."
                    elif state == "paused":
                        payload["response"] = "I sent Resume, but Apple Music is still paused. Check Music for a sign-in, playback, or connection message."
                    else:
                        payload["response"] = "I sent Resume, but couldn't confirm a playing track within three seconds. Check Music before retrying."
                elif payload.get("success") and track:
                    prefix = "Paused" if payload["playback_state"] == "paused" else "Playing"
                    payload["response"] = f"{prefix} {track['title']} by {track['artist']}."
                else:
                    payload["response"] = "Apple Music hasn't confirmed playback yet."
                return payload
            except (subprocess.SubprocessError, OSError, ValueError, KeyError, TypeError):
                return self._unavailable("I couldn't read Apple Music's playback state. Please try again.")

    def _get_artwork(self, track_id: str) -> str | None:
        if track_id == self._artwork_id:
            return self._artwork
        self._artwork_id, self._artwork = track_id, None
        if not re.fullmatch(r"[A-Fa-f0-9]+", track_id):
            return None
        script = f'''tell application "Music"
if persistent ID of current track is not "{track_id}" then return ""
try
return raw data of artwork 1 of current track
on error
return ""
end try
end tell'''
        try:
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            match = re.fullmatch(r"«data (?:JPEG|PNGf|tdta)([A-Fa-f0-9]+)»", result.stdout.strip())
            if result.returncode == 0 and match and len(match.group(1)) <= 4_000_000:
                data = bytes.fromhex(match.group(1))
                mime = "image/png" if data.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg" if data.startswith(b"\xff\xd8\xff") else None
                if mime:
                    self._artwork = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
        except (subprocess.SubprocessError, OSError, ValueError):
            pass
        return self._artwork

    @staticmethod
    def _unavailable(response: str) -> dict:
        return {"action": "music_playback", "success": False, "available": False,
                "playback_state": "unknown", "track": None, "response": response}


apple_music = AppleMusic()