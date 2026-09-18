import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services.tools import apple_music as module
from services.tools.apple_music import AppleMusic, parse_music_request
from services.tools.apple_music import music_followup_message


@pytest.mark.parametrize("text,kind,query", [
    ("play something", "soothing", ""),
    ("play soothing music", "soothing", ""),
    ("play songs by Adele", "artist", "Adele"),
    ("play Adele songs", "artist", "Adele"),
    ("play Hello by Adele", "song", "Hello"),
    ("play playlist Relax", "playlist", "Relax"),
    ("play jazz music", "genre", "jazz"),
    ("start my playlist", "playlist", "Favorites"),
    ("play hall of fame song", "song", "hall of fame song"),
    ("play Hall of Fame song by The Script", "song", "Hall of Fame song"),
    ("play Your Song", "song", "Your Song"),
    ("play Adele's song", "artist", "Adele"),
])
def test_music_requests(text, kind, query):
    result = parse_music_request(text)
    assert result["kind"] == kind
    assert result["query"] == query


@pytest.mark.parametrize("text", ["what is music", "play a video", "open Safari", "play the game"])
def test_non_music_requests(text):
    assert parse_music_request(text) is None


@pytest.mark.parametrize("text,operation", [("pause music", "pause"), ("resume music", "resume"), ("next song", "next"), ("previous track", "previous")])
def test_controls(text, operation):
    assert parse_music_request(text) == {"operation": operation}


@pytest.mark.parametrize("message", [
    "play music", "play the music", "play Apple Music", "start music",
    "put on music", "please play music!", "resume the Apple Music",
])
def test_plain_music_request_resumes_without_library_search(monkeypatch, message):
    from services.tools.mac_tool import MacTool

    run = Mock(return_value={"action": "music_playback", "success": True, "playback_state": "playing"})
    monkeypatch.setattr(module.apple_music, "run", run)
    assert parse_music_request(message) == {"operation": "resume"}
    result = MacTool().execute(message)
    run.assert_called_once_with(operation="resume")
    assert result["playback_state"] == "playing"


@pytest.mark.parametrize("message,expected_title", [
    ("play Hall of Fame song", "Hall of Fame"),
    ("play Hall of Fame song by The Script", "Hall of Fame"),
    ("play Your Song", "Your Song"),
])
def test_native_title_selection_with_song_suffix(message, expected_title):
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to exercise the JXA selection logic without Music")
    harness = r'''
const tracks = [
    {name: 'Hall of Fame', artist: 'The Script', persistentID: 'ABC1'},
    {name: 'Your Song', artist: 'Elton John', persistentID: 'ABC2'},
    {name: 'Your Other Track', artist: 'Another Artist', persistentID: 'ABC3'}
].map(values => Object.fromEntries(Object.entries({...values, album: '', duration: 200}).map(([key, value]) => [key, () => value])));
let current = null;
global.Application = () => ({
    libraryPlaylists: [{tracks: {whose: filter => () => tracks.filter(track => Object.entries(filter).every(([key, rule]) => {
        const actual = track[key]().toLowerCase();
        return rule._equals !== undefined ? actual === rule._equals.toLowerCase() : actual.includes(rule._contains.toLowerCase());
    }))}}],
    play: track => { current = track; },
    playerState: () => current ? 'playing' : 'stopped',
    get currentTrack() { return current; },
    playerPosition: () => 0
});
eval(process.argv[1]);
console.log(run(JSON.parse(process.argv[2])));
'''
    request = parse_music_request(message)
    result = subprocess.run([node, "-e", harness, module._SCRIPT, json.dumps([
        request["operation"], request["kind"], request["query"], request["artist"],
    ])], capture_output=True, text=True, timeout=5, check=True)
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["track"]["title"] == expected_title


def test_query_is_passed_as_argument_not_script(monkeypatch):
    monkeypatch.setattr(module.platform, "system", lambda: "Darwin")
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps({"success": False, "reason": "not_found", "track": None, "playback_state": "paused"})))
    monkeypatch.setattr(module.subprocess, "run", run)
    query = '\"); doShellScript("bad")'
    result = AppleMusic().run("play", "song", query)
    assert run.call_args.args[0][-2] == query
    assert query not in run.call_args.args[0][4]
    assert result["success"] is False
    assert result["playback_state"] == "paused"


def test_permission_failure_does_not_claim_playback(monkeypatch):
    monkeypatch.setattr(module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(module.subprocess, "run", Mock(return_value=SimpleNamespace(returncode=1)))
    result = AppleMusic().run("resume")
    assert result["success"] is False
    assert result["track"] is None
    assert result["playback_state"] == "unknown"


@pytest.mark.parametrize("ready_after,final_state,expected", [(0, "playing", True), (3, "playing", True), (99, "paused", False), (99, "stopped", False)])
def test_resume_waits_for_native_confirmation_without_repeating_play(ready_after, final_state, expected):
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to exercise native confirmation logic")
    harness = r'''
let ticks = 0, plays = 0;
const readyAfter = Number(process.argv[2]), finalState = process.argv[3];
global.delay = () => { ticks++; };
global.Application = () => ({
    play: () => { plays++; },
    playerState: () => ticks >= readyAfter ? 'playing' : finalState === 'stopped' ? 'stopped' : 'paused',
    currentTrack: {persistentID: () => 'ABC1', name: () => 'Hall of Fame', artist: () => 'The Script', album: () => '', duration: () => 200},
    playerPosition: () => 42
});
eval(process.argv[1]);
console.log(JSON.stringify({result: JSON.parse(run(['resume'])), ticks, plays}));
'''
    completed = subprocess.run([node, "-e", harness, module._SCRIPT, str(ready_after), final_state], capture_output=True, text=True, timeout=5, check=True)
    result = json.loads(completed.stdout)
    assert result["plays"] == 1
    assert result["ticks"] == (ready_after if expected else 12)
    assert result["result"]["success"] is expected
    if not expected:
        assert result["result"]["reason"] == "resume_not_started"


@pytest.mark.parametrize("state,message", [("stopped", "stayed stopped"), ("paused", "still paused"), ("unknown", "within three seconds")])
def test_resume_failure_explains_observed_state(monkeypatch, state, message):
    monkeypatch.setattr(module.platform, "system", lambda: "Darwin")
    payload = {"available": True, "success": False, "playback_state": state, "reason": "resume_not_started", "track": None}
    monkeypatch.setattr(module.subprocess, "run", Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps(payload))))
    result = AppleMusic().run("resume")
    assert result["success"] is False
    assert message in result["response"]


@pytest.mark.parametrize("wrapper", ["JPEG", "tdta"])
def test_snapshot_contains_real_metadata_and_artwork(monkeypatch, wrapper):
    monkeypatch.setattr(module.platform, "system", lambda: "Darwin")
    snapshot = {"success": True, "playback_state": "playing", "track": {"id": "ABC123", "title": "Hello", "artist": "Adele", "album": "25", "duration": 300}, "position": 12}
    run = Mock(side_effect=[SimpleNamespace(returncode=0, stdout=json.dumps(snapshot)), SimpleNamespace(returncode=0, stdout=f"«data {wrapper}FFD8FF00»")])
    monkeypatch.setattr(module.subprocess, "run", run)
    result = AppleMusic().run()
    assert result["track"]["artist"] == "Adele"
    assert result["track"]["artwork_url"].startswith("data:image/jpeg;base64,")
    assert result["position"] == 12


def test_music_routes_require_local_access_and_valid_controls(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from services.gateway.music import router

    run = Mock(return_value={"success": True, "playback_state": "paused", "track": None})
    monkeypatch.setattr(module.apple_music, "run", run)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 1234)) as client:
        assert client.get("/api/music/status", headers={"origin": "https://example.com"}).status_code == 403
        run.assert_not_called()
        assert client.post("/api/music/control", json={"operation": "shell"}).status_code == 422
        assert client.post("/api/music/control", json={"operation": "pause"}).status_code == 200
        run.assert_called_once_with("pause")
        assert client.get("/api/music/status").headers["cache-control"] == "no-store"


def test_mac_skill_routes_specific_music_to_adapter(monkeypatch):
    from services.brain.intent import Intent
    from services.skills.base import SkillContext
    from services.skills.mac import MacSkill
    from services.tools.mac_tool import MacTool

    run = Mock(return_value={"success": False, "response": "Not found", "action": "music_playback"})
    monkeypatch.setattr(module.apple_music, "run", run)
    tool = MacTool()
    skill = MacSkill(tool)
    context = SkillContext(message="play Hello by Adele", intent=Intent.APP_LAUNCH)
    assert skill.can_handle(context)
    assert tool.can_handle(context.message)
    assert tool.execute(context.message)["success"] is False
    run.assert_called_once_with(operation="play", kind="song", query="Hello", artist="Adele")


@pytest.mark.parametrize("text", ["cancel", "no thanks", "what time is it", "open Safari"])
def test_followup_does_not_capture_other_commands(text):
    assert music_followup_message(text) is None


def test_short_reply_only_routes_in_music_choice_context(monkeypatch):
    from services.brain.intent import Intent
    from services.skills.base import SkillContext
    from services.skills.mac import MacSkill
    import services.skills.mac as mac_module

    monkeypatch.setattr(mac_module, "logger", Mock())
    tool = Mock()
    tool.execute.return_value = {"response": "Playing jazz"}
    skill = MacSkill(tool)
    context = SkillContext(message="jazz", intent=next(intent for intent in Intent if intent not in (Intent.APP_LAUNCH, Intent.CLIPBOARD)))
    assert not skill.can_handle(context)
    context.context = {"music_choice_pending": True}
    assert skill.can_handle(context)
    skill.execute(context)
    tool.execute.assert_called_once_with("play jazz")


@pytest.mark.parametrize("success,state", [(True, "playing"), (True, "paused"), (False, "unknown")])
def test_chat_preserves_playback_outcome(monkeypatch, success, state):
    from services.gateway import routes
    from starlette.requests import Request

    voice = Mock()
    voice.has_active_enrollment_session.return_value = False
    voice.is_enrollment_trigger.return_value = False
    conversation = Mock()
    conversation.handle.return_value = {"response": "Music result", "action": "music_playback", "success": success, "playback_state": state}
    monkeypatch.setattr(routes, "registry", SimpleNamespace(voice_engine=voice, conversation=conversation))
    monkeypatch.setattr(routes, "_should_block_sensitive_request", lambda text: False)
    request = Request({"type": "http", "method": "POST", "path": "/chat", "headers": []})
    result = routes.chat(routes.ChatRequest(message="play jazz"), request)
    assert result.success is success
    assert result.playback_state == state