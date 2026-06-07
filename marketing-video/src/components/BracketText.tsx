import React from "react";
import {AbsoluteFill} from "remotion";
import {COLORS, FONT_STACK} from "../timing";

interface BracketTextProps {
  text: string;
  // 0 -> 1 fade/scale in
  enter: number;
  // 0 -> 1 fade out (1 = fully gone)
  exit?: number;
}

// Splits "[ backtests look clean ]" into bracket + inner so the
// brackets can take an accent color.
const splitBrackets = (text: string) => {
  const trimmed = text.trim();
  if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
    return {
      open: "[",
      inner: trimmed.slice(1, -1),
      close: "]",
    };
  }
  return {open: "", inner: trimmed, close: ""};
};

export const BracketText: React.FC<BracketTextProps> = ({
  text,
  enter,
  exit = 0,
}) => {
  const {open, inner, close} = splitBrackets(text);
  const opacity = enter * (1 - exit);
  const scale = 0.98 + 0.02 * enter;
  const translateY = (1 - enter) * 12;

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <div
        style={{
          opacity,
          transform: `translateY(${translateY}px) scale(${scale})`,
          fontFamily: FONT_STACK,
          fontSize: 92,
          fontWeight: 600,
          letterSpacing: "-0.02em",
          color: COLORS.textPrimary,
          textAlign: "center",
          maxWidth: 1400,
          lineHeight: 1.1,
        }}
      >
        <span style={{color: COLORS.blue, fontWeight: 400, marginRight: 16}}>
          {open}
        </span>
        {inner}
        <span style={{color: COLORS.blue, fontWeight: 400, marginLeft: 16}}>
          {close}
        </span>
      </div>
    </AbsoluteFill>
  );
};
