import React from "react";
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";
import {COLORS, FONT_STACK, MetricTone, SCRIPT} from "../timing";
import {AmbientBackground} from "../components/AmbientBackground";
import {AppHeaderMock} from "../components/AppHeaderMock";
import {SidebarMock} from "../components/SidebarMock";
import {StrategyCardMock} from "../components/StrategyCardMock";
import {LifecycleMock} from "../components/LifecycleMock";
import {ProductFrame} from "../components/ProductFrame";
import {AnimatedCursor} from "../components/AnimatedCursor";
import {toneColor} from "../components/tone";
import {Caption} from "./Caption";

const CC = SCRIPT.commandCenter;
const FRAME_W = 1320;
const FRAME_H = 760;

// Scene 3 (10-18s): the full Research Command Center. App header + sidebar +
// workspace-health summary + a mini lifecycle pipeline + a list of strategy
// rows. The cursor travels to the headline strategy, hovers (the row lifts and
// glows), then clicks it (ClickRipple).
export const CommandCenterScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const appear = spring({frame, fps, config: {damping: 200, mass: 0.8}});

  // Pipeline connector flow.
  const pipeProgress = interpolate(frame, [20, 70], [0, 0.55], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // The headline row is index 0 (SPY Trend Following v3).
  const targetIndex = 0;

  // Cursor choreography (px in the 1920x1080 frame).
  // Travels from upper area down to the first strategy row, hovers, clicks.
  const cx = interpolate(frame, [55, 110, 150], [1180, 900, 900], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const cy = interpolate(frame, [55, 110, 150], [300, 560, 560], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const hovering = frame >= 108;
  const clickFrame = 150;
  const clickProgress = interpolate(frame, [clickFrame, clickFrame + 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const clicking = frame >= clickFrame && frame <= clickFrame + 6;

  return (
    <AbsoluteFill>
      <AmbientBackground />

      <AbsoluteFill style={{alignItems: "center", justifyContent: "center"}}>
        <ProductFrame
          width={FRAME_W}
          height={FRAME_H}
          appear={appear}
          glow={COLORS.blue}
          titlebarDots
        >
          <div style={{display: "flex", flexDirection: "column", height: "100%"}}>
            <AppHeaderMock area="Research Command Center" />
            <div style={{display: "flex", flex: 1, minHeight: 0}}>
              <SidebarMock active="Home" />
              <div
                style={{
                  flex: 1,
                  minWidth: 0,
                  padding: "22px 26px",
                  overflow: "hidden",
                  fontFamily: FONT_STACK,
                  display: "flex",
                  flexDirection: "column",
                  gap: 18,
                }}
              >
                <div style={{fontSize: 18, fontWeight: 800, color: COLORS.textPrimary}}>
                  Workspace Health
                </div>

                {/* Summary tiles. */}
                <div style={{display: "flex", gap: 14}}>
                  {CC.summary.map((s) => {
                    const accent = toneColor(s.tone as MetricTone);
                    return (
                      <div
                        key={s.label}
                        style={{
                          flex: 1,
                          padding: "14px 16px",
                          borderRadius: 13,
                          background: COLORS.surface,
                          border: `1px solid ${COLORS.border}`,
                          boxShadow: "0 2px 10px rgba(0,0,0,0.3)",
                        }}
                      >
                        <div style={{fontSize: 11.5, color: COLORS.textSecondary, fontWeight: 600, marginBottom: 8}}>
                          {s.label}
                        </div>
                        <div style={{fontSize: 26, fontWeight: 800, color: accent, letterSpacing: "-0.02em"}}>
                          {s.value}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Mini lifecycle pipeline. */}
                <div
                  style={{
                    padding: "16px 22px",
                    borderRadius: 13,
                    background: "rgba(255,255,255,0.02)",
                    border: `1px solid ${COLORS.border}`,
                  }}
                >
                  <LifecycleMock currentKey="paperCandidate" progress={pipeProgress} />
                </div>

                {/* Strategy rows. */}
                <div style={{display: "flex", flexDirection: "column", gap: 11}}>
                  {CC.strategies.map((s, i) => (
                    <StrategyCardMock
                      key={s.name}
                      name={s.name}
                      stage={s.stage}
                      score={s.score}
                      highlighted={hovering && i === targetIndex}
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>
        </ProductFrame>
      </AbsoluteFill>

      <Caption
        text={SCRIPT.commandCenter.caption}
        sub={SCRIPT.commandCenter.sub}
        kicker="Command Center"
        inAt={20}
        position="bottom"
      />

      <AnimatedCursor
        x={cx}
        y={cy}
        hovering={hovering}
        clicking={clicking}
        clickProgress={clickProgress}
        ringColor={COLORS.blue}
        label={hovering ? "Open strategy" : undefined}
      />
    </AbsoluteFill>
  );
};
