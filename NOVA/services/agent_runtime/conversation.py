"""Agent and web research commands shared by typed and spoken conversations."""

from __future__ import annotations

import re


def agent_command(message: str) -> tuple[str, str] | None:
    text = message.strip()
    text = re.sub(r"^(?:(?:hey|hi|hello)\s+)?(?:nova|lumi)\b[\s,:!]*", "", text, flags=re.I)
    text = re.sub(r"^(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?", "", text, flags=re.I)
    text = re.sub(r"^(?:i\s+(?:want|need)\s+you\s+to\s+|go\s+ahead\s+and\s+)(?:please\s+)?", "", text, flags=re.I)
    if re.fullmatch(r"(?:research|search|task)\s+(?:status|progress)[?.!]*|(?:how(?:'s| is) (?:the |my )?(?:research|search|task)(?: going)?)\??", text, re.I):
        return "status", ""
    if re.fullmatch(r"(?:show(?: me)? (?:the |my )?(?:research|search) (?:results|findings)|what did (?:you|the agents) find)[?.!]*", text, re.I):
        return "results", ""
    delegation = re.fullmatch(
        r"(?:(?:use|ask|have|tell|send) (?:your |my |the )?(?:research )?agents? (?:to )?|agents?[, :]+)(?:research|investigate|compare|look into|search(?: up)?(?: for| about| on)?|look up)\s+(.+)",
        text, re.I | re.S,
    )
    research = re.fullmatch(
        r"(?:search(?:\s+(?:the\s+)?(?:web|internet|online))?(?:\s+up)?(?:\s+(?:for|about|on))?|google|look\s+up|research|investigate|look\s+into|find\s+(?:information|sources|details)\s+(?:about|on|for)|find\s+out(?:\s+about)?)\s+(.+)",
        text, re.I | re.S,
    )
    if delegation or research:
        objective = (delegation or research).group(1).strip()
        local_search = re.search(
            r"^(?:(?:my|our|the|this|local)\s+)?(?:files?|folders?|directories|directory|emails?|inbox|mailbox|contacts?|calendar|clipboard|playlists?|music\s+library|saved\s+memories|saved\s+reports)\b"
            r"|^(?:my|our|this|local)\s+(?:repository|repo|codebase|workspace|project)\b"
            r"|\b(?:in|inside|within|from)\s+(?:my|our|the|this|local)\s+(?:files?|folders?|emails?|inbox|mailbox|contacts?|calendar|library|repository|repo|codebase|workspace|computer|mac|memory|memories|reports)\b"
            r"|^(?:[~/]|[A-Za-z]:\\)",
            objective, re.I,
        )
        if not local_search:
            return "research", objective
    if re.fullmatch(r"(?:nova[, ]+)?(?:what(?:'s| is) (?:the )?)?(?:agent |agents |my agents? )?status[?.!]*", text, re.I):
        return "status", ""
    if re.search(r"\b(?:agents?|agent tasks?)\b", text, re.I):
        if re.match(r"(?:please )?(?:stop|cancel|halt)\b", text, re.I):
            return "stop", ""
        if re.match(r"(?:please )?(?:use|ask|have|tell|send)\b", text, re.I):
            return "capabilities", ""
        if re.search(r"\b(results|findings|found|learned)\b", text, re.I):
            return "results", ""
        if re.search(r"\b(status|progress|doing|finished|running|completed)\b", text, re.I):
            return "status", ""
        if re.search(r"\b(can|capabilities|available|which|who)\b", text, re.I):
            return "capabilities", ""
    return None


def status_reply(status: dict) -> str:
    state = status["state"]
    if state not in {"READY", "HALTED"}:
        return "My governed agent runtime is not ready. No agent work can start until its local model and audit storage are available."
    graphs = status.get("graphs", [])
    active = [graph for graph in graphs if graph["status"] == "RUNNING"]
    if not graphs:
        return "My agent runtime is halted." if state == "HALTED" else "My research agents are ready. No agent tasks have run in this backend session."
    selected = active if active else graphs[:1]
    parts = ["My agent runtime is halted." if state == "HALTED" else
             f"I have {len(active)} active agent run{'s' if len(active) != 1 else ''}." if active else "My latest agent run has finished."]
    for graph in selected[:3]:
        parts.append(f"{graph['finished_tasks']} of {graph['total_tasks']} tasks finished "
                     f"({graph['finished_percent'] or 0:g}%); {graph['successful_tasks']} successful. "
                     f"Run outcome: {graph['status'].lower()}.")
        for node in graph["nodes"][:6]:
            outcome = node.get("result_status") if node["state"] == "COMPLETED" else node["state"]
            parts.append(f"{node['name']}: {(outcome or node['state']).lower()}.")
    return " ".join(parts)


class AgentConversation:
    def __init__(self, owner) -> None:
        self.owner = owner

    def handle(self, message: str) -> dict | None:
        command = agent_command(message)
        if command is None:
            return None
        action, objective = command
        if action == "capabilities":
            response = ("I can delegate read-only web research to named tasks: Scout discovers sources, "
                        "Atlas checks independent sources, and Prism compares their findings. They share "
                        "the research-agent permission set, with at most two running at once. "
                        "Just say 'search about' followed by a topic; you do not need to name an agent. "
                        "Ask 'research status' or 'what did you find?' for updates. "
                        "NOVA also has a local developer quiz: say 'play a game'. It is a conversation game, not a tool-enabled agent. "
                        "Code changes, shell execution and other write actions are not enabled for these agents.")
            return {"response": response, "intent": "agent_runtime", "action": "agent_capabilities",
                    "data": {"monitor_url": "/agents"}}
        return self.owner.command(action, objective)