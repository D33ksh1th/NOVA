# ADR 0001 — Agent Runtime Split

- **Status:** Accepted (Phase 1)
- **Date:** 2026-09-04
- **Supersedes:** none
- **Superseded by:** none

## Context

NOVA already ships an agent layer under `services/agents/`
(`chat_agent`, `system_agent`, `coding_agent`, plus empty `memory_agent` and
`planner_agent`). That layer is an **intent router**: `AgentManager.execute()`
walks a list of agents, the first whose `can_handle(message, intent)` returns
`True` wins, and the selected agent forwards the raw user message to
`ToolManager.execute(message)`.

We are introducing a governed **agent runtime** with a strict security
constitution (deny-by-default capabilities, a single tool broker choke point,
hash-chained audit, bound single-use approvals, enforced budgets, and
untrusted-content isolation).

The existing intent router cannot host these invariants without a rewrite of its
public contracts (`base.Agent`, `registry.AgentRegistry`, `manager.AgentManager`
all change shape and become async). Rewriting them in place would break the
service container, which imports those exact symbols at
`packages/registry/registry.py:75`:

```python
from services.agents import (
    AgentRegistry, AgentManager, SystemAgent, ChatAgent, CodingAgent,
)
```

## Decision

Build the new governed layer in a **separate package**:
`services/agent_runtime/`. The legacy intent router at `services/agents/`
is **not modified** and continues to boot NOVA exactly as before.

This split is **temporary**. It exists only so the legacy layer can be *deleted*
rather than merged. The two packages are isolated by a hard, tested boundary:

- `services/agent_runtime/**` must not import from `services.agents.**`.
- `services/agents/**` must not import from `services.agent_runtime.**`.

Both directions are enforced by import-guard unit tests. No bridge module is
permitted — a bridge would become load-bearing and defeat the retirement plan.

Naming: inside the new package, the worker directory is
`services/agent_runtime/agents/**` (the I3 tool-import grep guard targets it).
The legacy concept is never called "agent" in new code; it is referred to as the
**intent router**.

## Legacy Tool-Reach Inventory (the unhardened surface)

The intent router's tool reach is **not** scoped by each agent's keyword list.
`can_handle` only decides *selection*; once selected, the agent passes the raw
message to the shared `ToolManager`, which dispatches to **any** registered tool
whose own `can_handle` matches. So every tool-holding agent effectively reaches
the entire tool registry.

| Intent-router agent | Holds `tool_manager`? | Actual tool reach today |
| --- | --- | --- |
| `system_agent` | yes | **Full registry** via `tool_manager.execute(message)` |
| `coding_agent` | yes | **Full registry** via `tool_manager.execute(message)` (includes `TerminalTool`, tier 2 destructive) |
| `chat_agent` | no | None directly — LLM + context builders only |
| `memory_agent` | — | File is **empty** (no behaviour) |
| `planner_agent` | — | File is **empty** (no behaviour) |

Full registry = `date`, `time`, `weather`, `location`, `web_search`, `gmail`,
`reminder`, `filesystem`, `terminal`, `system_info`, `mac`, `vision`.

**Consequence:** `system_agent` and `coding_agent` are each an
uncontrolled path to all twelve tools — including terminal command execution —
outside `ToolBroker`, capability grants, risk tiers, approvals, budgets, and the
hash-chained audit log. `coding_agent` reaching `TerminalTool` is the single
largest risk in the current surface. This is the surface the runtime exists to
replace, and the reason for constraint 1B below.

## Freeze (constraint 1B)

`services/agents/*` is in **maintenance mode** as of 2026-09-04: bug fixes only.
No new tools, capabilities, or agents are added there while `agent_runtime` is
built. Every capability added to the legacy layer is a control-bypassing path to
the same tools, so the freeze matters more than the naming.

## Retirement Sequence

The legacy layer is retired incrementally as governed replacements land. Legacy
agents are **deleted**, not maintained beside their replacements:

1. **Phase 6 — legacy `CodingAgent` DELETED** once the governed coding/exec
   agent lands. This removes the ungoverned `TerminalTool` path first, because
   it is the highest-risk reach.
2. **Legacy `SystemAgent` DELETED** when the governed System agent lands.
3. **`chat_agent`, `memory_agent`, `planner_agent` migrate or die last.**
   `chat_agent` is the fallback conversational path and has no direct action-tool
   reach, so it is lowest risk and retired last (or reshaped into a governed
   conversational agent).

Each deletion also removes the corresponding symbol from
`services/agents/__init__.py` and its import in `packages/registry/registry.py`.
Those edits happen in the phase that performs the deletion — never in Phase 1.

## Single Integration Point

The **only** permitted cross-package call is the Brain invoking the runtime:

```python
result = await agent_runtime.run_task(description, objective, hints)
```

No other cross-package call is permitted in either direction. In particular the
intent router does not call into `agent_runtime`, and `agent_runtime` does not
call into the intent router. In Phase 1 even this single entry point is **not**
wired into the Brain or Initiative Engine — invocation is manual only, and NOVA
boots identically with `agent_runtime` present and unwired.

## Structured-Args Prerequisite (Constitution I15, resolution 3C)

The governed tool contract adds a structured `invoke(**args)` entrypoint on
`services/tools/base.py` (additive; `execute(message)` is untouched and the
intent router never sees it). Constitution I15 caps any tool lacking
`SUPPORTS_STRUCTURED_ARGS = True` at `READ_ONLY` and makes the broker deny it at
`LOW` risk or above with reason `NO_STRUCTURED_ENTRYPOINT`.

**Consequence for the retirement plan:** `terminal_tool` and `filesystem_tool`
must be converted to expose `invoke(**args)` with an `ARG_SCHEMA` and a resource
scope (workspace-root prefix for filesystem, command allowlist for terminal)
**before** any writing agent can be granted them. That conversion is an explicit
**Phase 4 prerequisite**, not a Phase 6 surprise. Until it happens, the governed
layer physically cannot reach destructive tools — which is the intended safety
posture while the legacy `coding_agent` (full registry reach, including
`terminal_tool`) still exists.

## Search Backend Is a Phase 2 Decision (resolution 4G)

The Phase 1 evidence pipeline is proven against DuckDuckGo's Instant Answer API,
which is thin and returns empty for many comparison-shaped queries. That is
acceptable: Phase 1 proves the *evidence pipeline* (runtime-minted evidence,
ledger, fabrication rejection), not search quality. Selecting a real backend
(Brave / Tavily / SearxNG) is a Phase 2 decision.

**Constraint:** swapping the search backend must not require touching the
`ToolBroker` or the `EvidenceLedger`. The broker mints evidence from a stable
results contract (`data["results"] = [{title, url, snippet, source}]`); if a new
backend forces changes to the broker or ledger, the abstraction is in the wrong
place and must be corrected rather than worked around.

## Consequences

### Phase 2 Implementation Status (2026-09-08)

- All graph and planning modules live in `services/agent_runtime/`; the intent
  router stays frozen. The Phase 2 template paths are superseded by this split.
- Pydantic is the structural schema source of truth. `planning/plan_schema.json`
  is generated from `GraphPlan.model_json_schema()` and checked for drift in tests.
- Initiative invocation context is enforced as READ_ONLY, with rejection rather
  than risk downgrade. The live Initiative Engine remains unwired.
- `AgentManager.run_graph()` creates each task and delegates execution through
  the broker. Named subtasks are display labels, not new capability grants.
  The research concurrency limit remains two; a third subtask queues.
- Graph snapshots report completed task count, task states, and measured elapsed
  time. They do not interpolate per-agent percentage progress.
- The broker now requires a metered model response for research synthesis.
  Existing unmetered model adapters cannot silently report zero token usage.
- Live Brain/UI activation and writing agents are not enabled by this change.
  Remaining gates include a production metered/cancellable model adapter,
  persistent audit storage, verification, approval hardening, and bounded worker
  termination. The earlier Phase 1 completion claim did not establish all of
  these properties; passing the current offline tests is not production sign-off.

- **Positive:** the governed layer is built and tested in isolation with zero
  risk to the booting system; the legacy layer has a written death sentence
  rather than an open-ended coexistence; the boundary is machine-enforced.
- **Negative:** two agent packages exist simultaneously and two selection
  mechanisms coexist until retirement completes; contributors must know which
  package to touch (the freeze and naming rules address this).
- **Debt:** this ADR is the tracking record. It is closed when
  `services/agents/` is empty and its import in
  `packages/registry/registry.py` is gone.
