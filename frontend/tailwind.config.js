/** @type {import('tailwindcss').Config} */
// Tokens: institutional deep-navy research terminal.
// Linear + Datadog + Vercel + Bloomberg — dark, restrained, premium.
// Accents are DESATURATED on purpose: muted, not neon.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Background layers: deepest → elevated. Softer, less black,
        // gentle separation between layers (no harsh jumps).
        bg: {
          950: "#070A10",  // absolute floor
          900: "#0B0F16",  // body / app bg
          800: "#0F141C",  // sidebar, topbar
          700: "#141A24",  // cards, panels
          600: "#1B2330",  // hover, elevated, input bg
        },
        // Borders: calm, low-contrast cool strokes — quieter than before.
        border: {
          DEFAULT: "#212A38",
          strong: "#2C3848",
          accent: "#2A4256",
        },
        // Text scale: clear hierarchy, softened primary (no pure white).
        text: {
          primary: "#DDE5F0",
          secondary: "#94A4BC",
          muted: "#5E708A",
          inverse: "#0B0F16",
        },
        // Brand / primary accent: muted institutional sky-blue (desaturated).
        brand: {
          DEFAULT: "#4C9BD4",
          500: "#4C9BD4",
          600: "#3D80B5",
        },
        accent: {
          200: "#A9CFE8",
          300: "#86B8DC",
          500: "#4C9BD4",  // muted sky — not neon cyan
          600: "#3D80B5",
        },
        // Secondary accent: muted teal.
        teal: {
          300: "#74C4B8",
          500: "#3FA092",
        },
        // Semantic reliability states — desaturated, premium tones.
        fidelity: {
          high:    "#5BB98C",  // good / passes — muted green
          medium:  "#D9A93E",  // warning / assumption drift — muted amber
          low:     "#D97A72",  // bad / broken — muted red
          info:    "#6B7B92",  // neutral / not measured
        },
        // Severity kept for backward compat; remapped to muted palette.
        severity: {
          critical: "#D97A72",
          high:     "#D08A55",
          medium:   "#D9A93E",
          low:      "#5FA6C4",
          info:     "#6B7B92",
          success:  "#5BB98C",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      letterSpacing: {
        // Calmer eyebrow tracking — institutional, not spaced-out terminal.
        eyebrow: "0.08em",
      },
      borderRadius: {
        card:    "8px",   // panels — softer, premium
        control: "6px",   // inputs, buttons
        chip:    "4px",   // badges — slightly rounded
      },
      maxWidth: {
        content: "1440px",
      },
      boxShadow: {
        // Subtle elevation for cards — soft, layered, no glow.
        panel: "0 1px 2px rgba(0,0,0,0.4), 0 1px 3px rgba(0,0,0,0.25)",
        card:  "0 1px 2px rgba(0,0,0,0.35), 0 4px 12px -4px rgba(0,0,0,0.45)",
        glow:  "0 0 16px rgba(76,155,212,0.10)",
      },
    },
  },
  plugins: [],
};
