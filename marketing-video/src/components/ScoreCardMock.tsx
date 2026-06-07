import React from "react";
import {COLORS, FONT_STACK, MetricTone} from "../timing";
import {toneColor} from "./tone";

interface ScoreCardMockProps {
  label: string;
  // Big numeric value (e.g. "88.8") — omit if using a verdict word.
  value?: string;
  // Word verdict (e.g. "Verified", "Review") — used when value is absent.
  verdict?: string;
  tone: MetricTone;
  // Glow intensifies when the cursor passes / focuses this card.
  focused?: boolean;
  // 0 -> 1 fade + rise.
  appear?: number;
}

// A metric/score card: label + big number or verdict word + tone color.
export const ScoreCardMock: React.FC<ScoreCardMockProps> = ({
  label,
  value,
  verdict,
  tone,
  focused = false,
  appear = 1,
}) => {
  const a = Math.max(0, Math.min(1, appear));
  const accent = toneColor(tone);
  const big = value ?? verdict ?? "—";
  const isWord = value === undefined && verdict !== undefined;

  return (
    <div
      style={{
        position: "relative",
        flex: 1,
        minWidth: 0,
        padding: "18px 20px",
        borderRadius: 14,
        background: focused ? COLORS.elevated : COLORS.surface,
        border: `1px solid ${focused ? accent + "66" : COLORS.border}`,
        boxShadow: focused
          ? `0 14px 36px rgba(0,0,0,0.5), 0 0 30px ${accent}3a`
          : "0 2px 10px rgba(0,0,0,0.3)",
        transform: `translateY(${(1 - a) * 18}px) scale(${focused ? 1.02 : 1})`,
        opacity: a,
        fontFamily: FONT_STACK,
        overflow: "hidden",
      }}
    >
      {/* Top accent bar. */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 3,
          background: accent,
          opacity: focused ? 1 : 0.6,
          boxShadow: focused ? `0 0 14px ${accent}` : "none",
        }}
      />
      <div
        style={{
          fontSize: 12,
          fontWeight: 600,
          color: COLORS.textSecondary,
          letterSpacing: "0.02em",
          marginBottom: 10,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: isWord ? 26 : 34,
          fontWeight: 800,
          lineHeight: 1,
          color: accent,
          letterSpacing: "-0.02em",
        }}
      >
        {big}
        {!isWord && value ? (
          <span style={{fontSize: 14, fontWeight: 600, color: COLORS.textMuted}}>
            {" "}
            /100
          </span>
        ) : null}
      </div>
    </div>
  );
};
