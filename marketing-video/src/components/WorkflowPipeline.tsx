import React from "react";
import {interpolate} from "remotion";
import {COLORS, FONT_STACK, WorkflowStep} from "../timing";

interface WorkflowPipelineProps {
  // 0 -> 1: connector sweeps left to right
  progress: number;
  steps: WorkflowStep[];
}

export const WorkflowPipeline: React.FC<WorkflowPipelineProps> = ({
  progress,
  steps,
}) => {
  const count = steps.length;

  return (
    <div
      style={{
        position: "relative",
        width: 1560,
        fontFamily: FONT_STACK,
      }}
    >
      {/* Base connector line. */}
      <div
        style={{
          position: "absolute",
          top: 44,
          left: 80,
          right: 80,
          height: 4,
          borderRadius: 2,
          background: COLORS.cardBorder,
        }}
      />
      {/* Animated connector fill. */}
      <div
        style={{
          position: "absolute",
          top: 44,
          left: 80,
          width: `calc((100% - 160px) * ${progress})`,
          height: 4,
          borderRadius: 2,
          background: `linear-gradient(90deg, ${COLORS.blue}, ${COLORS.purple}, ${COLORS.cyan})`,
          boxShadow: `0 0 16px ${COLORS.blue}66`,
        }}
      />
      <div
        style={{
          position: "relative",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
        }}
      >
        {steps.map((step, i) => {
          // Each step lights up as the connector reaches its position.
          const threshold = count > 1 ? i / (count - 1) : 0;
          const lit = interpolate(
            progress,
            [threshold - 0.08, threshold + 0.04],
            [0, 1],
            {extrapolateLeft: "clamp", extrapolateRight: "clamp"}
          );
          const scale = 0.94 + 0.06 * lit;

          return (
            <div
              key={step.label}
              style={{
                width: 220,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                textAlign: "center",
              }}
            >
              <div
                style={{
                  width: 88,
                  height: 88,
                  borderRadius: 22,
                  background: COLORS.cardBg,
                  border: `2px solid ${
                    lit > 0.5 ? step.color : COLORS.cardBorder
                  }`,
                  boxShadow:
                    lit > 0.5
                      ? `0 0 28px ${step.color}66, 0 12px 30px rgba(15,23,42,0.10)`
                      : "0 8px 22px rgba(15,23,42,0.06)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  transform: `scale(${scale})`,
                  transition: "none",
                }}
              >
                <span
                  style={{
                    width: 22,
                    height: 22,
                    borderRadius: "50%",
                    background: lit > 0.5 ? step.color : COLORS.cardBorder,
                    boxShadow: lit > 0.5 ? `0 0 14px ${step.color}` : "none",
                  }}
                />
              </div>
              <div
                style={{
                  marginTop: 18,
                  fontSize: 24,
                  fontWeight: 600,
                  color: lit > 0.5 ? COLORS.textPrimary : COLORS.textSecondary,
                  opacity: 0.5 + 0.5 * lit,
                }}
              >
                {step.label}
              </div>
              <div
                style={{
                  marginTop: 6,
                  fontSize: 16,
                  fontWeight: 400,
                  color: COLORS.textSecondary,
                  opacity: 0.4 + 0.6 * lit,
                  maxWidth: 200,
                  lineHeight: 1.3,
                }}
              >
                {step.caption}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
