import React from "react";
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";
import {COLORS, FONT_STACK, MetricTone, SCRIPT} from "../timing";
import {AmbientBackground} from "../components/AmbientBackground";
import {toneColor} from "../components/tone";
import {Caption} from "./Caption";

const CARD = SCRIPT.hook.card;

// Scene 1 (0-5s): a clean, confident backtest card slides in. A soft green
// glow appears around the headline Sharpe metric. Caption sets up the hook.
export const HookScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const enter = spring({frame, fps, config: {damping: 200, mass: 0.9}});
  const rise = (1 - enter) * 36;

  // Green glow ramps up around the Sharpe metric.
  const glow = interpolate(frame, [22, 50], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill>
      <AmbientBackground />
      <AbsoluteFill
        style={{alignItems: "center", justifyContent: "center", fontFamily: FONT_STACK}}
      >
        <div
          style={{
            position: "relative",
            width: 640,
            padding: "34px 38px",
            borderRadius: 22,
            background: COLORS.surface,
            border: `1px solid ${COLORS.border}`,
            boxShadow:
              "0 50px 120px rgba(0,0,0,0.6), 0 16px 40px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.05)",
            opacity: enter,
            transform: `translateY(${rise}px) scale(${0.96 + enter * 0.04})`,
          }}
        >
          {/* Header. */}
          <div
            style={{
              display: "flex",
              alignItems: "flex-start",
              justifyContent: "space-between",
              marginBottom: 26,
            }}
          >
            <div>
              <div
                style={{fontSize: 22, fontWeight: 800, color: COLORS.textPrimary, letterSpacing: "-0.02em"}}
              >
                {CARD.title}
              </div>
              <div style={{marginTop: 6, fontSize: 13, color: COLORS.textMuted, fontWeight: 600}}>
                {CARD.assetClass} · Backtest v3
              </div>
            </div>
            <span
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: COLORS.success,
                background: "rgba(0,212,146,0.12)",
                border: `1px solid rgba(0,212,146,0.3)`,
                borderRadius: 999,
                padding: "6px 13px",
                whiteSpace: "nowrap",
              }}
            >
              {CARD.badge}
            </span>
          </div>

          {/* Metric grid. */}
          <div style={{display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14}}>
            {CARD.metrics.map((m, i) => {
              const isSharpe = i === 0;
              const accent = toneColor(m.tone as MetricTone);
              return (
                <div
                  key={m.label}
                  style={{
                    position: "relative",
                    padding: "16px 18px",
                    borderRadius: 14,
                    background: COLORS.elevated,
                    border: `1px solid ${
                      isSharpe ? `rgba(0,212,146,${0.25 + glow * 0.4})` : COLORS.border
                    }`,
                    boxShadow: isSharpe
                      ? `0 0 ${glow * 34}px rgba(0,212,146,${glow * 0.55}), inset 0 0 0 1px rgba(0,212,146,${glow * 0.2})`
                      : "0 2px 8px rgba(0,0,0,0.25)",
                    overflow: "hidden",
                  }}
                >
                  <div style={{fontSize: 12.5, fontWeight: 600, color: COLORS.textSecondary, marginBottom: 8}}>
                    {m.label}
                  </div>
                  <div
                    style={{
                      fontSize: 30,
                      fontWeight: 800,
                      color: accent,
                      letterSpacing: "-0.02em",
                      lineHeight: 1,
                    }}
                  >
                    {m.value}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </AbsoluteFill>

      <Caption
        text={SCRIPT.hook.caption}
        sub={SCRIPT.hook.sub}
        kicker="The setup"
        inAt={30}
      />
    </AbsoluteFill>
  );
};
