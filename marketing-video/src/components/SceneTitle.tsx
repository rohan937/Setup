import React from "react";
import {AbsoluteFill} from "remotion";
import {COLORS, FONT_STACK} from "../timing";

interface SceneTitleProps {
  title: string;
  subtitle?: string;
  // 0 -> 1: fade + slide up
  progress: number;
  children?: React.ReactNode;
}

export const SceneTitle: React.FC<SceneTitleProps> = ({
  title,
  subtitle,
  progress,
  children,
}) => {
  const translateY = (1 - progress) * 20;
  const opacity = progress;

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        fontFamily: FONT_STACK,
      }}
    >
      {/* Glow sweep behind the title. */}
      <div
        style={{
          position: "absolute",
          width: 1100,
          height: 320,
          borderRadius: "50%",
          background: `radial-gradient(ellipse at center, ${COLORS.blue}26, transparent 70%)`,
          filter: "blur(60px)",
          opacity: progress * 0.9,
        }}
      />
      <div
        style={{
          position: "relative",
          textAlign: "center",
          transform: `translateY(${translateY}px)`,
          opacity,
          maxWidth: 1500,
        }}
      >
        <div
          style={{
            fontSize: 74,
            fontWeight: 700,
            letterSpacing: "-0.025em",
            color: COLORS.textPrimary,
            lineHeight: 1.08,
          }}
        >
          {title}
        </div>
        {subtitle ? (
          <div
            style={{
              marginTop: 28,
              fontSize: 36,
              fontWeight: 500,
              color: COLORS.textSecondary,
              letterSpacing: "0.01em",
            }}
          >
            {subtitle}
          </div>
        ) : null}
        {children ? <div style={{marginTop: 40}}>{children}</div> : null}
      </div>
    </AbsoluteFill>
  );
};
