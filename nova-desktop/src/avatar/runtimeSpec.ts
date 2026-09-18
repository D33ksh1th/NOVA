import type { AvatarState } from "@/types";

export type NovaEmotionState =
  | "happy"
  | "concerned"
  | "curious"
  | "excited"
  | "focused"
  | "listening"
  | "thinking"
  | "speaking"
  | "sleeping"
  | "relaxed"
  | "proud"
  | "shy";

export const REQUIRED_BLEND_SHAPES = [
  "Smile",
  "Frown",
  "Concern",
  "Surprised",
  "Thinking",
  "Sleepy",
  "Happy",
  "Curious",
  "Blink_Left",
  "Blink_Right",
  "Eye_Squint",
  "Mouth_Open",
  "Mouth_Closed",
  "AA",
  "E",
  "I",
  "O",
  "U",
  "FV",
  "MBP",
  "L",
  "WQ",
  "Rest",
] as const;

export const REQUIRED_ANIMATION_CLIPS = [
  "NOVA_Idle_01",
  "NOVA_Idle_02",
  "NOVA_Idle_03",
  "NOVA_Idle_04",
  "NOVA_Blink",
  "NOVA_Ear_Twitch",
  "NOVA_Tail_Movement",
  "NOVA_Stretch",
  "NOVA_Yawn",
  "NOVA_Walk",
  "NOVA_Run",
  "NOVA_Sit",
  "NOVA_Lie_Down",
  "NOVA_Sleep",
  "NOVA_Wake_Up",
  "NOVA_Eat",
  "NOVA_Drink",
  "NOVA_Look_Around",
  "NOVA_Observe_User",
  "NOVA_Listen",
  "NOVA_Thinking",
  "NOVA_Talking",
  "NOVA_Celebrate",
  "NOVA_Happy_Jump",
  "NOVA_Confused",
  "NOVA_Concerned",
  "NOVA_Scratch_Ear",
  "NOVA_Clean_Paw",
  "NOVA_Tail_Wag",
] as const;

const STATE_CANDIDATES: Record<AvatarState, string[]> = {
  idle: ["NOVA_Idle_01", "NOVA_Idle_02", "NOVA_Observe_User", "idle"],
  listening: ["NOVA_Listen", "NOVA_Look_Around", "listen"],
  thinking: ["NOVA_Thinking", "NOVA_Confused", "thinking"],
  speaking: ["NOVA_Talking", "NOVA_Tail_Wag", "talk"],
  sleeping: ["NOVA_Sleep", "NOVA_Lie_Down", "sleep"],
  happy: ["NOVA_Celebrate", "NOVA_Happy_Jump", "NOVA_Tail_Wag"],
  curious: ["NOVA_Look_Around", "NOVA_Observe_User"],
  concerned: ["NOVA_Concerned", "NOVA_Confused"],
  excited: ["NOVA_Celebrate", "NOVA_Happy_Jump"],
  focused: ["NOVA_Observe_User", "NOVA_Thinking"],
  relaxed: ["NOVA_Idle_03", "NOVA_Idle_04", "NOVA_Sit"],
  proud: ["NOVA_Sit", "NOVA_Observe_User"],
  shy: ["NOVA_Look_Around", "NOVA_Idle_02"],
};

function normalizeName(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function buildIndex(availableClips: string[]) {
  const map = new Map<string, string>();
  for (const clip of availableClips) {
    map.set(normalizeName(clip), clip);
  }
  return map;
}

export function resolveClipForState(
  avatarState: AvatarState,
  availableClips: string[],
  overrideClip?: string | null
): string | null {
  if (!availableClips.length) return null;

  const index = buildIndex(availableClips);

  if (overrideClip) {
    const hit = index.get(normalizeName(overrideClip));
    if (hit) return hit;
  }

  const candidates = STATE_CANDIDATES[avatarState] ?? STATE_CANDIDATES.idle;
  for (const candidate of candidates) {
    const hit = index.get(normalizeName(candidate));
    if (hit) return hit;
  }

  return availableClips[0] ?? null;
}

export function missingRequiredClips(availableClips: string[]): string[] {
  const index = buildIndex(availableClips);
  return REQUIRED_ANIMATION_CLIPS.filter((clip) => !index.has(normalizeName(clip)));
}
