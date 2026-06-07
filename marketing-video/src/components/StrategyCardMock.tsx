import React from "react";
import {COLORS, FONT_STACK} from "../timing";
import {scoreTone, toneColor} from "./tone";

interface StrategyCardMockProps {
  name: string;
  stage: string;
  score: number;
  assetClass?: string;
  // Lifts + glows when the cursor hovers this row.
  highlighted?: boolean;
}

// A strategy row/card with name, asset badge, reliability number, stage badge.
export const StrategyCardMock: React.FC<StrategyCardMockProps> = ({
  name,
  stage,
  score,
  assetClass = "US Equities",
  highlighted = false,
}) => {
  const accent = toneColor(scoreTone(score));

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "14px 18px",
        borderRadius: 12,
        background: highlighted ? COLORS.elevated : COLORS.surface,
        border: `1px solid ${highlighted ? "rgba(79,140,255,0.45)" : COLORS.border}`,
        boxShadow: highlighted
          ? `0 12px 32px rgba(0,0,0,0.45), 0 0 0 1px ${COLORS.blue}33, 0 0 28px ${COLORS.blue}33`
          : "0 2px 8px rgba(0,0,0,0.25)",
        transform: highlighted ? "translateY(-2px)" : "none",
        fontFamily: FONT_STACK,
      }}
    >
      <div style={{display: "flex", flexDirection: "column", gap: 7}}>
        <span style={{fontSize: 15, fontWeight: 600, color: COLORS.textPrimary}}>
          {name}
        </span>
        <span
          style={{
            alignSelf: "flex-start",
            fontSize: 11,
            fontWeight: 600,
            color: COLORS.textSecondary,
            background: "rgba(255,255,255,0.05)",
            border: `1px solid ${COLORS.border}`,
            borderRadius: 999,
            padding: "2px 9px",
          }}
        >
          {assetClass}
        </span>
      </div>

      <div style={{display: "flex", alignItems: "center", gap: 16}}>
        <div style={{display: "flex", flexDirection: "column", alignItems: "flex-end"}}>
          <span style={{fontSize: 20, fontWeight: 700, color: accent}}>{score}</span>
          <span style={{fontSize: 10.5, color: COLORS.textMuted, fontWeight: 600}}>
            reliability
          </span>
        </div>
        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: COLORS.textPrimary,
            background: "rgba(255,255,255,0.05)",
            border: `1px solid ${COLORS.border}`,
            borderRadius: 8,
            padding: "6px 11px",
          }}
        >
          {stage}
        </span>
      </div>
    </div>
  );
};
