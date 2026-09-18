"use strict";

(() => {
  const element = (id) => document.getElementById(id);
  const terminal = new Set(["COMPLETED", "FAILED", "SKIPPED", "CANCELLED"]);
  let snapshot = null;
  let selectedRun = null;
  let selectedTask = null;
  let pending = false;
  let timer = null;
  let controller = null;
  let renderKey = null;
  let runRenderKey = null;
  let commandPending = false;
  let connected = false;
  let hasReply = false;
  let announcementKey = null;
  let speechEnabled = false;

  function localVoice() {
    return window.speechSynthesis?.getVoices().find((voice) => voice.localService && voice.lang.startsWith("en"));
  }

  function announceTasks(graph) {
    const message = graph
      ? `${label(graph.status)}. ${graph.finished_tasks} of ${graph.total_tasks} tasks finished; ${graph.successful_tasks} successful. ${graph.nodes.map((node) => `${node.name}: ${label(nodeState(node))}`).join(". ")}.`
      : snapshot?.pending_runs ? "Research queued." : "No task activity recorded.";
    const key = `${graph?.graph_id || "none"}:${message}`;
    if (key === announcementKey) return;
    announcementKey = key;
    element("task-announcement").textContent = message;
    if (!speechEnabled || document.hidden) return;
    const voice = localVoice();
    if (!voice) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(message);
    utterance.voice = voice;
    window.speechSynthesis.speak(utterance);
  }

  function speechControls() {
    const supported = !!localVoice();
    element("speak-updates").disabled = !supported;
    element("speak-updates").title = supported ? "Speak task updates" : "No local English speech voice available";
    if (!supported) speechEnabled = false;
    element("speak-updates").setAttribute("aria-pressed", String(speechEnabled));
  }

  function commandControls() {
    const ready = connected && snapshot?.state === "READY";
    const busy = snapshot?.pending_runs || snapshot?.graphs.some((graph) => graph.status === "RUNNING");
    element("start-research").disabled = commandPending || !ready || !!busy;
    element("stop-agents").disabled = commandPending || !ready;
    element("ask-status").disabled = commandPending || !connected;
    element("ask-results").disabled = commandPending || !connected;
  }

  async function sendCommand(action, objective = "") {
    if (commandPending) return;
    commandPending = true;
    commandControls();
    try {
      const response = await fetch("/api/agent-runtime/command", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({action, objective}), signal: AbortSignal.timeout(10000),
      });
      if (!response.ok) throw new Error("Command unavailable");
      const reply = await response.json();
      element("nova-reply").textContent = reply.response;
      hasReply = true;
      if (reply.action === "agent_research_started") element("research-topic").value = "";
    } catch (error) {
      element("nova-reply").textContent = "NOVA did not acknowledge this request. Check agent status before submitting again.";
      hasReply = true;
    } finally {
      commandPending = false;
      await refresh();
      commandControls();
    }
  }

  function text(tag, value, className = "") {
    const node = document.createElement(tag);
    node.textContent = value;
    node.className = className;
    return node;
  }

  function label(state) {
    return state ? state.toLowerCase().replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase()) : "Unknown";
  }

  function badge(state) {
    const node = text("span", label(state), "badge");
    node.dataset.state = state;
    return node;
  }

  function nodeState(node) {
    return node.state === "COMPLETED" ? node.result_status || node.state : node.state;
  }

  function duration(milliseconds) {
    const seconds = Math.floor(Math.max(0, milliseconds) / 1000);
    return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  }

  function selectedGraph() {
    return snapshot?.graphs.find((graph) => graph.graph_id === selectedRun);
  }

  function runName(graph) {
    return graph.nodes[0]?.name || "Task graph";
  }

  function renderRuns() {
    const query = element("run-search").value.trim().toLowerCase();
    const runs = (snapshot?.graphs || []).filter((graph) => `${graph.graph_id} ${graph.nodes.map((node) => node.name).join(" ")}`.toLowerCase().includes(query));
    const key = JSON.stringify([selectedRun, query, runs.map((graph) => [graph.graph_id, runName(graph), graph.status, graph.finished_tasks, graph.total_tasks])]);
    if (key === runRenderKey) return;
    runRenderKey = key;
    const list = element("run-list");
    const focused = document.activeElement?.dataset.runId;
    list.replaceChildren();
    element("run-count").textContent = snapshot?.graphs.length || 0;
    if (!runs.length) list.append(text("p", query ? "No matching runs" : "No recorded runs", "rail-empty"));
    for (const graph of runs) {
      const button = text("button", "", "run-item");
      button.type = "button";
      button.dataset.runId = graph.graph_id;
      button.setAttribute("aria-pressed", String(graph.graph_id === selectedRun));
      button.append(text("span", runName(graph), "run-name"));
      const meta = text("span", "", "run-meta");
      meta.append(badge(graph.status), text("span", `${graph.finished_tasks}/${graph.total_tasks}`));
      button.append(meta);
      button.addEventListener("click", () => {
        selectedRun = graph.graph_id;
        selectedTask = null;
        renderKey = null;
        renderRuns();
        renderGraph();
      });
      list.append(button);
    }
    if (focused) [...list.querySelectorAll("button")].find((button) => button.dataset.runId === focused)?.focus();
  }

  function renderRegistry() {
    element("runtime-state").textContent = label(snapshot.state);
    element("agent-count").textContent = snapshot.agents.length;
    if (!hasReply) element("nova-reply").textContent = snapshot.state === "READY"
      ? "Scout, Atlas and Prism are ready for read-only research."
      : snapshot.state === "HALTED" ? "Agent work is halted."
      : snapshot.state === "UNAVAILABLE" ? `Agent runtime unavailable: ${snapshot.reason_code || "startup checks failed"}.`
      : "The agent runtime is not attached to this backend.";
    const registry = element("agent-registry");
    registry.replaceChildren();
    for (const agent of snapshot.agents) {
      const entry = text("div", "", "registry-agent");
      entry.append(text("strong", agent.id.replaceAll("_", " ")),
        text("small", `${agent.enabled ? "Enabled" : "Disabled"} / ${agent.concurrency_limit} concurrent / ${label(agent.risk)}`),
        text("small", agent.capabilities.join(", ")));
      registry.append(entry);
    }
  }

  function matches(node) {
    const query = element("task-search").value.trim().toLowerCase();
    if (!`${node.name} ${node.id} ${node.agent}`.toLowerCase().includes(query)) return false;
    switch (element("task-filter").value) {
      case "active": return ["RUNNING", "RETRYING"].includes(node.state);
      case "queued": return node.state === "QUEUED";
      case "finished": return terminal.has(node.state);
      case "issues": return ["FAILED", "PARTIAL", "REFUSED", "SKIPPED", "CANCELLED"].includes(nodeState(node));
      default: return true;
    }
  }

  function renderDetails(graph) {
    const node = graph?.nodes.find((item) => item.id === selectedTask);
    if (!node) {
      element("task-detail").close();
      return;
    }
    element("detail-title").textContent = node.name;
    element("detail-state").textContent = label(nodeState(node));
    element("detail-state").dataset.state = nodeState(node);
    const fields = element("detail-fields");
    fields.replaceChildren();
    const dependencies = node.depends_on.map((id) => graph.nodes.find((item) => item.id === id)?.name || id);
    const values = {"Task ID": node.id, "Agent": node.agent, "Run": graph.graph_id,
      "Attempt": String(node.attempts), "Dependencies": dependencies.join(", ") || "None",
      "Outcome": node.result_status ? label(node.result_status) : "Pending"};
    for (const [name, value] of Object.entries(values)) {
      const row = document.createElement("div");
      row.append(text("dt", name), text("dd", value));
      fields.append(row);
    }
  }

  function renderGraph() {
    const graph = selectedGraph();
    announceTasks(graph);
    const nodes = graph?.nodes || [];
    const visible = nodes.filter(matches);
    element("run-id").textContent = graph?.graph_id || "No run selected";
    element("run-title").textContent = graph ? runName(graph) : "Agent activity";
    element("run-status").hidden = !graph;
    element("run-status").textContent = label(graph?.status);
    element("run-status").dataset.state = graph?.status || "";
    element("finished").textContent = graph ? `${graph.finished_tasks} / ${graph.total_tasks}` : "--";
    element("successful").textContent = graph ? String(graph.successful_tasks) : "--";
    element("in-progress").textContent = graph ? String(nodes.filter((node) => ["RUNNING", "RETRYING"].includes(node.state)).length) : "--";
    element("elapsed").textContent = graph ? duration(graph.elapsed_ms) : "--";
    element("progress-label").textContent = graph?.finished_percent != null ? `${graph.finished_percent}% finished` : "--";
    element("progress").value = graph?.finished_percent || 0;
    element("task-count").textContent = nodes.length;
    element("task-table").hidden = !visible.length;
    element("empty").hidden = !!visible.length;
    if (!visible.length) {
      const disabled = ["DISABLED", "UNAVAILABLE", "STARTING"].includes(snapshot?.state);
      element("empty-title").textContent = graph ? "No matching tasks" : disabled ? "Runtime not ready" : snapshot?.pending_runs ? "Research queued" : "No graph runs yet";
      element("empty-description").textContent = graph ? "No tasks match the current filters." : disabled ? "No agent work is running." : "No task activity has been recorded in this session.";
    }
    const key = JSON.stringify([selectedRun, visible]);
    if (key !== renderKey) {
      renderKey = key;
      const rows = element("task-rows");
      const focused = document.activeElement?.dataset.taskId;
      rows.replaceChildren();
      for (const node of visible) {
        const row = text("div", "", "task-row");
        row.setAttribute("role", "row");
        const name = text("div", "");
        name.append(text("div", node.name, "task-name"), text("div", node.agent.replaceAll("_", " "), "task-agent"));
        const dependencies = node.depends_on.map((id) => graph.nodes.find((item) => item.id === id)?.name || id);
        const inspect = text("button", "", "icon-button");
        inspect.setAttribute("aria-label", `Inspect ${node.name}`);
        inspect.title = `Inspect ${node.name}`;
        inspect.dataset.taskId = node.id;
        const icon = document.createElement("i");
        icon.dataset.lucide = "arrow-up-right";
        icon.setAttribute("aria-hidden", "true");
        inspect.append(icon);
        inspect.addEventListener("click", () => {
          selectedTask = node.id;
          renderDetails(selectedGraph());
          element("task-detail").showModal();
        });
        for (const cell of [name, badge(nodeState(node)), text("span", node.attempts || "--"), text("span", dependencies.join(", ") || "None", "dependencies")]) {
          cell.setAttribute("role", "cell");
          row.append(cell);
        }
        const action = text("div", "");
        action.setAttribute("role", "cell");
        action.append(inspect);
        row.append(action);
        rows.append(row);
      }
      window.lucide?.createIcons();
      if (focused) [...rows.querySelectorAll("button")].find((button) => button.dataset.taskId === focused)?.focus();
    }
    if (element("task-detail").open) renderDetails(graph);
  }

  async function refresh() {
    if (pending || document.hidden) return;
    pending = true;
    clearTimeout(timer);
    element("refresh").disabled = true;
    controller = new AbortController();
    const timeout = setTimeout(() => controller?.abort(), 8000);
    try {
      const response = await fetch("/api/agent-runtime/status", {cache: "no-store", signal: controller.signal});
      if (!response.ok) throw new Error("Status unavailable");
      const next = await response.json();
      if (!Array.isArray(next.graphs) || !Array.isArray(next.agents)) throw new Error("Invalid status");
      snapshot = next;
      connected = true;
      if (!snapshot.graphs.some((graph) => graph.graph_id === selectedRun)) selectedRun = snapshot.graphs[0]?.graph_id || null;
      element("connection").dataset.state = "live";
      element("connection-label").textContent = "Connected";
      element("alert").hidden = true;
      element("updated").textContent = `Updated ${new Date(snapshot.observed_at).toLocaleTimeString()}`;
      renderRuns();
      renderRegistry();
      renderGraph();
    } catch (error) {
      connected = false;
      element("connection").dataset.state = "error";
      element("connection-label").textContent = "Disconnected";
      element("alert").hidden = false;
      element("alert").textContent = snapshot ? "Connection lost. Showing the last received snapshot." : "Runtime status is unavailable. Reconnecting to the local monitor.";
      if (!snapshot) {
        element("empty-title").textContent = "Status unavailable";
        element("empty-description").textContent = "No snapshot has been received.";
      }
    } finally {
      clearTimeout(timeout);
      pending = false;
      controller = null;
      element("refresh").disabled = false;
      commandControls();
      if (!document.hidden) timer = setTimeout(refresh, 1500);
    }
  }

  element("refresh").addEventListener("click", refresh);
  element("speak-updates").addEventListener("click", () => {
    speechEnabled = !speechEnabled && !!localVoice();
    window.speechSynthesis?.cancel();
    speechControls();
    if (speechEnabled) {
      announcementKey = null;
      announceTasks(selectedGraph());
    }
  });
  element("research-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!element("start-research").disabled) sendCommand("research", element("research-topic").value.trim());
  });
  element("ask-status").addEventListener("click", () => sendCommand("status"));
  element("ask-results").addEventListener("click", () => sendCommand("results"));
  element("stop-agents").addEventListener("click", () => element("stop-confirm").showModal());
  element("stop-confirm").addEventListener("close", () => {
    if (element("stop-confirm").returnValue === "stop") sendCommand("stop");
    element("stop-confirm").returnValue = "";
  });
  element("run-search").addEventListener("input", renderRuns);
  element("task-search").addEventListener("input", renderGraph);
  element("task-filter").addEventListener("change", renderGraph);
  element("close-detail").addEventListener("click", () => element("task-detail").close());
  document.addEventListener("visibilitychange", () => {
    clearTimeout(timer);
    if (document.hidden) {
      controller?.abort();
      if (speechEnabled) window.speechSynthesis?.cancel();
    }
    else refresh();
  });
  window.addEventListener("pagehide", () => {
    clearTimeout(timer);
    controller?.abort();
    if (speechEnabled) window.speechSynthesis?.cancel();
    window.speechSynthesis?.removeEventListener("voiceschanged", speechControls);
  });
  window.speechSynthesis?.addEventListener("voiceschanged", speechControls);
  speechControls();
  window.lucide?.createIcons();
  refresh();
})();