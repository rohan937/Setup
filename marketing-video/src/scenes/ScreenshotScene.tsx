import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {AmbientBackground} from "../components/AmbientBackground";
import {ScreenshotFrame} from "../components/ScreenshotFrame";
import {COLORS, FONT_STACK, SCRIPT} from "../timing";

export const ScreenshotScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();

  const shots = SCRIPT.screenshots.shots;
  const stagger = 8;
  const positions = [
    {offsetX: -560, rotate: -4},
    {offsetX: 0, rotate: 0},
    {offsetX: 560, rotate: 4},
  ];

  const captionStart = shots.length * stagger + 14;
  const captionAppear = interpolate(
    frame,
    [captionStart, captionStart + 16],
    [0, 1],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"}
  );

  const exit = interpolate(
    frame,
    [durationInFrames - 12, durationInFrames],
    [1, 0],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"}
  );

  return (
    <AbsoluteFill style={{opacity: exit}}>
      <AmbientBackground />
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          fontFamily: FONT_STACK,
        }}
      >
        <div
          style={{
            position: "relative",
            width: 1600,
            height: 420,
          }}
        >
          {shots.map((shot, i) => {
            const start = i * stagger;
            const appear = interpolate(frame, [start, start + 20], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            const pos = positions[i] ?? {offsetX: 0, rotate: 0};
            // Middle card sits slightly forward/higher.
            const isCenter = i === 1;
            return (
              <div
                key={shot.src}
                style={{
                  position: "absolute",
                  left: "50%",
                  top: "50%",
                  marginLeft: -260,
                  marginTop: isCenter ? -190 : -160,
                  zIndex: isCenter ? 2 : 1,
                }}
              >
                <ScreenshotFrame
                  src={shot.src}
                  label={shot.label}
                  width={520}
                  appear={appear}
                  offsetX={pos.offsetX}
                  rotate={pos.rotate}
                />
              </div>
            );
          })}
        </div>

        <div
          style={{
            position: "absolute",
            bottom: 110,
            fontSize: 30,
            fontWeight: 600,
            color: COLORS.textSecondary,
            opacity: captionAppear,
            transform: `translateY(${(1 - captionAppear) * 10}px)`,
            textAlign: "center",
            maxWidth: 1200,
          }}
        >
          {SCRIPT.screenshots.caption}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
