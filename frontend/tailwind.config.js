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
      // M108 controlled vibrancy — institutional gradients for high-impact demo surfaces.
      backgroundImage: {
        "grad-primary":  "linear-gradient(135deg, #4F8CFF, #8B5CF6)",   // blue→purple
        "grad-cyan":     "linear-gradient(135deg, #38BDF8, #4F8CFF)",   // cyan→blue
        "grad-success":  "linear-gradient(135deg, #00D492, #38BDF8)",   // green→cyan
        "grad-warning":  "linear-gradient(135deg, #FFB547, #FF8A5B)",   // amber→orange
        "grad-danger":   "linear-gradient(135deg, #FF6B6B, #F472B6)",   // red→pink (critical only)
        "grad-research": "linear-gradient(135deg, #8B5CF6, #4F8CFF)",   // purple→blue
        "grad-hero":     "linear-gradient(120deg, rgba(79,140,255,0.14), rgba(139,92,246,0.12) 45%, rgba(0,212,146,0.08))",
      },
      boxShadow: {
        // M101 subtle premium elevation + primary glow.
        panel:        "0 1px 2px rgba(0,0,0,0.3), 0 1px 3px rgba(0,0,0,0.2)",
        card:         "0 1px 3px rgba(0,0,0,0.3), 0 8px 24px -8px rgba(0,0,0,0.5)",
        "card-hover": "0 2px 4px rgba(0,0,0,0.35), 0 12px 32px -8px rgba(0,0,0,0.6)",
        glow:         "0 0 0 1px rgba(79,140,255,0.15), 0 0 24px rgba(79,140,255,0.12)",
        // M102 state-aware glows — subtle low-opacity rings, never neon.
        "glow-success":  "0 0 0 1px rgba(0,212,146,0.25), 0 0 20px -4px rgba(0,212,146,0.25)",
        "glow-warning":  "0 0 0 1px rgba(255,181,71,0.25), 0 0 20px -4px rgba(255,181,71,0.22)",
        "glow-danger":   "0 0 0 1px rgba(255,107,107,0.25), 0 0 20px -4px rgba(255,107,107,0.22)",
        "glow-primary":  "0 0 0 1px rgba(79,140,255,0.25), 0 0 20px -4px rgba(79,140,255,0.22)",
        "glow-research": "0 0 0 1px rgba(139,92,246,0.25), 0 0 20px -4px rgba(139,92,246,0.22)",
        "lift":          "0 4px 16px -4px rgba(0,0,0,0.55)",
        // M108 stronger glows — higher opacity + spread for demo / score / hero cards.
        "glow-success-lg":  "0 0 0 1px rgba(0,212,146,0.45), 0 0 28px -2px rgba(0,212,146,0.40)",
        "glow-warning-lg":  "0 0 0 1px rgba(255,181,71,0.45), 0 0 28px -2px rgba(255,181,71,0.38)",
        "glow-danger-lg":   "0 0 0 1px rgba(255,107,107,0.45), 0 0 28px -2px rgba(255,107,107,0.38)",
        "glow-primary-lg":  "0 0 0 1px rgba(79,140,255,0.45), 0 0 28px -2px rgba(79,140,255,0.40)",
        "glow-research-lg": "0 0 0 1px rgba(139,92,246,0.45), 0 0 28px -2px rgba(139,92,246,0.40)",
      },
      // M102 motion tokens — calm, institutional. Static by default.
      keyframes: {
        "fade-in": { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        "slide-up": { "0%": { opacity: "0", transform: "translateY(8px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        "soft-pulse": { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.55" } },
        "gradient-drift": { "0%": { transform: "translate3d(0,0,0) scale(1)" }, "50%": { transform: "translate3d(3%,-3%,0) scale(1.08)" }, "100%": { transform: "translate3d(0,0,0) scale(1)" } },
        "shimmer": { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
        // M108 vibrancy keyframes.
        "connector-flow": { "0%": { backgroundPosition: "0% 0" }, "100%": { backgroundPosition: "200% 0" } },
        "shimmer-tinted": { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
      },
      animation: {
        "fade-in": "fade-in 0.3s ease-out both",
        "slide-up": "slide-up 0.35s ease-out both",
        "soft-pulse": "soft-pulse 2.4s ease-in-out infinite",
        "gradient-drift": "gradient-drift 16s ease-in-out infinite",
        "shimmer": "shimmer 1.6s ease-in-out infinite",
        // M108 vibrancy animations.
        "connector-flow": "connector-flow 3s linear infinite",
        "hero-drift": "gradient-drift 22s ease-in-out infinite",  // slower, calmer hero variant
      },
    },
  },
  plugins: [],
};
