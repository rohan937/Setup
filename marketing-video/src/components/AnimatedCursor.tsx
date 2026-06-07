import React from "react";
import {COLORS, FONT_STACK} from "../timing";
import {ClickRipple} from "./ClickRipple";

interface AnimatedCursorProps {
  // Current px position (scenes pass already-eased values).
  x: number;
  y: number;
  hovering?: boolean;
  clicking?: boolean;
  // 0 -> 1 lifecycle of the active click (drives the ripple). Optional.
  clickProgress?: number;
  label?: string;
  ringColor?: string;
}

// A macOS-style arrow cursor with soft shadow, hover ring, and click ripple.
export const AnimatedCursor: React.FC<AnimatedCursorProps> = ({
  x,
  y,
  hovering = false,
  clicking = false,
  clickProgress = 0,
  label,
  ringColor = COLORS.blue,
}) => {
  const scale = clicking ? 0.86 : 1;

  return (
    <>
      {/* Click ripple emitted at the cursor tip. */}
      {clickProgress > 0 && clickProgress < 1 ? (
        <ClickRipple x={x} y={y} progress={clickProgress} color={ringColor} />
      ) : null}

      <div
        style={{
          position: "absolute",
          left: x,
          top: y,
          transform: `scale(${scale})`,
          transformOrigin: "top left",
          pointerEvents: "none",
          zIndex: 50,
          transition: "transform 60ms ease-out",
        }}
      >
        {/* Hover ring sits behind the arrow, centered on the tip. */}
        {hovering ? (
          <div
            style={{
              position: "absolute",
              left: -16,
              top: -16,
              width: 44,
              height: 44,
              borderRadius: "50%",
              border: `2px solid ${ringColor}`,
              boxShadow: `0 0 18px ${ringColor}66`,
              opacity: 0.7,
            }}
          />
        ) : null}

        {/* macOS-style arrow cursor. */}
        <svg
          width="26"
          height="26"
          viewBox="0 0 24 24"
          fill="none"
          style={{
            display: "block",
            filter: "drop-shadow(0 4px 8px rgba(0,0,0,0.55))",
          }}
        >
          <path
            d="M5 3 L5 19 L9.2 15.2 L11.8 21 L14.4 19.8 L11.9 14.2 L17.5 14.2 Z"
            fill="#FFFFFF"
            stroke="#0B1020"
            strokeWidth="1.1"
            strokeLinejoin="round"
          />
        </svg>

        {/* Optional click/intent label pill. */}
        {label ? (
          <div
            style={{
              position: "absolute",
              left: 24,
              top: 18,
              padding: "5px 10px",
              borderRadius: 999,
              background: COLORS.elevated,
              border: `1px solid ${COLORS.border}`,
              color: COLORS.textPrimary,
              fontFamily: FONT_STACK,
              fontSize: 12,
              fontWeight: 600,
              whiteSpace: "nowrap",
              boxShadow: "0 8px 20px rgba(0,0,0,0.4)",
            }}
          >
            {label}
          </div>
        ) : null}
      </div>
    </>
  );
};
