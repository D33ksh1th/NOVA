import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { ResearchReports, safeSourceUrl } from "./ResearchReports";
import { apiResearchReport, apiResearchReports } from "@/services/api";
import { useAppStore } from "@/stores/useAppStore";
import { OpenResearchReport } from "./OpenResearchReport";

vi.mock("@/services/api", () => ({ apiResearchReport: vi.fn(), apiResearchReports: vi.fn() }));

describe("saved research reports", () => {
  let container: HTMLDivElement;
  let root: Root;
  beforeEach(() => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    useAppStore.setState({ activeReportId: "saved-report" });
    const summary = { id: "saved-report", topic: "Laptop comparison", status: "PARTIAL", created_at: "2026-09-09T10:00:00Z" };
    vi.mocked(apiResearchReports).mockResolvedValue({ items: [summary], total: 1 });
    vi.mocked(apiResearchReport).mockResolvedValue({ ...summary, updated_at: summary.created_at, graph_id: "graph", elapsed_ms: 1500,
      tasks: [{ id: "scout", name: "Scout", agent: "research_agent", state: "COMPLETED", result_status: "SUCCESS", attempts: 1, depends_on: [] }],
      findings: [{ task_id: "scout", agent_name: "Scout", text: "A sourced finding <img src=x>", source_ids: ["evidence"] }],
      sources: [{ id: "evidence", url: "https://example.com/review", domain: "example.com", retrieved_at: summary.created_at, digest: "hash" }],
      images: [{ id: "image", title: "Laptop", url: "https://external-content.duckduckgo.com/image.jpg", source_url: "https://example.com/review", retrieved_at: summary.created_at, digest: "hash" }],
      gaps: [{ task_id: "prism", name: "Prism", reason: "Citations could not be verified." }] });
    container = document.createElement("div"); document.body.append(container); root = createRoot(container);
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

  it("reopens saved findings safely with citations and unresolved outcomes", async () => {
    await act(async () => root.render(<ResearchReports />));
    expect(apiResearchReport).toHaveBeenCalledWith("saved-report", expect.any(AbortSignal));
    expect(container.textContent).toContain("A sourced finding <img src=x>");
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector('a[href="https://example.com/review"]')).not.toBeNull();
    expect(container.textContent).toContain("Citations could not be verified.");
    const sources = [...container.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent === "Sources")!;
    await act(async () => sources.click());
    expect(container.textContent).toContain("Evidence record");
  });

  it("shows storage errors without inventing saved history", async () => {
    vi.mocked(apiResearchReports).mockRejectedValue(new Error("offline"));
    vi.mocked(apiResearchReport).mockRejectedValue(new Error("offline"));
    await act(async () => root.render(<ResearchReports />));
    expect(container.textContent).toContain("Saved history is unavailable");
    expect(container.textContent).not.toContain("A sourced finding");
  });

  it("highlights cited Prism takeaways and shows comparison focus and measured coverage", async () => {
    const report = await apiResearchReport("saved-report");
    const finding = { ...report.findings[0], task_id: "prism", agent_name: "Prism", text: "Lower deployment effort, but limited benchmark evidence.", category: "tradeoff" as const, subject: "Deployment effort", priority: "high" as const };
    vi.mocked(apiResearchReport).mockResolvedValue({ ...report, findings: [finding], key_takeaways: [finding], coverage: {
      cited_domains: 1, evidence_scope: "search_results", searches: [{ task_id: "scout", agent_name: "Scout", query: "official documentation", status: "OK", sources: 5, reviewed_sources: 3 }],
    } });
    await act(async () => root.render(<ResearchReports />));
    const takeaways = container.querySelector('[aria-label="Key takeaways"]');
    expect(takeaways?.textContent).toContain("Deployment effort");
    expect(takeaways?.querySelector('a[href="https://example.com/review"]')).not.toBeNull();
    expect(container.textContent).toContain("source pages have not been read in full");
    await act(async () => [...container.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(button => button.textContent === "Comparison")!.click());
    expect(container.querySelector("table")?.textContent).toContain("tradeoff");
    await act(async () => [...container.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(button => button.textContent === "Coverage")!.click());
    expect(container.textContent).toContain("5 retrieved records / 3 supplied to the model");
  });

  it("rejects executable source links", () => {
    expect(safeSourceUrl("javascript:alert(1)")).toBeUndefined();
    expect(safeSourceUrl("https://user:password@example.com")).toBeUndefined();
    expect(safeSourceUrl("https://example.com/review")).toBe("https://example.com/review");
  });

  it("shows scored source and image relevance without implying verification", async () => {
    const report = await apiResearchReport("saved-report");
    const relevance = { score: 75, query: "Laptop battery", matched_terms: ["laptop"], missing_terms: ["battery"], method: "lexical-v1" };
    vi.mocked(apiResearchReport).mockResolvedValue({ ...report,
      coverage: { cited_domains: 1, evidence_scope: "search_results", searches: [{ task_id: "scout", agent_name: "Scout", query: "Laptop battery", status: "OK", sources: 8, reviewed_sources: 5,
        retrieval: { candidate_sources: 52, providers_requested: ["duckduckgo", "bing", "brave", "google"], pages_crawled: 0 } }] },
      sources: [{ ...report.sources[0], relevance }], images: [{ ...report.images![0], relevance }] });
    await act(async () => root.render(<ResearchReports />));
    async function tab(name: string) {
      await act(async () => [...container.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(button => button.textContent === name)!.click());
    }
    await tab("Sources");
    expect(container.textContent).toContain("Relevance: 75/100");
    expect(container.textContent).toContain("Missing termsbattery");
    expect(container.textContent).toContain("not factual or visual verification");
    await tab("Images");
    expect(container.querySelector("figure")?.textContent).toContain("Relevance: 75/100");
    expect(container.querySelector("img")).toBeNull();
    await tab("Coverage");
    expect(container.textContent).toContain("52 unique eligible source candidates / 4 providers requested / Search snippets");
    expect(container.textContent).toContain("0 extracts downloaded / 0 attempts / 0 supplied to the model");
  });

  it("distinguishes downloaded, supplied, truncated and unavailable page extracts", async () => {
    const report = await apiResearchReport("saved-report");
    const page = { task_id: "scout", agent_name: "Scout", url: "https://example.com/review", status: "READ", supplied_to_model: true, truncated: true };
    vi.mocked(apiResearchReport).mockResolvedValue({ ...report, coverage: {
      cited_domains: 1, evidence_scope: "search_results_and_page_extracts", searches: [],
      page_reads: [page, { ...page, supplied_to_model: false }, { ...page, status: "UNAVAILABLE", supplied_to_model: false, truncated: false }],
    } });
    await act(async () => root.render(<ResearchReports />));
    expect(container.textContent).toContain("1 page extracts supplied to the model");
    expect(container.textContent).not.toContain("source pages have not been read in full");
    await act(async () => [...container.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(button => button.textContent === "Coverage")!.click());
    expect(container.textContent).toContain("2 extracts downloaded / 3 attempts / 1 supplied to the model");
    expect(container.textContent).toContain("Downloaded; excluded from context");
    expect(container.textContent).toContain("Unavailable or denied");
    expect(container.textContent).toContain("Truncated extract");
  });

  it("shows scoped repository findings and non-navigating file citations", async () => {
    const report = await apiResearchReport("saved-report");
    vi.mocked(apiResearchReport).mockResolvedValue({ ...report, kind: "repository_review",
      scope: { repository: "nova-desktop", files: ["src/App.tsx"], mode: "READ_ONLY" },
      sources: [{ ...report.sources[0], kind: "file_content", url: "repo:src/App.tsx", domain: "nova-desktop" }] });
    await act(async () => root.render(<ResearchReports />));
    expect(container.textContent).toContain("nova-desktop / READ_ONLY");
    expect(container.textContent).toContain("[1] src/App.tsx");
    expect(container.textContent).toContain("No tests executed or files changed");
    expect(container.querySelector('a[href^="repo:"]')).toBeNull();
    expect([...container.querySelectorAll('[role="tab"]')].map(tab => tab.textContent)).toEqual(["Overview", "Sources", "Activity"]);
    await act(async () => [...container.querySelectorAll<HTMLButtonElement>("button")].find(button => button.textContent === "Sources")!.click());
    expect(container.querySelector('[role="tabpanel"] a')).toBeNull();
    expect(container.textContent).toContain("SHA-256: hash");
  });

  it("loads source images only on request and handles broken images", async () => {
    await act(async () => root.render(<ResearchReports />));
    await act(async () => [...container.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent === "Images")!.click());
    expect(container.querySelector("img")).toBeNull();
    await act(async () => container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click());
    const image = container.querySelector("img")!;
    expect(image.getAttribute("referrerpolicy")).toBe("no-referrer");
    await act(async () => image.dispatchEvent(new Event("error")));
    expect(container.textContent).toContain("Image unavailable");
  });

  it("opens the exact saved report from chat", async () => {
    await act(async () => root.render(<OpenResearchReport identity="older-report" />));
    await act(async () => container.querySelector("button")!.click());
    expect(useAppStore.getState().currentPage).toBe("skills");
    expect(useAppStore.getState().activeReportId).toBe("older-report");
  });

  it("renders approved Bing thumbnails but rejects untrusted hosts", async () => {
    const report = await apiResearchReport("saved-report");
    vi.mocked(apiResearchReport).mockResolvedValue({ ...report, images: [
      { ...report.images![0], url: "https://ts1.mm.bing.net/image.jpg" },
      { ...report.images![0], id: "unsafe", url: "https://ts1.mm.bing.net.evil.test/image.jpg" },
    ] });
    await act(async () => root.render(<ResearchReports />));
    await act(async () => [...container.querySelectorAll<HTMLButtonElement>("button")].find(button => button.textContent === "Images")!.click());
    expect(container.querySelectorAll("figure")).toHaveLength(1);
    expect(container.querySelector("img")).toBeNull();
    await act(async () => container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click());
    expect(container.querySelector("img")!.src).toBe("https://ts1.mm.bing.net/image.jpg");
    expect(container.textContent).toContain("not visually verified");
  });

  it("hides unrelated images in older reports while preserving a cited-page image", async () => {
    const report = await apiResearchReport("saved-report");
    vi.mocked(apiResearchReport).mockResolvedValue({ ...report,
      sources: [...report.sources, { ...report.sources[0], id: "uncited", url: "https://example.com/uncited" }],
      images: [
        { ...report.images![0], source_url: "https://example.com/review#photo" },
        { ...report.images![0], id: "other-page", title: "Unrelated subject", source_url: "https://example.com/other" },
        { ...report.images![0], id: "unused-source", title: "Uncited subject", source_url: "https://example.com/uncited" },
      ] });
    await act(async () => root.render(<ResearchReports />));
    await act(async () => [...container.querySelectorAll<HTMLButtonElement>("button")].find(button => button.textContent === "Images")!.click());
    expect(container.querySelectorAll("figure")).toHaveLength(1);
    expect(container.textContent).not.toContain("Unrelated subject");
    expect(container.textContent).not.toContain("Uncited subject");
    expect(container.querySelector("img")).toBeNull();
  });

  it("shows no images instead of unrelated fallback candidates when findings are empty", async () => {
    const report = await apiResearchReport("saved-report");
    vi.mocked(apiResearchReport).mockResolvedValue({ ...report, findings: [] });
    await act(async () => root.render(<ResearchReports />));
    await act(async () => [...container.querySelectorAll<HTMLButtonElement>("button")].find(button => button.textContent === "Images")!.click());
    expect(container.textContent).toContain("No images matched the cited findings.");
    expect(container.querySelector("figure")).toBeNull();
    expect(container.querySelector('input[type="checkbox"]')).toBeNull();
  });
});