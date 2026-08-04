export function toSubtitleText(input: string): string {
  let text = (input || "").trim();
  if (!text) return "";

  const infoLike =
    /bluetooth|connected devices?|paired|saved devices?|nearby scan|available devices?|pair\/connect|pairing readiness/i.test(text);

  // Remove fenced code and inline formatting markers that should not appear in subtitles.
  text = text.replace(/```[\s\S]*?```/g, " ");
  text = text.replace(/`([^`]+)`/g, "$1");
  text = text.replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1");
  text = text.replace(/\*\*([^*]+)\*\*/g, "$1");
  text = text.replace(/\*([^*]+)\*/g, "$1");
  text = text.replace(/__([^_]+)__/g, "$1");
  text = text.replace(/_([^_]+)_/g, "$1");
  text = text.replace(/~~([^~]+)~~/g, "$1");
  text = text.replace(/^#{1,6}\s*/gm, "");

  if (!infoLike) {
    // Default mode: keep subtitles compact for normal chat responses.
    text = text.replace(/^\s*[-*+]\s+/gm, "");
    text = text.replace(/\s+/g, " ").trim();
    return text;
  }

  // Info mode: preserve section structure and bullet pointers.
  text = text.replace(/:\s*-\s+/g, ":\n- ");
  text = text.replace(/\)\s*-\s+/g, ")\n- ");
  text = text.replace(/-\s+None\s+(Paired\s+Not\s+Connected\s*\(\d+\):)/gi, "- None\n\n$1");
  text = text.replace(/-\s+None\s+(Saved\s+Devices\s+You\s+Can\s+Connect\s*\(\d+\):)/gi, "- None\n\n$1");
  text = text.replace(/-\s+None\s+(Nearby\s+Scan\s+Results\s*\(\d+\):)/gi, "- None\n\n$1");

  const sectionLabels = [
    /Bluetooth Status/gi,
    /Devices Available For Pairing/gi,
    /Controller State\s*:\s*/gi,
    /Discoverable\s*:\s*/gi,
    /Controller Addr\s*:\s*/gi,
    /Connected Devices\s*\(\d+\):/gi,
    /Paired Not Connected\s*\(\d+\):/gi,
    /Saved Devices You Can Connect\s*\(\d+\):/gi,
    /Nearby Scan Results\s*\(\d+\):/gi,
    /Paired Devices\s*\(\d+\):/gi,
    /Available Devices\s*:/gi,
    /Pairing Readiness\s*:/gi,
    /To pair\/connect, say:/gi,
  ];

  for (const section of sectionLabels) {
    text = text.replace(section, (m) => `\n${m}`);
  }

  text = text.replace(/[ \t]+/g, " ");
  text = text.replace(/\n{3,}/g, "\n\n");
  return text.trim();
}
