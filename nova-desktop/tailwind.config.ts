import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

const config: Config = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#0a0d14",
          secondary: "#111520",
          tertiary: "#161c2c",
          card: "#1a2035",
          elevated: "#1f2740",
        },
        border: {
          DEFAULT: "rgba(255,255,255,0.07)",
          subtle: "rgba(255,255,255,0.04)",
          accent: "rgba(255,165,50,0.25)",
        },
        nova: {
          orange: "#f97316",
          amber: "#fbbf24",
          glow: "#ff6b1a",
          dim: "#7c3c0a",
        },
        accent: {
          blue: "#3b82f6",
          purple: "#8b5cf6",
          green: "#10b981",
          red: "#ef4444",
        },
        text: {
          primary: "#e8edf8",
          secondary: "#8b9ab8",
          muted: "#4a5675",
          accent: "#f97316",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
        display: ["Outfit", "Inter", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 20px rgba(249,115,22,0.3)",
        "glow-sm": "0 0 10px rgba(249,115,22,0.2)",
        "glow-lg": "0 0 40px rgba(249,115,22,0.25)",
        card: "0 4px 24px rgba(0,0,0,0.4)",
        panel: "0 8px 40px rgba(0,0,0,0.6)",
      },
      backdropBlur: {
        xs: "2px",
      },
      animation: {
        "fade-in": "fadeIn 200ms ease",
        "slide-up": "slideUp 240ms ease",
        "slide-in-right": "slideInRight 240ms ease",
        "pulse-glow": "pulseGlow 2s ease-in-out infinite",
        "typing-dot": "typingDot 1.2s ease-in-out infinite",
        float: "float 3s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        slideUp: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        slideInRight: {
          from: { opacity: "0", transform: "translateX(12px)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
        pulseGlow: {
          "0%, 100%": { boxShadow: "0 0 10px rgba(249,115,22,0.2)" },
          "50%": { boxShadow: "0 0 24px rgba(249,115,22,0.5)" },
        },
        typingDot: {
          "0%, 80%, 100%": { opacity: "0.2", transform: "scale(0.8)" },
          "40%": { opacity: "1", transform: "scale(1)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-6px)" },
        },
      },
    },
  },
  plugins: [typography],
};

export default config;
