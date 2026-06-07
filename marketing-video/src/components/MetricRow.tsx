import React from "react";
import {COLORS, FONT_STACK, MetricTone} from "../timing";

interface MetricRowProps {
  label: string;
  value: string;
  tone: MetricTone;
  // 0 -> 1: fade + slideX
  appear: number;
}

const toneColor = (tone: MetricTone): string => {
  switch (tone) {
    case "warning":
      return COLORS.warning;
    case "danger":
      return COLORS.danger;
    case "success":
      return COLORS.success;
    default:
      return COLORS.textPrimary;
  }
};

export const MetricRow: React.FC<MetricRowProps> = ({
  label,
  value,
  tone,
  appear,
}) => {
  const translateX = (1 - appear) * 24;
  const opacity = appear;
  const color = toneColor(tone);

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "16px 0",
        borderBottom: `1px solid ${COLORS.cardBorder}`,
        transform: `translateX(${translateX}px)`,
        opacity,
        fontFamily: FONT_STACK,
      }}
    >
      <span
        style={{
          fontSize: 24,
          fontWeight: 500,
          color: COLORS.textSecondary,
        }}
      >
        {label}
      </span>
      <span
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          fontSize: 26,
          fontWeight: 700,
          color,
          letterSpacing: "-0.01em",
        }}
      >
        {tone !== "neutral" ? (
          <span
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              backgroundColor: color,
              boxShadow: `0 0 12px ${color}99`,
            }}
          />
        ) : null}
        {value}
      </span>
    </div>
  );
};
