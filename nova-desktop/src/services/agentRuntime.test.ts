import { apiAgentRuntimeCommand, apiAgentRuntimeStatus } from "./api";

describe("governed runtime API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("preserves the backend API prefix and passes cancellation", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ state: "READY" }) });
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    expect(await apiAgentRuntimeStatus(controller.signal)).toEqual({ state: "READY" });
    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/api\/agent-runtime\/status$/),
      expect.objectContaining({ signal: controller.signal, cache: "no-store" }));
  });

  it("sends an explicit bounded research command", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ action: "agent_research_started" }) });
    vi.stubGlobal("fetch", fetchMock);
    await apiAgentRuntimeCommand("research", "local speech models");
    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/api\/agent-runtime\/command$/),
      expect.objectContaining({ method: "POST", body: JSON.stringify({ action: "research", objective: "local speech models" }) }));
  });

  it("does not retry or report success after rejection", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 403, text: async () => "Denied" });
    vi.stubGlobal("fetch", fetchMock);
    await expect(apiAgentRuntimeCommand("stop")).rejects.toThrow("403");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});