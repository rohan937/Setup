import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {AmbientBackground} from "../components/AmbientBackground";
import {SceneTitle} from "../components/SceneTitle";
import {COLORS, SCRIPT} from "../timing";

// Faint floating card outlines behind the title for depth.
const ghostCards = [
  {x: -560, y: -180, w: 280, h: 180, r: -6},
  {x: 540, y: -120, w: 300, h: 200, r: 5},
  {x: -440, y: 220, w: 260, h: 160, r: 4},
  {x: 520, y: 240, w: 280, h: 170, r: -5},
];

export const ProductRevealScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();

  const progress = interpolate(frame, [4, 28], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const exit = interpolate(
    frame,
    [durationInFrames - 12, durationInFrames],
    [1, 0],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"}
  );

  // Glow sweep that moves horizontally.
  const sweepX = interpolate(frame, [0, durationInFrames], [-600, 600]);

  return (
    <AbsoluteFill style={{opacity: exit}}>
      <AmbientBackground />

      {/* Ghost card outlines. */}
      <AbsoluteFill style={{justifyContent: "center", alignItems: "center"}}>
        {ghostCards.map((c, i) => {
          const cardAppear = interpolate(
            frame,
            [i * 4, i * 4 + 20],
            [0, 1],
            {extrapolateLeft: "clamp", extrapolateRight: "clamp"}
          );
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                width: c.w,
                height: c.h,
                left: `calc(50% + ${c.x}px)`,
                top: `calc(50% + ${c.y}px)`,
                marginLeft: -c.w / 2,
                marginTop: -c.h / 2,
                borderRadius: 20,
                border: `1px solid ${COLORS.cardBorder}`,
                background: "rgba(255,255,255,0.35)",
                transform: `rotate(${c.r}deg)`,
                opacity: cardAppear * 0.6,
              }}
            />
          );
        })}
      </AbsoluteFill>

      {/* Glow sweep. */}
      <AbsoluteFill style={{justifyContent: "center", alignItems: "center"}}>
        <div
          style={{
            position: "absolute",
            width: 500,
            height: 700,
            transform: `translateX(${sweepX}px) rotate(18deg)`,
            background:
              "linear-gradient(90deg, transparent, rgba(255,255,255,0.5), transparent)",
            filter: "blur(40px)",
            opacity: 0.6,
          }}
        />
      </AbsoluteFill>

      <SceneTitle
        title={SCRIPT.reveal.title}
        subtitle={SCRIPT.reveal.subtitle}
        progress={progress}
      />
    </AbsoluteFill>
  );
};
