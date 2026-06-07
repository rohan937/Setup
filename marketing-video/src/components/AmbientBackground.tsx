import React from "react";
import {AbsoluteFill, useCurrentFrame} from "remotion";
import {COLORS} from "../timing";

interface Blob {
  color: string;
  size: number;
  baseX: number;
  baseY: number;
  driftX: number;
  driftY: number;
  speed: number;
  phase: number;
  opacity: number;
}

interface AmbientBackgroundProps {
  // Shifts the dominant glow. "tension" leans into deeper blues.
  tint?: "default" | "tension";
}

const baseBlobs: Blob[] = [
  {
    color: COLORS.blue,
    size: 900,
    baseX: 12,
    baseY: 18,
    driftX: 40,
    driftY: 30,
    speed: 0.012,
    phase: 0,
    opacity: 0.18,
  },
  {
    color: COLORS.purple,
    size: 820,
    baseX: 78,
    baseY: 28,
    driftX: 35,
    driftY: 45,
    speed: 0.009,
    phase: 1.6,
    opacity: 0.16,
  },
  {
    color: COLORS.cyan,
    size: 760,
    baseX: 60,
    baseY: 82,
    driftX: 50,
    driftY: 35,
    speed: 0.011,
    phase: 3.1,
    opacity: 0.15,
  },
  {
    color: COLORS.blue,
    size: 640,
    baseX: 28,
    baseY: 78,
    driftX: 30,
    driftY: 40,
    speed: 0.008,
    phase: 4.4,
    opacity: 0.12,
  },
];

export const AmbientBackground: React.FC<AmbientBackgroundProps> = ({
  tint = "default",
}) => {
  const frame = useCurrentFrame();

  const blobs =
    tint === "tension"
      ? baseBlobs.map((b, i) => ({
          ...b,
          color: i === 1 ? "#3B5BDB" : i === 2 ? COLORS.blue : b.color,
          opacity: b.opacity + 0.05,
        }))
      : baseBlobs;

  return (
    <AbsoluteFill style={{backgroundColor: COLORS.bg, overflow: "hidden"}}>
      {blobs.map((b, i) => {
        const dx = Math.sin(frame * b.speed + b.phase) * b.driftX;
        const dy = Math.cos(frame * b.speed * 0.85 + b.phase) * b.driftY;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: `${b.baseX}%`,
              top: `${b.baseY}%`,
              width: b.size,
              height: b.size,
              marginLeft: -b.size / 2,
              marginTop: -b.size / 2,
              borderRadius: "50%",
              background: `radial-gradient(circle at center, ${b.color} 0%, rgba(255,255,255,0) 70%)`,
              opacity: b.opacity,
              filter: "blur(100px)",
              transform: `translate(${dx}px, ${dy}px)`,
            }}
          />
        );
      })}
      {/* Soft top wash to keep things airy and premium. */}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(255,255,255,0.55) 0%, rgba(255,255,255,0) 35%)",
        }}
      />
    </AbsoluteFill>
  );
};
