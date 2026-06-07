import {COLORS, MetricTone} from "../timing";

// Maps a semantic tone to its accent color.
export const toneColor = (tone: MetricTone): string => {
  switch (tone) {
    case "success":
      return COLORS.success;
    case "warning":
      return COLORS.warning;
    case "danger":
      return COLORS.danger;
    case "primary":
      return COLORS.blue;
    case "neutral":
    default:
      return COLORS.textSecondary;
  }
};

// Tone glyph used in check / gate rows.
export const toneGlyph = (tone: MetricTone): string => {
  switch (tone) {
    case "success":
      return "✓";
    case "warning":
      return "⚠";
    case "danger":
      return "✕";
    default:
      return "•";
  }
};

// Derives a tone from a 0-100 score band.
export const scoreTone = (score: number): MetricTone => {
  if (score >= 85) return "success";
  if (score >= 70) return "warning";
  return "danger";
};
