/** @type {import('tailwindcss').Config} */
// Tokens: M101 institutional research platform.
// Deeper navy with blue cast, brighter institutional blue + purple research accent.
// Premium, restrained, high-contrast hierarchy.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Background layers: deeper navy with blue cast (M101).
        bg: {
          950: "#070B14",  // absolute floor
          900: "#0B1020",  // body / app bg — M101 Background
          800: "#0E1526",  // sidebar, topbar
          700: "#111827",  // cards, panels — M101 Surface
          600: "#162033",  // hover, elevated, input bg — M101 Elevated Surface
        },
        // Borders: translucent white strokes per M101 spec.
        border: {
          DEFAULT: "rgba(255,255,255,0.08)",
          strong: "rgba(255,255,255,0.14)",
          accent: "rgba(79,140,255,0.32)",
        },
        // Text scale: bright, clear M101 hierarchy.
        text: {
          primary: "#F8FAFC",
          secondary: "#94A3B8",
          muted: "#64748B",
          inverse: "#0B1020",
        },
        // Brand / primary accent: brighter institutional blue (M101).
        brand: {
          DEFAULT: "#4F8CFF",
          500: "#4F8CFF",
          600: "#6AA0FF",  // HOVER — lighter per M101
        },
        accent: {
          200: "#BBD2FF",
          300: "#9BBEFF",
          500: "#4F8CFF",
          600: "#6AA0FF",
        },
        // Secondary accent: aligned to M101 success green family.
        teal: {
          300: "#5EEAD0",
          500: "#00D492",
        },
        // Semantic reliability states — M101 brighter tones.
        fidelity: {
          high:    "#00D492",  // success
          medium:  "#FFB547",  // warning
          low:     "#FF6B6B",  // danger
          info:    "#64748B",  // neutral
        },
        // Severity kept for backward compat; remapped to M101.
        severity: {
          critical: "#FF6B6B",
          high:     "#FF8A5B",
          medium:   "#FFB547",
          low:      "#4F8CFF",
          info:     "#64748B",
          success:  "#00D492",
        },
        // M101 Research Accent (purple) — newly introduced.
        research: {
          DEFAULT: "#8B5CF6",
          300: "#A78BFA",
          500: "#8B5CF6",
          600: "#7C4DEF",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
        // M101 typography hierarchy.
        "display": ["2.25rem", { lineHeight: "2.5rem", letterSpacing: "-0.02em" }],   // 36px page titles
        "metric": ["3rem", { lineHeight: "1", letterSpacing: "-0.02em" }],            // 48px hero metric values
        "metric-sm": ["2.25rem", { lineHeight: "1", letterSpacing: "-0.02em" }],      // 36px metric
      },
      letterSpacing: {
        // Softer eyebrow tracking per M101.
        eyebrow: "0.06em",
      },
      borderRadius: {
        card:    "12px",  // panels — softer, premium (M101)
        control: "8px",   // inputs, buttons
        chip:    "5px",   // badges — slightly rounded
      },
      maxWidth: {
        content: "1440px",
      },
      boxShadow: {
        // M101 subtle premium elevation + primary glow.
        panel:        "0 1px 2px rgba(0,0,0,0.3), 0 1px 3px rgba(0,0,0,0.2)",
        card:         "0 1px 3px rgba(0,0,0,0.3), 0 8px 24px -8px rgba(0,0,0,0.5)",
        "card-hover": "0 2px 4px rgba(0,0,0,0.35), 0 12px 32px -8px rgba(0,0,0,0.6)",
        glow:         "0 0 0 1px rgba(79,140,255,0.15), 0 0 24px rgba(79,140,255,0.12)",
      },
    },
  },
  plugins: [],
};
