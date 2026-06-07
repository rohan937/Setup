import React from "react";
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";
import {COLORS, FONT_STACK, SCRIPT} from "../timing";
import {AmbientBackground} from "../components/AmbientBackground";
import {AppHeaderMock} from "../components/AppHeaderMock";
import {TabBarMock} from "../components/TabBarMock";
import {GovernancePanelMock} from "../components/GovernancePanelMock";
import {ProductFrame} from "../components/ProductFrame";
import {AnimatedCursor} from "../components/AnimatedCursor";
import {Caption} from "./Caption";

const WS = SCRIPT.workspace;
const FRAME_W = 1320;
const FRAME_H = 760;

// Scene 7 (49-60s): the cursor clicks the "Governance" tab. The Promotion
// Readiness panel reveals its gates. The cursor then clicks the "Generate
// Research Risk Narrative" button (ClickRipple + pressed state), and the
// AI narrative panel slides in beneath.
export const GovernanceScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const frameAppear = spring({frame, fps, config: {damping: 200, mass: 0.8}});

  // Click 1: the Governance tab.
  const tabClick = 24;
  const tabClickProg = interpolate(frame, [tabClick, tabClick + 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const activeTab = frame >= tabClick ? "Governance" : "Evidence";

  // Panel reveal after tab click.
  const panelAppear = interpolate(frame, [tabClick + 8, 80], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Click 2: the Generate button -> narrative reveal.
  const btnClick = 170;
  const btnClickProg = interpolate(frame, [btnClick, btnClick + 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const buttonPressed = frame >= btnClick && frame <= btnClick + 12;
  const narrativeAppear = interpolate(frame, [btnClick + 10, btnClick + 50], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const clicking =
    (frame >= tabClick && frame <= tabClick + 6) ||
    (frame >= btnClick && frame <= btnClick + 6);
  const clickProgress = frame < 100 ? tabClickProg : btnClickProg;

  // Cursor path: tab -> button.
  const cx = interpolate(
    frame,
    [0, tabClick, 120, btnClick],
    [560, 700, 960, 960],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic)}
  );
  const cy = interpolate(
    frame,
    [0, tabClick, 120, btnClick],
    [320, 250, 560, 560],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic)}
  );
  const onButton = frame >= 120 && frame < btnClick + 20;
  const hovering = frame <= tabClick + 4 || onButton;

  return (
    <AbsoluteFill>
      <AmbientBackground />

      <AbsoluteFill style={{alignItems: "center", justifyContent: "center"}}>
        <ProductFrame width={FRAME_W} height={FRAME_H} appear={frameAppear} glow={COLORS.blue} titlebarDots>
          <div style={{display: "flex", flexDirection: "column", height: "100%"}}>
            <AppHeaderMock area="Strategy Workspace" />
            <div
              style={{
                flex: 1,
                minHeight: 0,
                padding: "20px 30px 24px",
                fontFamily: FONT_STACK,
                display: "flex",
                flexDirection: "column",
                gap: 16,
              }}
            >
              <div style={{fontSize: 18, fontWeight: 800, color: COLORS.textPrimary}}>
                {WS.strategyName}
              </div>
              <TabBarMock tabs={[...WS.tabs]} active={activeTab} />
              <div
                style={{
                  flex: 1,
                  minHeight: 0,
                  display: "flex",
                  alignItems: "flex-start",
                  justifyContent: "center",
                  overflow: "hidden",
                  paddingTop: 4,
                }}
              >
                <GovernancePanelMock
                  appear={panelAppear}
                  buttonPressed={buttonPressed}
                  narrativeAppear={narrativeAppear}
                />
              </div>
            </div>
          </div>
        </ProductFrame>
      </AbsoluteFill>

      <Caption
        text={SCRIPT.governance.caption}
        sub={SCRIPT.governance.sub}
        kicker="Promotion Readiness"
        inAt={40}
        position="top"
      />

      <AnimatedCursor
        x={cx}
        y={cy}
        hovering={hovering}
        clicking={clicking}
        clickProgress={clickProgress}
        ringColor={COLORS.blue}
        label={onButton ? "Generate narrative" : undefined}
      />
    </AbsoluteFill>
  );
};
