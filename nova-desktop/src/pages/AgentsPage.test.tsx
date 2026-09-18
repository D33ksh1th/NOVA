import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { AgentsPage } from "./AgentsPage";
import { apiAgentRuntimeCommand, apiAgentRuntimeStatus, apiRepositoryReview } from "@/services/api";

vi.mock("@/services/api", () => ({ apiAgentRuntimeStatus: vi.fn(), apiAgentRuntimeCommand: vi.fn(), apiRepositoryReview: vi.fn() }));
vi.mock("@/components/ResearchReports", () => ({ ResearchReports: () => null }));

describe("native agent controls", () => {
  let container: HTMLDivElement;
  let root: Root;
  beforeEach(() => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    vi.mocked(apiAgentRuntimeStatus).mockReset();
    vi.mocked(apiAgentRuntimeCommand).mockReset();
    vi.mocked(apiRepositoryReview).mockReset();
    vi.mocked(apiAgentRuntimeCommand).mockResolvedValue({ action: "agent_status", response: "Actual runtime status." });
    vi.mocked(apiAgentRuntimeStatus).mockResolvedValue({ state: "READY", reason_code: "", pending_runs: 0,
      observed_at: new Date().toISOString(), agents: [], graphs: [{ graph_id: "run-test", status: "PARTIAL",
        finished_tasks: 3, successful_tasks: 2, total_tasks: 3, finished_percent: 100, elapsed_ms: 2000,
        nodes: [{ id: "prism", name: "Prism", agent: "research_agent", state: "COMPLETED",
          result_status: "PARTIAL", attempts: 1, depends_on: [] }] }] });
    HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
    HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });
  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });
  async function render() { await act(async () => root.render(<AgentsPage />)); }
  function button(title: string) { return container.querySelector<HTMLButtonElement>(`button[title="${title}"]`)!; }

  it("shows finished separately from successful and asks for actual status", async () => {
    await render();
    await act(async () => [...container.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.textContent === "Live activity")!.click());
    expect(container.textContent).toContain("3 / 3");
    expect(container.textContent).toContain("Successful2");
    expect(container.querySelector("summary")?.textContent).toContain("partial");
    await act(async () => button("Ask NOVA for agent status").click());
    expect(apiAgentRuntimeCommand).toHaveBeenCalledWith("status", "");
    expect(container.textContent).toContain("Actual runtime status.");
  });

  it("requires confirmation before stopping", async () => {
    await render();
    await act(async () => button("Stop all agents").click());
    expect(container.querySelector("dialog")?.open).toBe(true);
    const dialogButtons = container.querySelectorAll<HTMLButtonElement>("dialog button");
    await act(async () => dialogButtons[0].click());
    expect(apiAgentRuntimeCommand).not.toHaveBeenCalled();
    await act(async () => button("Stop all agents").click());
    await act(async () => dialogButtons[1].click());
    expect(apiAgentRuntimeCommand).toHaveBeenCalledWith("stop", "");
  });

  it("requires the reader grant and explicit paths before submitting a review", async () => {
    await render();
    await act(async () => [...container.querySelectorAll("button")].find(item => item.textContent === "Repository review")!.click());
    expect(button("Start repository review").disabled).toBe(true);
    expect(container.textContent).toContain("Repository reader unavailable");
    const snapshot = await vi.mocked(apiAgentRuntimeStatus).mock.results[0].value;
    vi.mocked(apiAgentRuntimeStatus).mockResolvedValue({ ...snapshot, agents: [{ id: "repo_reader", enabled: true,
      concurrency_limit: 1, capabilities: ["repo.read"], risk: "READ_ONLY" }] });
    vi.mocked(apiRepositoryReview).mockResolvedValue({ action: "agent_repository_started", response: "Review queued.", data: { report_id: "repo-fixture" } });
    await act(async () => button("Refresh agent status").click());
    async function fill(selector: string, value: string, prototype: object) {
      const element = container.querySelector(selector)!;
      await act(async () => { Object.getOwnPropertyDescriptor(prototype, "value")!.set!.call(element, value);
        element.dispatchEvent(new Event("input", { bubbles: true })); });
    }
    await fill('[aria-label="Repository question"]', "Explain routing", HTMLInputElement.prototype);
    await fill("textarea", "../outside.ts", HTMLTextAreaElement.prototype);
    expect(button("Start repository review").disabled).toBe(true);
    await fill("textarea", "src/App.tsx\nsrc/pages/AgentsPage.tsx", HTMLTextAreaElement.prototype);
    expect(button("Start repository review").disabled).toBe(false);
    await act(async () => button("Start repository review").click());
    expect(apiRepositoryReview).toHaveBeenCalledWith("Explain routing", ["src/App.tsx", "src/pages/AgentsPage.tsx"]);
    expect(apiAgentRuntimeCommand).not.toHaveBeenCalled();
    expect(container.textContent).toContain("Review queued.");
  });

  it("disables research and stop when status is unreachable", async () => {
    vi.mocked(apiAgentRuntimeStatus).mockRejectedValue(new Error("Offline"));
    await render();
    expect(container.querySelector("[role=alert]")?.textContent).toContain("unavailable");
    expect(button("Start read-only research").disabled).toBe(true);
    expect(button("Stop all agents").disabled).toBe(true);
    expect(apiAgentRuntimeCommand).not.toHaveBeenCalled();
  });

  function speech() {
    const voice = { localService: true, lang: "en-GB", name: "Local test voice" };
    const synthesis = { getVoices: vi.fn(() => [voice]), speak: vi.fn(), cancel: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn() };
    vi.stubGlobal("speechSynthesis", synthesis);
    vi.stubGlobal("SpeechSynthesisUtterance", class { constructor(public text: string) {} });
    return synthesis;
  }

  it("announces accurate task outcomes and keeps speech off by default", async () => {
    const synthesis = speech();
    await render();
    expect(container.querySelector('[aria-label="Task updates"]')?.textContent).toContain("2 successful. Prism: partial");
    expect(button("Speak task updates").getAttribute("aria-pressed")).toBe("false");
    expect(synthesis.speak).not.toHaveBeenCalled();
    await act(async () => button("Speak task updates").click());
    expect(synthesis.speak).toHaveBeenCalledTimes(1);
    expect(synthesis.speak.mock.calls[0][0].text).toContain("Prism: partial");
    await act(async () => button("Refresh agent status").click());
    expect(synthesis.speak).toHaveBeenCalledTimes(1);
    await act(async () => button("Speak task updates").click());
    expect(synthesis.cancel).toHaveBeenCalled();
  });

  it("announces transitions and disconnection rather than stale success", async () => {
    const synthesis = speech();
    await render();
    await act(async () => button("Speak task updates").click());
    vi.mocked(apiAgentRuntimeStatus).mockRejectedValue(new Error("offline"));
    await act(async () => button("Refresh agent status").click());
    expect(synthesis.speak).toHaveBeenCalledTimes(2);
    expect(synthesis.speak.mock.calls[1][0].text).toContain("Task status unavailable");
    expect(container.querySelector('[aria-label="Task updates"]')?.textContent).not.toContain("successful");
  });

  it("blocks remote voices but leaves screen-reader updates available", async () => {
    const synthesis = speech();
    synthesis.getVoices.mockReturnValue([{ localService: false, lang: "en-US", name: "Remote" }]);
    await render();
    expect(container.querySelector<HTMLButtonElement>('[aria-label="Speak task updates"]')?.disabled).toBe(true);
    expect(container.querySelector('[aria-label="Task updates"]')?.getAttribute("aria-live")).toBe("polite");
    expect(synthesis.speak).not.toHaveBeenCalled();
  });

  it("cancels owned speech when leaving the Agents page", async () => {
    const synthesis = speech();
    await render();
    await act(async () => button("Speak task updates").click());
    await act(async () => root.render(<div>Another page</div>));
    expect(synthesis.cancel).toHaveBeenCalled();
    expect(synthesis.removeEventListener).toHaveBeenCalledWith("voiceschanged", expect.any(Function));
  });
});