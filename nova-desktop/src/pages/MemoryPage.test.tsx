import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryPage } from "./MemoryPage";
import { apiMemories, apiSaveMemory } from "@/services/api";
vi.mock("@/services/api", () => ({ apiMemories: vi.fn(), apiSaveMemory: vi.fn() }));
describe("saved memory view", () => {
  let container: HTMLDivElement;
  let root: Root;
  beforeEach(() => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    vi.clearAllMocks();
    vi.mocked(apiMemories).mockResolvedValue({ preference: "<img src=x>" });
    container = document.createElement("div"); document.body.append(container); root = createRoot(container);
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
  it("renders actual stored values as text without writing on load", async () => {
    await act(async () => root.render(<MemoryPage />));
    expect(container.textContent).toContain("<img src=x>");
    expect(container.querySelector("img")).toBeNull();
    expect(apiSaveMemory).not.toHaveBeenCalled();
    await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Edit preference"]')!.click());
    expect(container.querySelector<HTMLTextAreaElement>('textarea[aria-label="Memory value"]')!.value).toBe("<img src=x>");
    expect(apiSaveMemory).not.toHaveBeenCalled();
  });
  it("shows an unavailable state instead of sample personal facts", async () => {
    vi.mocked(apiMemories).mockRejectedValue(new Error("offline"));
    await act(async () => root.render(<MemoryPage />));
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Saved memory is unavailable");
    expect(container.querySelectorAll("article")).toHaveLength(0);
  });
  it("requires overwrite confirmation and refreshes after an explicit save", async () => {
    const confirmation = vi.spyOn(window, "confirm").mockReturnValue(false);
    vi.mocked(apiSaveMemory).mockResolvedValue({ status: "stored", key: "preference" });
    await act(async () => root.render(<MemoryPage />));
    await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Edit preference"]')!.click());
    await act(async () => container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
    expect(apiSaveMemory).not.toHaveBeenCalled();
    confirmation.mockReturnValue(true);
    await act(async () => container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
    expect(apiSaveMemory).toHaveBeenCalledTimes(1);
    expect(apiSaveMemory).toHaveBeenCalledWith("preference", "<img src=x>");
    expect(apiMemories).toHaveBeenCalledTimes(2);
    expect(container.querySelector("form")).toBeNull();
  });
  it("preserves the draft when saving fails", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(apiSaveMemory).mockRejectedValue(new Error("offline"));
    await act(async () => root.render(<MemoryPage />));
    await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Edit preference"]')!.click());
    await act(async () => container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Your draft is still available");
    expect(container.querySelector("textarea")!.value).toBe("<img src=x>");
  });
});