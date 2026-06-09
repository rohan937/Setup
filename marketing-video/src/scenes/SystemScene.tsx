import React from "react";
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from "remotion";
import {COLORS, FONT_STACK, SCRIPT} from "../timing";
import {AmbientBackground} from "../components/AmbientBackground";
import {Caption} from "./Caption";

const SYSTEM = SCRIPT.system;

// Two-digit hex alpha (00-ff) from a 0..1 value scaled to `max` (default 255).
const hexA = (t: number, max = 255): string =>
  Math.round(Math.max(0, Math.min(1, t)) * max)
    .toString(16)
    .padStart(2, "0");

// Scene 8 (60-66s) — "Research Governance System".
// A screenshot-free system diagram that replaces the old product montage:
// the governed workflow (Evidence -> Reality -> Verification -> Governance ->
// Promotion) with the six QuantFidelity modules lighting up beneath it.
// No <Img>, no SafeScreenshotFrame, no fallback preview cards. Pure motion
// graphics in the dark QuantFidelity palette, so it never depends on PNGs.
export const SystemScene: React.FC = () => {
  const frame = useCurrentFrame();

  const headerAppear = interpolate(frame, [0, 16], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  return (
    <AbsoluteFill>
      <AmbientBackground />

      <AbsoluteFill
        style={{
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: FONT_STACK,
          gap: 52,
          padding: "0 90px",
        }}
      >
        {/* Kicker. */}
        <div
          style={{
            fontSize: 14,
            fontWeight: 700,
            letterSpacing: "0.22em",
            textTransform: "uppercase",
            color: COLORS.blue,
            opacity: headerAppear,
            transform: `translateY(${(1 - headerAppear) * -10}px)`,
          }}
        >
          {SYSTEM.kicker}
        </div>

        {/* Workflow pipeline — nodes light up left to right. */}
        <div style={{display: "flex", alignItems: "center", gap: 0}}>
          {SYSTEM.pipeline.map((node, i) => {
            const start = 8 + i * 9;
            const appear = interpolate(frame, [start, start + 16], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.out(Easing.cubic),
            });
            return (
              <React.Fragment key={node}>
                <div
                  style={{
                    padding: "15px 28px",
                    borderRadius: 14,
                    background: COLORS.surface,
                    border: `1px solid ${COLORS.border}`,
                    boxShadow: `0 10px 30px rgba(0,0,0,0.45), 0 0 ${
                      appear * 30
                    }px ${COLORS.blue}${hexA(appear, 64)}`,
                    fontSize: 20,
                    fontWeight: 700,
                    color: COLORS.textPrimary,
                    opacity: appear,
                    transform: `translateY(${(1 - appear) * 16}px) scale(${
                      0.92 + appear * 0.08
                    })`,
                    whiteSpace: "nowrap",
                  }}
                >
                  {node}
                </div>
                {i < SYSTEM.pipeline.length - 1 ? (
                  <div
                    style={{
                      width: 46,
                      height: 2,
                      margin: "0 6px",
                      background: `linear-gradient(90deg, ${COLORS.blue}, ${COLORS.purple})`,
                      opacity: appear,
                      boxShadow: `0 0 10px ${COLORS.blue}aa`,
                    }}
                  />
                ) : null}
              </React.Fragment>
            );
          })}
        </div>

        {/* Six modules — light up one by one beneath the pipeline. */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 300px)",
            gap: 20,
          }}
        >
          {SYSTEM.modules.map((mod, i) => {
            const start = 52 + i * 9;
            const lit = interpolate(frame, [start, start + 18], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.out(Easing.cubic),
            });
            return (
              <div
                key={mod}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 14,
                  padding: "18px 22px",
                  borderRadius: 14,
                  background: `rgba(22,32,51,${0.55 + lit * 0.35})`,
                  border: `1px solid rgba(79,140,255,${0.08 + lit * 0.34})`,
                  boxShadow: `0 8px 24px rgba(0,0,0,0.4), 0 0 ${
                    lit * 26
                  }px ${COLORS.blue}${hexA(lit, 60)}`,
                  opacity: 0.4 + lit * 0.6,
                  transform: `translateY(${(1 - lit) * 14}px)`,
                }}
              >
                <div
                  style={{
                    width: 12,
                    height: 12,
                    borderRadius: 999,
                    flexShrink: 0,
                    background: `linear-gradient(135deg, ${COLORS.blue}, ${COLORS.purple})`,
                    boxShadow: `0 0 ${4 + lit * 12}px ${COLORS.blue}`,
                    opacity: 0.5 + lit * 0.5,
                  }}
                />
                <span
                  style={{
                    fontSize: 17,
                    fontWeight: 600,
                    color: lit > 0.5 ? COLORS.textPrimary : COLORS.textSecondary,
                  }}
                >
                  {mod}
                </span>
              </div>
            );
          })}
        </div>
      </AbsoluteFill>

      {/* Copy. */}
      <AbsoluteFill style={{fontFamily: FONT_STACK, pointerEvents: "none"}}>
        <Caption text={SYSTEM.caption} inAt={24} position="bottom" />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
