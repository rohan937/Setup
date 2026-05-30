/** @type {import('tailwindcss').Config} */
// Tokens: deep-navy research terminal. Quant cockpit, not security SaaS.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Background layers: deepest → elevated
        bg: {
          950: "#04070D",  // absolute floor
          900: "#070B12",  // body / app bg
          800: "#0A0F1A",  // sidebar, topbar
          700: "#0E1520",  // cards, panels
          600: "#131E2F",  // hover, elevated, input bg
        },
        // Borders: subtle cool-toned strokes
        border: {
          DEFAULT: "#1C2B3D",
          strong: "#263A52",
          accent: "#1A3A52",
        },
        // Text scale
        text: {
          primary: "#E5EDF7",
          secondary: "#8BA3BE",
          muted: "#4B6282",
          inverse: "#070B12",
        },
        // Primary accent: cyan / sky
        accent: {
          200: "#BAE6FD",
          300: "#7DD3FC",
          500: "#38BDF8",
          600: "#0EA5E9",
        },
        // Secondary accent: teal
        teal: {
          300: "#5EEAD4",
          500: "#14B8A6",
        },
        // Semantic reliability states
        fidelity: {
          high:    "#34D399",  // good / passes
          medium:  "#FBBF24",  // warning / assumption drift
          low:     "#F87171",  // bad / broken
          info:    "#64748B",  // neutral / not measured
        },
        // Severity kept for backward compat; remapped to terminal palette
        severity: {
          critical: "#F87171",
          high:     "#FB923C",
          medium:   "#FBBF24",
          low:      "#67E8F9",
          info:     "#64748B",
          success:  "#34D399",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "1rem" }],
      },
      borderRadius: {
        card:    "6px",   // panels — sharper than generic SaaS
        control: "4px",   // inputs, buttons
        chip:    "2px",   // badges — near-square, finance terminal
      },
      maxWidth: {
        content: "1440px",
      },
      boxShadow: {
        panel: "0 1px 3px rgba(0,0,0,0.5), 0 0 0 1px rgba(28,43,61,0.8)",
        glow:  "0 0 16px rgba(56,189,248,0.12)",
      },
    },
  },
  plugins: [],
};
