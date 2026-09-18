module.exports = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: { DEFAULT: "#17181b", secondary: "#1d1f23", tertiary: "#24262b", card: "#282a30", elevated: "#32353c" },
        border: { DEFAULT: "rgba(222,223,230,0.13)", subtle: "rgba(255,255,255,0.05)", accent: "rgba(216,177,66,0.45)" },
        nova: { orange: "#d8b142", amber: "#e8c976", glow: "#edce70", dim: "#554722" },
        accent: { blue: "#83b4e8", purple: "#c0acd9", green: "#88b6a1", red: "#e89582" },
        text: { primary: "#f1f0ec", secondary: "#b9bbc5", muted: "#8d909f", accent: "#d8b142" },
      },
      fontFamily: { sans: ["Outfit", "sans-serif"], mono: ["JetBrains Mono", "Fira Code", "monospace"], display: ["Outfit", "sans-serif"] },
      boxShadow: {
        glow: "0 0 24px rgba(216,177,66,0.12)", "glow-sm": "0 0 12px rgba(216,177,66,0.08)", "glow-lg": "0 0 48px rgba(216,177,66,0.12)",
        card: "0 4px 24px rgba(0,0,0,0.4)", panel: "0 8px 40px rgba(0,0,0,0.6)",
      },
      backdropBlur: { xs: "2px" },
      animation: { "fade-in": "fadeIn 200ms ease", "slide-up": "slideUp 240ms ease", "slide-in-right": "slideInRight 240ms ease", "pulse-glow": "pulseGlow 2s ease-in-out infinite", "typing-dot": "typingDot 1.2s ease-in-out infinite", float: "float 3s ease-in-out infinite" },
      keyframes: {
        fadeIn: { from: { opacity: "0" }, to: { opacity: "1" } },
        slideUp: { from: { opacity: "0", transform: "translateY(8px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        slideInRight: { from: { opacity: "0", transform: "translateX(12px)" }, to: { opacity: "1", transform: "translateX(0)" } },
        pulseGlow: { "0%, 100%": { boxShadow: "0 0 8px rgba(216,177,66,0.12)" }, "50%": { boxShadow: "0 0 18px rgba(216,177,66,0.24)" } },
        typingDot: { "0%, 80%, 100%": { opacity: "0.2", transform: "scale(0.8)" }, "40%": { opacity: "1", transform: "scale(1)" } },
        float: { "0%, 100%": { transform: "translateY(0px)" }, "50%": { transform: "translateY(-6px)" } },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};