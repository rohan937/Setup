import React from "react";
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";
import {COLORS, FONT_STACK, SCRIPT} from "../timing";
import {AmbientBackground} from "../components/AmbientBackground";
import {AppHeaderMock} from "../components/AppHeaderMock";
import {TabBarMock} from "../components/TabBarMock";
import {RealityCheckPanelMock} from "../components/RealityCheckPanelMock";
import {ProductFrame} from "../components/ProductFrame";
import {AnimatedCursor} from "../components/AnimatedCursor";
import {Caption} from "./Caption";

const WS = SCRIPT.workspace;
const FRAME_W = 1320;
const FRAME_H = 760;

// Scene 5 (28-39s): the Reality tab is active. The Backtest Reality Check panel
// slides in; its checks reveal one-by-one. The cursor moves to the "Turnover"
// check and a tooltip appears explaining the cost-sensitivity risk.
export const RealityScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const frameAppear = spring({frame, fps, config: {damping: 200, mass: 0.8}});
  const panelAppear = interpolate(frame, [12, 40], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Reveal checks one-by-one.
  const total = SCRIPT.reality.panel.checks.length;
  const revealCount = Math.round(
    interpolate(frame, [40, 130], [0, total], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );

  // Cursor moves to the "Turnover" check (3rd row) then holds; tooltip shows.
  const cx = interpolate(frame, [150, 200], [1180, 1000], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const cy = interpolate(frame, [150, 200], [360, 560], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const hovering = frame >= 196;
  const showTooltip = frame >= 206;

  return (
    <AbsoluteFill>
      <AmbientBackground tint="tension" />

      <AbsoluteFill style={{alignItems: "center", justifyContent: "center"}}>
        <ProductFrame width={FRAME_W} height={FRAME_H} appear={frameAppear} glow={COLORS.warning} titlebarDots>
          <div style={{display: "flex", flexDirection: "column", height: "100%"}}>
            <AppHeaderMock area="Strategy Workspace" />
            <div
              style={{
                flex: 1,
                minHeight: 0,
                padding: "20px 30px 28px",
                fontFamily: FONT_STACK,
                display: "flex",
                flexDirection: "column",
                gap: 18,
              }}
            >
              <div style={{fontSize: 18, fontWeight: 800, color: COLORS.textPrimary}}>
                {WS.strategyName}
              </div>
              <TabBarMock tabs={[...WS.tabs]} active="Reality" />
              <div style={{flex: 1, display: "flex", alignItems: "center", justifyContent: "center"}}>
                <RealityCheckPanelMock
                  appear={panelAppear}
                  revealCount={revealCount}
                  showTooltip={showTooltip}
                />
              </div>
            </div>
          </div>
        </ProductFrame>
      </AbsoluteFill>

      <Caption
        text={SCRIPT.reality.caption}
        sub={SCRIPT.reality.sub}
        kicker="Backtest Reality Check"
        inAt={14}
        position="bottom"
      />

      <AnimatedCursor
        x={cx}
        y={cy}
        hovering={hovering}
        ringColor={COLORS.warning}
        label={hovering ? "Turnover 1.8x" : undefined}
      />
    </AbsoluteFill>
  );
};
