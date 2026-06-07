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
import {MetricRow} from "../components/MetricRow";
import {COLORS, FONT_STACK, SCRIPT} from "../timing";

export const BacktestCardScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  const rise = spring({
    frame,
    fps,
    config: {damping: 200, mass: 0.7},
    durationInFrames: 24,
  });

  const metrics = SCRIPT.backtest.metrics;
  const rowStart = 16;
  const rowStagger = 9;

  // Badge appears after all rows.
  const badgeStart = rowStart + metrics.length * rowStagger + 6;
  const badgeAppear = interpolate(
    frame,
    [badgeStart, badgeStart + 14],
    [0, 1],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"}
  );

  const captionStart = badgeStart + 12;
  const captionAppear = interpolate(
    frame,
    [captionStart, captionStart + 16],
    [0, 1],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"}
  );

  const sceneExit = interpolate(
    frame,
    [durationInFrames - 12, durationInFrames],
    [1, 0],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"}
  );

  return (
    <AbsoluteFill style={{opacity: sceneExit}}>
      <AmbientBackground />
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          fontFamily: FONT_STACK,
        }}
      >
        <FloatingCard width={760} rise={rise} title={SCRIPT.backtest.title}>
          {metrics.map((m, i) => {
            const start = rowStart + i * rowStagger;
            const appear = interpolate(frame, [start, start + 12], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            return (
              <MetricRow
                key={m.label}
                label={m.label}
                value={m.value}
                tone={m.tone}
                appear={appear}
              />
            );
          })}

          {/* Amber reality-check badge. */}
          <div
            style={{
              marginTop: 28,
              opacity: badgeAppear,
              transform: `translateY(${(1 - badgeAppear) * 10}px)`,
            }}
          >
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 12,
                padding: "12px 22px",
                borderRadius: 14,
                background: `${COLORS.warning}1f`,
                border: `1px solid ${COLORS.warning}55`,
                color: COLORS.warning,
                fontSize: 22,
                fontWeight: 700,
                boxShadow: `0 0 24px ${COLORS.warning}33`,
              }}
            >
              <span
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: "50%",
                  background: COLORS.warning,
                  boxShadow: `0 0 12px ${COLORS.warning}`,
                }}
              />
              {SCRIPT.backtest.badge}
            </div>
          </div>
        </FloatingCard>

        <div
          style={{
            marginTop: 36,
            maxWidth: 760,
            textAlign: "center",
            fontSize: 26,
            fontWeight: 500,
            color: COLORS.textSecondary,
            opacity: captionAppear,
            transform: `translateY(${(1 - captionAppear) * 10}px)`,
            lineHeight: 1.4,
          }}
        >
          {SCRIPT.backtest.caption}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
