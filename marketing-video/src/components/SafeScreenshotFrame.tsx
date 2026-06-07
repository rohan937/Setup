import React from "react";
import {Img, staticFile} from "remotion";
import {AVAILABLE_SCREENSHOTS, COLORS, FONT_STACK} from "../timing";

interface SafeScreenshotFrameProps {
  // Filename only, e.g. "home.png" (resolved under public/screenshots/).
  name: string;
  label: string;
  // 0 -> 1 fade + slide up.
  appear: number;
  width?: number;
  offsetX?: number;
  rotate?: number;
}

// THE 404 FIX.
// If `name` is listed in AVAILABLE_SCREENSHOTS, render the real <Img>.
// Otherwise render a polished dark MOCK frame — and NEVER call
// staticFile/Img for a missing file, so there are zero 404 logs / decode
// attempts / crashes.
export const SafeScreenshotFrame: React.FC<SafeScreenshotFrameProps> = ({
  name,
  label,
  appear,
  width = 520,
  offsetX = 0,
  rotate = 0,
}) => {
  const a = Math.max(0, Math.min(1, appear));
  const height = Math.round((width * 9) / 16) + 36;
  const translateY = (1 - a) * 40;

  const exists = AVAILABLE_SCREENSHOTS.includes(name);

  return (
    <div
      style={{
        position: "relative",
        width,
        transform: `translate(${offsetX}px, ${translateY}px) rotate(${rotate}deg)`,
        opacity: a,
        fontFamily: FONT_STACK,
      }}
    >
      <div
        style={{
          width,
          height,
          borderRadius: 14,
          overflow: "hidden",
          background: COLORS.surface,
          border: `1px solid ${COLORS.border}`,
          boxShadow:
            "0 36px 80px rgba(0,0,0,0.55), 0 8px 22px rgba(0,0,0,0.4)",
        }}
      >
        {/* Dark browser chrome bar. */}
        <div
          style={{
            height: 36,
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "0 14px",
            background: "rgba(255,255,255,0.02)",
            borderBottom: `1px solid ${COLORS.border}`,
          }}
        >
          {["#FF6B6B", "#FFB547", "#00D492"].map((c) => (
            <span
              key={c}
              style={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                background: c,
                opacity: 0.85,
              }}
            />
          ))}
          <span
            style={{
              marginLeft: 10,
              fontSize: 12,
              color: COLORS.textSecondary,
              fontWeight: 600,
            }}
          >
            {label}
          </span>
        </div>

        {/* Content: real image only when it exists; otherwise a mock. */}
        <div style={{position: "relative", width, height: height - 36}}>
          {exists ? (
            <Img
              src={staticFile("screenshots/" + name)}
              style={{
                position: "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
                objectFit: "cover",
                display: "block",
              }}
            />
          ) : (
            <div
              style={{
                position: "absolute",
                inset: 0,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 14,
                background: `radial-gradient(120% 120% at 30% 0%, ${COLORS.blue}1f, transparent 55%), radial-gradient(120% 120% at 80% 100%, ${COLORS.purple}1f, transparent 55%), ${COLORS.bg}`,
              }}
            >
              <div
                style={{
                  width: 54,
                  height: 54,
                  borderRadius: 14,
                  background: `linear-gradient(135deg, ${COLORS.blue}, ${COLORS.purple})`,
                  boxShadow: `0 10px 30px ${COLORS.blue}55`,
                }}
              />
              <div style={{fontSize: 18, fontWeight: 700, color: COLORS.textPrimary}}>
                {label}
              </div>
              <div style={{fontSize: 12, color: COLORS.textMuted, fontWeight: 500}}>
                Preview
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
