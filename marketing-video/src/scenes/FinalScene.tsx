import React from "react";
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";
import {COLORS, FONT_STACK, SCRIPT} from "../timing";
import {AmbientBackground} from "../components/AmbientBackground";

const FINAL = SCRIPT.final;

// The six capabilities listed under the system map.
const CAPABILITIES = [
  "Reliability Score",
  "Backtest Reality",
  "Evidence Verification",
  "Shadow Drift",
  "Risk Narrative",
  "Promotion Packet",
];

const SUBTEXT = "Know what changed. Know what is missing. Know what is ready.";

// Scene 9 (66-72s): the system map (Evidence -> Reality -> Verification ->
// Governance -> Promotion), the six capabilities, the tagline, the wordmark,
// and the disclaimer. Settles cleanly.
export const FinalScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const mapAppear = spring({frame, fps, config: {damping: 200, mass: 0.7}});
  const titleAppear = interpolate(frame, [28, 52], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const subAppear = interpolate(frame, [44, 66], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const brandAppear = interpolate(frame, [60, 84], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill>
      <AmbientBackground />

      <AbsoluteFill
        style={{
          alignItems: "center",
          justifyContent: "center",
          fontFamily: FONT_STACK,
          gap: 30,
          padding: "0 80px",
        }}
      >
        {/* System map. */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 0,
            opacity: mapAppear,
            transform: `translateY(${(1 - mapAppear) * 20}px)`,
          }}
        >
          {FINAL.systemMap.map((node, i) => {
            const nodeAppear = interpolate(frame, [i * 6, i * 6 + 16], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.out(Easing.cubic),
            });
            return (
              <React.Fragment key={node}>
                <div
                  style={{
                    padding: "11px 20px",
                    borderRadius: 12,
                    background: COLORS.surface,
                    border: `1px solid ${COLORS.border}`,
                    boxShadow: `0 8px 24px rgba(0,0,0,0.4), 0 0 22px ${COLORS.blue}1f`,
                    fontSize: 15,
                    fontWeight: 700,
                    color: COLORS.textPrimary,
                    opacity: nodeAppear,
                    transform: `scale(${0.9 + nodeAppear * 0.1})`,
                    whiteSpace: "nowrap",
                  }}
                >
                  {node}
                </div>
                {i < FINAL.systemMap.length - 1 ? (
                  <div
                    style={{
                      width: 34,
                      height: 2,
                      margin: "0 4px",
                      background: `linear-gradient(90deg, ${COLORS.blue}, ${COLORS.purple})`,
                      opacity: nodeAppear,
                      boxShadow: `0 0 8px ${COLORS.blue}88`,
                    }}
                  />
                ) : null}
              </React.Fragment>
            );
          })}
        </div>

        {/* Six capabilities. */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            gap: 12,
            maxWidth: 920,
            opacity: mapAppear,
          }}
        >
          {CAPABILITIES.map((cap, i) => {
            const capAppear = interpolate(frame, [18 + i * 4, 18 + i * 4 + 14], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            return (
              <span
                key={cap}
                style={{
                  fontSize: 13.5,
                  fontWeight: 600,
                  color: COLORS.textSecondary,
                  background: "rgba(255,255,255,0.04)",
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: 999,
                  padding: "7px 15px",
                  opacity: capAppear,
                  transform: `translateY(${(1 - capAppear) * 10}px)`,
                }}
              >
                {cap}
              </span>
            );
          })}
        </div>

        {/* Tagline. */}
        <div
          style={{
            fontSize: 52,
            fontWeight: 800,
            color: COLORS.textPrimary,
            textAlign: "center",
            letterSpacing: "-0.03em",
            lineHeight: 1.1,
            maxWidth: 1100,
            marginTop: 12,
            opacity: titleAppear,
            transform: `translateY(${(1 - titleAppear) * 18}px)`,
            textShadow: "0 4px 40px rgba(0,0,0,0.5)",
          }}
        >
          {FINAL.title}
        </div>

        {/* Subtext. */}
        <div
          style={{
            fontSize: 19,
            fontWeight: 500,
            color: COLORS.textSecondary,
            textAlign: "center",
            opacity: subAppear,
            transform: `translateY(${(1 - subAppear) * 12}px)`,
          }}
        >
          {SUBTEXT}
        </div>

        {/* Wordmark. */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            marginTop: 14,
            opacity: brandAppear,
            transform: `translateY(${(1 - brandAppear) * 12}px)`,
          }}
        >
          <div
            style={{
              width: 30,
              height: 30,
              borderRadius: 9,
              background: `linear-gradient(135deg, ${COLORS.blue}, ${COLORS.purple})`,
              boxShadow: `0 6px 20px ${COLORS.blue}66`,
            }}
          />
          <span
            style={{
              fontSize: 30,
              fontWeight: 800,
              color: COLORS.textPrimary,
              letterSpacing: "-0.02em",
            }}
          >
            {FINAL.brand}
          </span>
        </div>

        {/* Disclaimer. */}
        <div
          style={{
            fontSize: 12.5,
            fontWeight: 500,
            color: COLORS.textMuted,
            marginTop: 6,
            opacity: brandAppear,
          }}
        >
          {FINAL.disclaimer}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
