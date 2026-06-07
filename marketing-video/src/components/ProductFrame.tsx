import React from "react";
import {COLORS, FONT_STACK} from "../timing";

interface ProductFrameProps {
  children: React.ReactNode;
  width: number;
  height: number;
  // 0 -> 1: fade + slight translateY/scale-in.
  appear: number;
  // Optional colored glow behind the window.
  glow?: string;
  // Show faux macOS traffic-light dots.
  titlebarDots?: boolean;
  style?: React.CSSProperties;
}

// A floating dark app window — the canvas for product mocks.
export const ProductFrame: React.FC<ProductFrameProps> = ({
  children,
  width,
  height,
  appear,
  glow,
  titlebarDots = false,
  style,
}) => {
  const a = Math.max(0, Math.min(1, appear));
  const translateY = (1 - a) * 28;
  const scale = 0.97 + a * 0.03;

  return (
    <div
      style={{
        position: "relative",
        width,
        height,
        transform: `translateY(${translateY}px) scale(${scale})`,
        opacity: a,
        fontFamily: FONT_STACK,
        ...style,
      }}
    >
      {/* Soft colored glow behind the window. */}
      {glow ? (
        <div
          style={{
            position: "absolute",
            inset: -50,
            borderRadius: 40,
            background: `radial-gradient(circle at 30% 0%, ${glow}38, transparent 60%), radial-gradient(circle at 80% 100%, ${glow}26, transparent 60%)`,
            filter: "blur(48px)",
            opacity: 0.9,
            zIndex: 0,
          }}
        />
      ) : null}

      <div
        style={{
          position: "relative",
          zIndex: 1,
          width,
          height,
          borderRadius: 16,
          overflow: "hidden",
          background: COLORS.surface,
          border: `1px solid ${COLORS.border}`,
          boxShadow:
            "0 40px 100px rgba(0,0,0,0.55), 0 12px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {titlebarDots ? (
          <div
            style={{
              height: 36,
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "0 16px",
              borderBottom: `1px solid ${COLORS.border}`,
              background: "rgba(255,255,255,0.02)",
            }}
          >
            {["#FF6B6B", "#FFB547", "#00D492"].map((c) => (
              <span
                key={c}
                style={{
                  width: 11,
                  height: 11,
                  borderRadius: "50%",
                  background: c,
                  opacity: 0.85,
                }}
              />
            ))}
          </div>
        ) : null}
        <div style={{flex: 1, minHeight: 0, position: "relative"}}>{children}</div>
      </div>
    </div>
  );
};
