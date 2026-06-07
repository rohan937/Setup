import React from "react";
import {useCurrentFrame} from "remotion";
import {COLORS, FONT_STACK} from "../timing";

interface AppHeaderMockProps {
  // Product-area label shown next to the wordmark, e.g. "Command Center".
  area?: string;
  user?: string;
}

// Slim app top bar: wordmark + area label, status dot, user pill.
export const AppHeaderMock: React.FC<AppHeaderMockProps> = ({
  area = "Command Center",
  user = "R. Shah",
}) => {
  const frame = useCurrentFrame();
  // Gentle pulse on the "API online" dot.
  const pulse = 0.6 + 0.4 * ((Math.sin(frame * 0.12) + 1) / 2);

  return (
    <div
      style={{
        height: 56,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 22px",
        borderBottom: `1px solid ${COLORS.border}`,
        background: "rgba(255,255,255,0.015)",
        fontFamily: FONT_STACK,
        flexShrink: 0,
      }}
    >
      <div style={{display: "flex", alignItems: "center", gap: 14}}>
        <div style={{display: "flex", alignItems: "center", gap: 9}}>
          <div
            style={{
              width: 22,
              height: 22,
              borderRadius: 7,
              background: `linear-gradient(135deg, ${COLORS.blue}, ${COLORS.purple})`,
              boxShadow: `0 4px 14px ${COLORS.blue}55`,
            }}
          />
          <span
            style={{
              fontSize: 16,
              fontWeight: 700,
              color: COLORS.textPrimary,
              letterSpacing: "-0.01em",
            }}
          >
            QuantFidelity
          </span>
        </div>
        <span style={{color: COLORS.textMuted, fontSize: 14}}>/</span>
        <span style={{color: COLORS.textSecondary, fontSize: 14, fontWeight: 500}}>
          {area}
        </span>
      </div>

      <div style={{display: "flex", alignItems: "center", gap: 16}}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 7,
            padding: "5px 11px",
            borderRadius: 999,
            background: "rgba(0,212,146,0.1)",
            border: `1px solid rgba(0,212,146,0.2)`,
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: COLORS.success,
              boxShadow: `0 0 ${6 + pulse * 6}px ${COLORS.success}`,
              opacity: pulse,
            }}
          />
          <span style={{color: COLORS.success, fontSize: 12, fontWeight: 600}}>
            API online
          </span>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "4px 10px 4px 4px",
            borderRadius: 999,
            background: COLORS.elevated,
            border: `1px solid ${COLORS.border}`,
          }}
        >
          <span
            style={{
              width: 24,
              height: 24,
              borderRadius: "50%",
              background: `linear-gradient(135deg, ${COLORS.purple}, ${COLORS.cyan})`,
              display: "inline-block",
            }}
          />
          <span style={{color: COLORS.textSecondary, fontSize: 13, fontWeight: 600}}>
            {user}
          </span>
        </div>
      </div>
    </div>
  );
};
