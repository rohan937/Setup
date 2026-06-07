import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import {COLORS, FONT_STACK} from "../timing";

interface CaptionProps {
  text: string;
  sub?: string;
  // "bottom" (default) or "top".
  position?: "bottom" | "top";
  // Frame the caption fades in.
  inAt?: number;
  // Frame the caption fades out (omit to stay).
  outAt?: number;
  // Eyebrow / kicker label above the caption (small, brand color).
  kicker?: string;
}

// Clean, concise scene caption. Secondary-toned, pinned top or bottom.
export const Caption: React.FC<CaptionProps> = ({
  text,
  sub,
  position = "bottom",
  inAt = 8,
  outAt,
  kicker,
}) => {
  const frame = useCurrentFrame();

  const fadeIn = interpolate(frame, [inAt, inAt + 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut =
    outAt !== undefined
      ? interpolate(frame, [outAt, outAt + 12], [1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : 1;
  const opacity = Math.min(fadeIn, fadeOut);
  const rise = (1 - fadeIn) * 14 * (position === "bottom" ? 1 : -1);

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        [position]: 64,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 8,
        padding: "0 80px",
        fontFamily: FONT_STACK,
        opacity,
        transform: `translateY(${rise}px)`,
        zIndex: 30,
        pointerEvents: "none",
      }}
    >
      {kicker ? (
        <div
          style={{
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: "0.2em",
            textTransform: "uppercase",
            color: COLORS.blue,
          }}
        >
          {kicker}
        </div>
      ) : null}
      <div
        style={{
          fontSize: 30,
          fontWeight: 700,
          color: COLORS.textPrimary,
          textAlign: "center",
          letterSpacing: "-0.02em",
          lineHeight: 1.2,
          maxWidth: 1200,
          textShadow: "0 2px 24px rgba(0,0,0,0.6)",
        }}
      >
        {text}
      </div>
      {sub ? (
        <div
          style={{
            fontSize: 17,
            fontWeight: 500,
            color: COLORS.textSecondary,
            textAlign: "center",
            lineHeight: 1.35,
            maxWidth: 1000,
          }}
        >
          {sub}
        </div>
      ) : null}
    </div>
  );
};
