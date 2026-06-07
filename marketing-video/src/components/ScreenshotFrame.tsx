import React, {useState} from "react";
import {Img, staticFile} from "remotion";
import {COLORS, FONT_STACK} from "../timing";

interface ScreenshotFrameProps {
  // Path relative to assets/ (public) dir, e.g. "screenshots/home.png"
  src: string;
  label: string;
  width?: number;
  // 0 -> 1: fade + slide up
  appear: number;
  // extra horizontal offset / rotation for staggered fan look
  offsetX?: number;
  rotate?: number;
}

// Renders a browser-ish frame. Attempts to load the image via <Img>;
// if it is missing/errors, gracefully falls back to a polished gradient
// placeholder so rendering never crashes.
export const ScreenshotFrame: React.FC<ScreenshotFrameProps> = ({
  src,
  label,
  width = 520,
  appear,
  offsetX = 0,
  rotate = 0,
}) => {
  const [failed, setFailed] = useState(false);
  const height = Math.round((width * 9) / 16) + 44;
  const translateY = (1 - appear) * 40;
  const opacity = appear;

  return (
    <div
      style={{
        position: "relative",
        width,
        transform: `translate(${offsetX}px, ${translateY}px) rotate(${rotate}deg)`,
        opacity,
        fontFamily: FONT_STACK,
      }}
    >
      <div
        style={{
          width,
          height,
          borderRadius: 18,
          overflow: "hidden",
          background: "#FFFFFF",
          border: `1px solid ${COLORS.cardBorder}`,
          boxShadow:
            "0 36px 80px rgba(15, 23, 42, 0.18), 0 8px 20px rgba(15, 23, 42, 0.08)",
        }}
      >
        {/* Browser chrome bar. */}
        <div
          style={{
            height: 44,
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "0 16px",
            background: "rgba(248, 250, 252, 0.9)",
            borderBottom: `1px solid ${COLORS.cardBorder}`,
          }}
        >
          {["#EF4444", "#F59E0B", "#00B894"].map((c) => (
            <span
              key={c}
              style={{
                width: 12,
                height: 12,
                borderRadius: "50%",
                background: c,
                opacity: 0.7,
              }}
            />
          ))}
          <span
            style={{
              marginLeft: 12,
              fontSize: 13,
              color: COLORS.textSecondary,
              fontWeight: 500,
            }}
          >
            {label}
          </span>
        </div>

        {/* Content area: image or placeholder. */}
        <div style={{position: "relative", width, height: height - 44}}>
          {failed ? null : (
            <Img
              src={staticFile(src)}
              onError={() => setFailed(true)}
              style={{
                position: "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
                objectFit: "cover",
                display: "block",
              }}
            />
          )}
          {failed ? (
            <div
              style={{
                position: "absolute",
                inset: 0,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 12,
                background: `linear-gradient(135deg, ${COLORS.blue}1f, ${COLORS.purple}1f 50%, ${COLORS.cyan}1f)`,
              }}
            >
              <div
                style={{
                  width: 56,
                  height: 56,
                  borderRadius: 14,
                  background: `linear-gradient(135deg, ${COLORS.blue}, ${COLORS.purple})`,
                  opacity: 0.9,
                  boxShadow: `0 8px 24px ${COLORS.blue}55`,
                }}
              />
              <div
                style={{
                  fontSize: 20,
                  fontWeight: 600,
                  color: COLORS.textPrimary,
                }}
              >
                {label}
              </div>
              <div
                style={{
                  fontSize: 13,
                  color: COLORS.textSecondary,
                }}
              >
                Preview
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};
