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
  // Shifts the dominant glow. "tension" leans into deeper, cooler tones.
  tint?: "default" | "tension";
  // Subtle AI sweep + scanlines. On by default; tasteful and low-contrast.
  sweep?: boolean;
}

const baseBlobs: Blob[] = [
  {
    color: COLORS.blue,
    size: 1000,
    baseX: 14,
    baseY: 20,
    driftX: 50,
    driftY: 38,
    speed: 0.0085,
    phase: 0,
    opacity: 0.16,
  },
  {
    color: COLORS.purple,
    size: 900,
    baseX: 80,
    baseY: 26,
    driftX: 44,
    driftY: 52,
    speed: 0.0068,
    phase: 1.6,
    opacity: 0.15,
  },
  {
    color: COLORS.cyan,
    size: 820,
    baseX: 62,
    baseY: 84,
    driftX: 58,
    driftY: 40,
    speed: 0.0079,
    phase: 3.1,
    opacity: 0.13,
  },
  {
    color: COLORS.blue,
    size: 680,
    baseX: 26,
    baseY: 80,
    driftX: 36,
    driftY: 46,
    speed: 0.0061,
    phase: 4.4,
    opacity: 0.1,
  },
];

export const AmbientBackground: React.FC<AmbientBackgroundProps> = ({
  tint = "default",
  sweep = true,
}) => {
  const frame = useCurrentFrame();

  const blobs =
    tint === "tension"
      ? baseBlobs.map((b, i) => ({
          ...b,
          color: i === 1 ? "#3B5BDB" : i === 2 ? COLORS.blue : b.color,
          opacity: b.opacity + 0.04,
        }))
      : baseBlobs;

  // Slow diagonal AI sweep across the frame.
  const sweepX = ((Math.sin(frame * 0.006) + 1) / 2) * 60 - 30; // -30..30 %

  return (
    <AbsoluteFill style={{backgroundColor: COLORS.bg, overflow: "hidden"}}>
      {/* Deep vignette to anchor the dark base. */}
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(120% 100% at 50% 0%, rgba(79,140,255,0.05) 0%, rgba(11,16,32,0) 45%), radial-gradient(120% 120% at 50% 120%, rgba(11,16,32,0.6) 0%, rgba(11,16,32,0) 50%)",
        }}
      />

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
              background: `radial-gradient(circle at center, ${b.color} 0%, rgba(11,16,32,0) 70%)`,
              opacity: b.opacity,
              filter: "blur(110px)",
              transform: `translate(${dx}px, ${dy}px)`,
            }}
          />
        );
      })}

      {sweep ? (
        <>
          {/* Soft AI sweep — a very faint moving sheen. */}
          <AbsoluteFill
            style={{
              background: `linear-gradient(115deg, rgba(255,255,255,0) 40%, rgba(139,92,246,0.05) 50%, rgba(255,255,255,0) 60%)`,
              transform: `translateX(${sweepX}%)`,
            }}
          />
          {/* Subtle scanlines for a quiet technical texture. */}
          <AbsoluteFill
            style={{
              backgroundImage:
                "repeating-linear-gradient(0deg, rgba(255,255,255,0.018) 0px, rgba(255,255,255,0.018) 1px, transparent 1px, transparent 3px)",
              opacity: 0.5,
              mixBlendMode: "overlay",
            }}
          />
        </>
      ) : null}
    </AbsoluteFill>
  );
};
