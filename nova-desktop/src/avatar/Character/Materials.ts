export const NOVA_MATERIALS = {
  fur: {
    baseColor: "#c98643",
    roughness: 0.82,
    metalness: 0.02,
    notes: "Phase B placeholder; replace with baked fur cards material set.",
  },
  eyes: {
    baseColor: "#6aa94a",
    roughness: 0.12,
    clearcoat: 1.0,
    notes: "Separate cornea + iris + moisture shell in Phase C.",
  },
  nose: {
    baseColor: "#d88fa2",
    roughness: 0.56,
    notes: "Slight wet spec response.",
  },
  pendant: {
    baseColor: "#38dfff",
    emissive: "#38dfff",
    emissiveIntensity: 0.65,
    notes: "Driven by thinking/response events.",
  },
} as const;
