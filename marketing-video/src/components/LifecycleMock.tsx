import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import {COLORS, FONT_STACK, STAGES} from "../timing";

interface LifecycleMockProps {
  // Key of the current stage (from STAGES).
  currentKey: string;
  // Optional key of a blocked stage (shows warning state).
  blockedKey?: string;
  // 0 -> 1 connector reveal / flow.
  progress: number;
}

type StageState = "completed" | "current" | "blocked" | "locked";

// 5-stage horizontal pipeline with animated connector flow.
export const LifecycleMock: React.FC<LifecycleMockProps> = ({
  currentKey,
  blockedKey,
  progress,
}) => {
  const frame = useCurrentFrame();
  const currentIndex = STAGES.findIndex((s) => s.key === currentKey);
  const pulse = 0.6 + 0.4 * ((Math.sin(frame * 0.14) + 1) / 2);

  const stateFor = (index: number, key: string): StageState => {
    if (key === blockedKey) return "blocked";
    if (index < currentIndex) return "completed";
    if (index === currentIndex) return "current";
    return "locked";
  };

  const colorFor = (st: StageState) => {
    switch (st) {
      case "completed":
        return COLORS.success;
      case "current":
        return COLORS.blue;
      case "blocked":
        return COLORS.warning;
      case "locked":
      default:
        return COLORS.textMuted;
    }
  };

  const glyphFor = (st: StageState) => {
    switch (st) {
      case "completed":
        return "✓";
      case "blocked":
        return "⚠";
      case "locked":
        return "🔒";
      case "current":
      default:
        return "●";
    }
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        width: "100%",
        fontFamily: FONT_STACK,
      }}
    >
      {STAGES.map((stage, i) => {
        const st = stateFor(i, stage.key);
        const color = colorFor(st);
        const isCurrent = st === "current";

        // Connector reveal: each segment fills as global progress crosses it.
        const segCount = STAGES.length - 1;
        const segStart = i / segCount;
        const segEnd = (i + 1) / segCount;
        const fill =
          i < STAGES.length - 1
            ? interpolate(progress, [segStart, segEnd], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              })
            : 0;
        const connectorActive = i < currentIndex;

        return (
          <React.Fragment key={stage.key}>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 10,
                width: 96,
                flexShrink: 0,
              }}
            >
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: "50%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 16,
                  fontWeight: 700,
                  color: st === "locked" ? COLORS.textMuted : "#0B1020",
                  background:
                    st === "locked"
                      ? "rgba(255,255,255,0.05)"
                      : st === "current"
                        ? color
                        : color,
                  border: `2px solid ${color}`,
                  boxShadow: isCurrent
                    ? `0 0 ${10 + pulse * 14}px ${color}, 0 0 0 4px ${color}22`
                    : st === "completed"
                      ? `0 0 12px ${color}55`
                      : "none",
                  opacity: isCurrent ? 0.9 + pulse * 0.1 : 1,
                }}
              >
                {glyphFor(st)}
              </div>
              <span
                style={{
                  fontSize: 11.5,
                  fontWeight: isCurrent ? 700 : 500,
                  color: st === "locked" ? COLORS.textMuted : COLORS.textPrimary,
                  textAlign: "center",
                  lineHeight: 1.25,
                }}
              >
                {stage.label}
              </span>
            </div>

            {/* Connector between stages. */}
            {i < STAGES.length - 1 ? (
              <div
                style={{
                  flex: 1,
                  height: 3,
                  marginTop: 18,
                  borderRadius: 3,
                  background: "rgba(255,255,255,0.08)",
                  position: "relative",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    width: `${fill * 100}%`,
                    background: connectorActive
                      ? COLORS.success
                      : `linear-gradient(90deg, ${COLORS.success}, ${COLORS.blue})`,
                    boxShadow: `0 0 10px ${connectorActive ? COLORS.success : COLORS.blue}88`,
                    borderRadius: 3,
                  }}
                />
              </div>
            ) : null}
          </React.Fragment>
        );
      })}
    </div>
  );
};
