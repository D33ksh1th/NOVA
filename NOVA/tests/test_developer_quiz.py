from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from packages.application.conversation_service import ConversationService
from services.games.developer_quiz import DeveloperQuiz, QUESTIONS


@pytest.fixture
def quiz(monkeypatch):
    monkeypatch.setattr("services.games.developer_quiz.random.sample", lambda population, count: list(population[:count]))
    return DeveloperQuiz()


@pytest.mark.parametrize("message", ["play a game", "let's play a game", "start coding quiz", "Hey Lumi, can you play a game?", "please start developer quiz", "play a fun game", "quiz me"])
def test_start_game_naturally(quiz, message):
    reply = quiz.handle(message)
    assert reply["data"]["state"] == "RUNNING"
    assert "Question 1/5" in reply["response"]


def test_correct_scoring_completion_and_replay(quiz):
    quiz.handle("play a game")
    for question in QUESTIONS[:5]:
        reply = quiz.handle("answer " + question[2])
    assert reply["data"] == {"game": "developer_quiz", "state": "COMPLETED", "score": 5, "answered": 5, "total": 5}
    assert quiz.handle("a") is None
    assert quiz.handle("play a game")["data"]["score"] == 0


def test_wrong_answer_skip_repeat_and_stop(quiz):
    quiz.handle("play a game")
    assert quiz.handle("a")["data"]["score"] == 0
    assert quiz.handle("repeat question")["data"]["answered"] == 1
    assert quiz.handle("skip question")["data"]["answered"] == 2
    assert quiz.handle("stop game")["data"]["state"] == "STOPPED"
    assert quiz.handle("quiz status")["data"]["state"] == "IDLE"


def test_active_game_does_not_hijack_other_commands(quiz):
    quiz.handle("play a game")
    for message in ("search Python docs", "stop agents", "fix this project", "B is a variable", "delete files"):
        assert quiz.handle(message) is None
    assert quiz.handle("play a game")["data"]["answered"] == 0


def test_game_is_local_and_bypasses_brain_and_research():
    brain = SimpleNamespace(process=Mock())
    agents = SimpleNamespace(handle=Mock())
    initiative = SimpleNamespace(evaluate=Mock())
    conversation = ConversationService(brain, initiative, agents)
    reply = conversation.handle("play a game")
    assert reply["intent"] == "game"
    brain.process.assert_not_called()
    agents.handle.assert_not_called()
    initiative.evaluate.assert_not_called()


def test_game_state_is_not_shared_across_conversation_services():
    first = DeveloperQuiz()
    second = DeveloperQuiz()
    first.handle("play a game")
    assert second.handle("a") is None