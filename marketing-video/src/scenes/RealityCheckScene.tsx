import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {AmbientBackground} from "../components/AmbientBackground";
import {FloatingCard} from "../components/FloatingCard";
import {COLORS, FONT_STACK, SCRIPT} from "../timing";

export const RealityCheckScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  const rise = spring({
    frame,
    fps,
    config: {damping: 200, mass: 0.7},
    durationInFrames: 24,
  });

  const bullets = SCRIPT.reality.bullets;
  const bulletStart = 18;
  const bulletStagger = 12;

  const conclusionStart = bulletStart + bullets.length * bulletStagger + 8;
  const conclusionAppear = interpolate(
    frame,
    [conclusionStart, conclusionStart + 16],
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
        <FloatingCard width={820} rise={rise} title={SCRIPT.reality.title}>
          <div style={{display: "flex", flexDirection: "column", gap: 18}}>
            {bullets.map((b, i) => {
              const start = bulletStart + i * bulletStagger;
              const appear = interpolate(frame, [start, start + 14], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              });
              return (
                <div
                  key={b}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 16,
                    opacity: appear,
                    transform: `translateX(${(1 - appear) * 22}px)`,
                  }}
                >
                  <span
                    style={{
                      flexShrink: 0,
                      width: 26,
                      height: 26,
                      borderRadius: "50%",
                      background: `${COLORS.warning}22`,
                      border: `1.5px solid ${COLORS.warning}`,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: COLORS.warning,
                      fontSize: 16,
                      fontWeight: 700,
                    }}
                  >
                    !
                  </span>
                  <span
                    style={{
                      fontSize: 25,
                      fontWeight: 500,
                      color: COLORS.textPrimary,
                    }}
                  >
                    {b}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Conclusion box with amber glow. */}
          <div
            style={{
              marginTop: 32,
              opacity: conclusionAppear,
              transform: `translateY(${(1 - conclusionAppear) * 12}px)`,
            }}
          >
            <div
              style={{
                padding: "20px 26px",
                borderRadius: 16,
                background: `${COLORS.warning}14`,
                border: `1px solid ${COLORS.warning}55`,
                boxShadow: `0 0 32px ${COLORS.warning}30`,
                fontSize: 30,
                fontWeight: 700,
                color: COLORS.warning,
                textAlign: "center",
                letterSpacing: "-0.01em",
              }}
            >
              {SCRIPT.reality.conclusion}
            </div>
          </div>
        </FloatingCard>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
