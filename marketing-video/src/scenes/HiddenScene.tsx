import React from "react";
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from "remotion";
import {COLORS, FONT_STACK, MetricTone, SCRIPT} from "../timing";
import {AmbientBackground} from "../components/AmbientBackground";
import {AnimatedCursor} from "../components/AnimatedCursor";
import {toneColor, toneGlyph} from "../components/tone";
import {Caption} from "./Caption";

const CARD = SCRIPT.hook.card;
const WARNINGS = SCRIPT.hidden.warnings;

// Scene 2 (5-10s): the confident card shifts up; hidden warning rows reveal
// one-by-one beneath it. The reassuring green glow curdles to amber. The
// AnimatedCursor enters and moves to hover the "Reality Check" affordance.
export const HiddenScene: React.FC = () => {
  const frame = useCurrentFrame();

  // Card shifts up to make room for the warning rows.
  const shift = interpolate(frame, [0, 22], [0, -118], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });

  // Green -> amber crossfade on the headline metric.
  const amber = interpolate(frame, [10, 40], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Cursor path: from off to the right toward the "Reality Check" pill.
  const cx = interpolate(frame, [40, 95], [1180, 980], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const cy = interpolate(frame, [40, 95], [380, 632], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const hovering = frame >= 90;

  return (
    <AbsoluteFill>
      <AmbientBackground tint="tension" />

      <AbsoluteFill
        style={{alignItems: "center", justifyContent: "center", fontFamily: FONT_STACK}}
      >
        <div style={{position: "relative", width: 640, transform: `translateY(${shift}px)`}}>
          {/* The same backtest card. */}
          <div
            style={{
              width: 640,
              padding: "26px 32px",
              borderRadius: 20,
              background: COLORS.surface,
              border: `1px solid ${COLORS.border}`,
              boxShadow: "0 40px 100px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.04)",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 18,
              }}
            >
              <div style={{fontSize: 19, fontWeight: 800, color: COLORS.textPrimary}}>
                {CARD.title}
              </div>
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 700,
                  color: COLORS.warning,
                  background: "rgba(255,181,71,0.12)",
                  border: `1px solid rgba(255,181,71,0.3)`,
                  borderRadius: 999,
                  padding: "5px 12px",
                }}
              >
                Under review
              </span>
            </div>
            <div style={{display: "flex", gap: 12}}>
              {CARD.metrics.map((m, i) => {
                const isSharpe = i === 0;
                const ringR = interpolate(amber, [0, 1], [0, 0]);
                const baseColor = toneColor(m.tone as MetricTone);
                const color = isSharpe
                  ? `color-mix(in srgb, ${COLORS.success} ${(1 - amber) * 100}%, ${COLORS.warning})`
                  : baseColor;
                return (
                  <div
                    key={m.label}
                    style={{
                      flex: 1,
                      padding: "12px 13px",
                      borderRadius: 11,
                      background: COLORS.elevated,
                      border: `1px solid ${
                        isSharpe ? `rgba(255,181,71,${0.2 + amber * 0.4})` : COLORS.border
                      }`,
                      boxShadow: isSharpe
                        ? `0 0 ${amber * 26 + ringR}px rgba(255,181,71,${amber * 0.5})`
                        : "none",
                    }}
                  >
                    <div style={{fontSize: 11, color: COLORS.textSecondary, marginBottom: 5, fontWeight: 600}}>
                      {m.label}
                    </div>
                    <div style={{fontSize: 20, fontWeight: 800, color}}>{m.value}</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Hidden warning rows revealing one-by-one beneath. */}
          <div
            style={{
              marginTop: 16,
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            {WARNINGS.map((w, i) => {
              const start = 22 + i * 13;
              const reveal = interpolate(frame, [start, start + 12], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: Easing.out(Easing.cubic),
              });
              const color = toneColor(w.tone as MetricTone);
              return (
                <div
                  key={w.label}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 13,
                    padding: "13px 16px",
                    borderRadius: 12,
                    background: COLORS.surface,
                    border: `1px solid ${color}44`,
                    boxShadow: `0 0 22px ${color}1f`,
                    opacity: reveal,
                    transform: `translateY(${(1 - reveal) * 14}px)`,
                  }}
                >
                  <span
                    style={{
                      width: 24,
                      height: 24,
                      flexShrink: 0,
                      borderRadius: "50%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 13,
                      fontWeight: 800,
                      color: "#0B1020",
                      background: color,
                      boxShadow: `0 0 12px ${color}88`,
                    }}
                  >
                    {toneGlyph(w.tone as MetricTone)}
                  </span>
                  <span style={{fontSize: 14, color: COLORS.textPrimary, fontWeight: 600}}>
                    {w.label}
                  </span>
                  <span style={{marginLeft: "auto", fontSize: 13.5, color, fontWeight: 700}}>
                    {w.value}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </AbsoluteFill>

      <Caption
        text={SCRIPT.hidden.caption}
        sub={SCRIPT.hidden.sub}
        kicker="The catch"
        position="top"
        inAt={6}
      />

      <AnimatedCursor
        x={cx}
        y={cy}
        hovering={hovering}
        ringColor={COLORS.warning}
        label={hovering ? "Reality Check" : undefined}
      />
    </AbsoluteFill>
  );
};
