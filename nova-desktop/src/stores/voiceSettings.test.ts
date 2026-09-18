import { useSettingsStore } from "./useSettingsStore";

describe("voice settings compatibility", () => {
  const original = useSettingsStore.getState().voice;
  afterEach(() => useSettingsStore.setState({ voice: original }));

  it("repairs a persisted male model paired with a female accent", async () => {
    const migrate = useSettingsStore.persist.getOptions().migrate!;
    const result = await migrate({ voice: { ...original, model: "english_lessac", accent: "english_clear", handsFreeWake: true } }, 3);
    expect(result.voice).toMatchObject({ model: "english_lessac", accent: "english_jarvis", handsFreeWake: true });
  });

  it("preserves an explicitly selected female model", async () => {
    const migrate = useSettingsStore.persist.getOptions().migrate!;
    const result = await migrate({ voice: { ...original, model: "english_amy", accent: "english_clear" } }, 3);
    expect(result.voice).toMatchObject({ model: "english_amy", accent: "english_friday" });
  });

  it("keeps model changes consistent with the actual voice sent to TTS", () => {
    useSettingsStore.getState().setVoice({ model: "english_amy" });
    expect(useSettingsStore.getState().voice.accent).toBe("english_friday");
    useSettingsStore.getState().setVoice({ model: "english_lessac", accent: "english_clear" });
    expect(useSettingsStore.getState().voice.accent).toBe("english_jarvis");
  });
});