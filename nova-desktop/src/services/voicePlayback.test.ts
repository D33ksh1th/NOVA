import { apiVoiceSpeak, apiVoiceStop } from "./api";

describe("voice playback lifecycle", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("does not mark newer playback finished when an old response arrives", async () => {
    let finishOld!: (response: Response) => void;
    let finishNew!: (response: Response) => void;
    const fetchMock = vi.fn()
      .mockReturnValueOnce(new Promise<Response>(resolve => { finishOld = resolve; }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true })))
      .mockReturnValueOnce(new Promise<Response>(resolve => { finishNew = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    const events: boolean[] = [];
    const onPlayback = (event: Event) => events.push((event as CustomEvent).detail.active);
    window.addEventListener("nova-playback", onPlayback);
    try {
      const oldSpeech = apiVoiceSpeak("Old", {});
      await apiVoiceStop();
      const newSpeech = apiVoiceSpeak("New", {});
      finishOld(new Response(JSON.stringify({ success: false, error: "interrupted" })));
      await oldSpeech;
      expect(events).toEqual([true, false, true]);
      finishNew(new Response(JSON.stringify({ success: true })));
      await newSpeech;
      expect(events).toEqual([true, false, true, false]);
    } finally {
      window.removeEventListener("nova-playback", onPlayback);
    }
  });

  it("reports a speech backend failure instead of pretending playback succeeded", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: false, error: "speech_failed" }))));
    await expect(apiVoiceSpeak("Reply", {})).rejects.toThrow("speech_failed");
  });
});