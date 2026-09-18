from types import SimpleNamespace

import pytest

from packages.application.conversation_service import ConversationService
from services.agent_runtime.conversation import AgentConversation, agent_command, status_reply


@pytest.mark.parametrize("message,action", [
    ("what is the agent status?", "status"), ("what are my agents doing?", "status"),
    ("status", "status"), ("stop all agents", "stop"), ("what can your agents do?", "capabilities"),
    ("use your agents to research local speech models", "research"),
    ("ask agents to research project status", "research"), ("ask agents to delete files", "capabilities"),
])
def test_explicit_agent_commands(message, action):
    assert agent_command(message)[0] == action


@pytest.mark.parametrize("message,objective", [
    ("search up for local speech models", "local speech models"),
    ("search up local speech models", "local speech models"),
    ("search for the latest AI news", "the latest AI news"),
    ("search the web for battery research", "battery research"),
    ("search online for Apple Music APIs", "Apple Music APIs"),
    ("Hey Lumi, can you please look up quantum computing?", "quantum computing?"),
    ("Nova, research agent frameworks", "agent frameworks"),
    ("please investigate new solar panels", "new solar panels"),
    ("could you find sources about climate change", "climate change"),
    ("use your agents to search up for local speech models", "local speech models"),
    ("ask agents to look up Python releases", "Python releases"),
    ("search about Python 3.13", "Python 3.13"),
    ("search on solar energy", "solar energy"),
    ("Google Python release notes", "Python release notes"),
    ("find out about local speech models", "local speech models"),
    ("find details on SQLite WAL", "SQLite WAL"),
    ("I need you to search for FastAPI authentication", "FastAPI authentication"),
    ("Lumi, go ahead and search about climate research", "climate research"),
])
def test_natural_research_requests_delegate_once_without_brain(message, objective):
    from unittest.mock import Mock

    owner = SimpleNamespace(command=Mock(return_value={"response": "Research queued", "action": "agent_research"}))
    brain = SimpleNamespace(process=Mock())
    initiative = SimpleNamespace(evaluate=Mock())
    conversation = ConversationService(brain, initiative, AgentConversation(owner))
    assert agent_command(message) == ("research", objective)
    assert conversation.handle(message)["action"] == "agent_research"
    owner.command.assert_called_once_with("research", objective)
    brain.process.assert_not_called()
    initiative.evaluate.assert_not_called()


@pytest.mark.parametrize("message", [
    "search my files for invoices", "look up my contacts", "search inbox for receipts",
    "search for Hall of Fame in my library", "search music library for Adele",
    "search for TODO in this repository", "search ~/Downloads", "look up saved reports",
    "don't search for anything", "what does web search mean?", "play music", "search",
    "tell me how to search the web", "help me understand Python",
    "search this project for errors", "Google my emails", "search my repo for TODO",
])
def test_other_requests_do_not_start_web_research(message):
    assert agent_command(message) is None


@pytest.mark.parametrize("message,action", [
    ("research status", "status"), ("search progress", "status"),
    ("how is my research going?", "status"), ("task status", "status"),
    ("show me the research results", "results"), ("what did you find?", "results"),
])
def test_natural_progress_and_results(message, action):
    assert agent_command(message) == (action, "")


def test_explicit_delegation_does_not_send_private_file_search_to_web():
    assert agent_command("ask research agents to search my files for invoices") == ("capabilities", "")


def test_conversation_routes_agents_without_brain_or_initiative():
    calls = []
    owner = SimpleNamespace(command=lambda action, objective: {"response": "Actual runtime status", "action": action})
    brain = SimpleNamespace(process=lambda message: calls.append(message) or "normal conversation")
    conversation = ConversationService(brain, agent_runtime=AgentConversation(owner))
    assert conversation.handle("agent status")["response"] == "Actual runtime status"
    assert not calls
    assert conversation.handle("help me understand Python") == "normal conversation"
    assert calls == ["help me understand Python"]


def test_partial_status_never_claims_success():
    report = status_reply({"state": "READY", "graphs": [{"status": "PARTIAL", "finished_tasks": 1,
        "total_tasks": 1, "finished_percent": 100, "successful_tasks": 0,
        "nodes": [{"name": "Scout", "state": "COMPLETED", "result_status": "PARTIAL"}]}]})
    assert "100%" in report and "0 successful" in report and "Scout: partial" in report


def test_capability_reply_distinguishes_local_game_from_governed_agents():
    reply = AgentConversation(SimpleNamespace()).handle("what can your agents do?")
    assert "do not need to name an agent" in reply["response"]
    assert "not a tool-enabled agent" in reply["response"]
    assert "write actions are not enabled" in reply["response"]