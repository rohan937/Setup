import React from "react";
import {interpolate} from "remotion";
import {COLORS} from "../timing";

interface ClickRippleProps {
  // Center position in px (relative to the containing absolute layer).
  x: number;
  y: number;
  // 0 -> 1 lifecycle of the ripple.
  progress: number;
  color?: string;
  maxRadius?: number;
}

// An expanding, fading ring used to punctuate a click.
export const ClickRipple: React.FC<ClickRippleProps> = ({
  x,
  y,
  progress,
  color = COLORS.blue,
  maxRadius = 64,
}) => {
  if (progress <= 0 || progress >= 1) return null;

  const radius = interpolate(progress, [0, 1], [4, maxRadius], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = interpolate(progress, [0, 0.15, 1], [0, 0.7, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const borderWidth = interpolate(progress, [0, 1], [3, 1]);

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width: radius * 2,
        height: radius * 2,
        marginLeft: -radius,
        marginTop: -radius,
        borderRadius: "50%",
        border: `${borderWidth}px solid ${color}`,
        boxShadow: `0 0 24px ${color}88`,
        opacity,
        pointerEvents: "none",
      }}
    />
  );
};
