/** @type {import('tailwindcss').Config} */
// Tokens mirror UIDesignSystem.txt: institutional, dark, calm, technical.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          900: "#0B0E14",
          800: "#11161F",
          700: "#161C27",
          600: "#1E2633",
        },
        border: {
          DEFAULT: "#28303D",
          strong: "#36404F",
        },
        text: {
          primary: "#E6EAF0",
          secondary: "#A4AEBE",
          muted: "#6B7686",
          inverse: "#0B0E14",
        },
        accent: {
          300: "#6FC2EE",
          500: "#2D9CDB",
          600: "#2280BA",
        },
        severity: {
          critical: "#E5484D",
          high: "#F2994A",
          medium: "#F2C94C",
          low: "#56CCF2",
          info: "#7E8AA0",
          success: "#27AE60",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      borderRadius: {
        card: "8px",
        control: "6px",
        chip: "4px",
      },
      maxWidth: {
        content: "1440px",
      },
    },
  },
  plugins: [],
};
