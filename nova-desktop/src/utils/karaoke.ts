/**
 * Progressive word-reveal ("karaoke") for NOVA subtitle display.
 *
 * Reveals words one at a time at the given WPM rate, calling onUpdate on
 * each step. Returns a cancel function — call it to abort early (the full
 * text is shown immediately on cancel so nothing is lost).
 */
export function startKaraoke(
  text: string,
  wpm: number,
  onUpdate: (partial: string) => void
): () => void {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return () => {};

  // Total estimated TTS duration for the whole text.
  // Piper/system TTS speaks at roughly 2.4 words/sec regardless of the WPM setting
  // (the rate slider mainly affects pauses, not syllable speed).
  // We spread the reveal evenly over that estimated duration so karaoke
  // tracks the real audio rather than using WPM directly.
  const effectiveWps = 2.4; // words per second — empirically matches Piper output
  const totalMs = (words.length / effectiveWps) * 1000;
  const msPerWord = totalMs / words.length;

  let current = 0;
  let cancelled = false;
  let timer: number | null = null;

  const reveal = () => {
    if (cancelled) return;
    current++;
    onUpdate(words.slice(0, current).join(" "));
    if (current < words.length) {
      timer = window.setTimeout(reveal, msPerWord);
    }
  };

  // Small initial delay so the first word appears just as audio starts.
  timer = window.setTimeout(reveal, 200);

  return () => {
    cancelled = true;
    if (timer !== null) window.clearTimeout(timer);
    onUpdate(text); // snap to full text on cancel/stop
  };
}
