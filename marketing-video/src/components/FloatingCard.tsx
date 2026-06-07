import React from "react";
import {COLORS, FONT_STACK} from "../timing";

interface FloatingCardProps {
  children: React.ReactNode;
  width?: number;
  // 0 -> 1: translateY(30px -> 0) + fade
  rise: number;
  title?: string;
}

export const FloatingCard: React.FC<FloatingCardProps> = ({
  children,
  width = 760,
  rise,
  title,
}) => {
  const translateY = (1 - rise) * 30;
  const opacity = rise;

  return (
    <div
      style={{
        position: "relative",
        width,
        transform: `translateY(${translateY}px)`,
        opacity,
        fontFamily: FONT_STACK,
      }}
    >
      {/* Soft color glow behind the card. */}
      <div
        style={{
          position: "absolute",
          inset: -40,
          borderRadius: 40,
          background: `radial-gradient(circle at 30% 0%, ${COLORS.blue}33, transparent 60%), radial-gradient(circle at 80% 100%, ${COLORS.purple}2e, transparent 60%)`,
          filter: "blur(40px)",
          opacity: 0.9,
          zIndex: 0,
        }}
      />
      <div
        style={{
          position: "relative",
          zIndex: 1,
          background: COLORS.cardBg,
          backdropFilter: "blur(18px)",
          WebkitBackdropFilter: "blur(18px)",
          border: `1px solid ${COLORS.cardBorder}`,
          borderRadius: 24,
          boxShadow:
            "0 30px 70px rgba(15, 23, 42, 0.12), 0 6px 18px rgba(15, 23, 42, 0.06)",
          padding: "40px 44px",
        }}
      >
        {title ? (
          <div
            style={{
              fontSize: 30,
              fontWeight: 600,
              color: COLORS.textPrimary,
              letterSpacing: "-0.01em",
              marginBottom: 28,
            }}
          >
            {title}
          </div>
        ) : null}
        {children}
      </div>
    </div>
  );
};
