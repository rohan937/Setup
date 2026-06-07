import React from "react";
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";
import {COLORS, FONT_STACK, SCRIPT} from "../timing";
import {AmbientBackground} from "../components/AmbientBackground";
import {AppHeaderMock} from "../components/AppHeaderMock";
import {TabBarMock} from "../components/TabBarMock";
import {EvidenceVerificationPanelMock} from "../components/EvidenceVerificationPanelMock";
import {ProductFrame} from "../components/ProductFrame";
import {AnimatedCursor} from "../components/AnimatedCursor";
import {Caption} from "./Caption";

const WS = SCRIPT.workspace;
const FRAME_W = 1320;
const FRAME_H = 760;

// Scene 6 (39-49s): the cursor clicks the "Evidence" tab (ClickRipple), the
// Evidence Verification panel reveals with chain nodes lighting sequentially,
// and the cursor finishes hovering the glowing root-hash.
export const EvidenceScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const frameAppear = spring({frame, fps, config: {damping: 200, mass: 0.8}});

  // Cursor begins over the tab bar, clicks "Evidence", then drops to root hash.
  const clickFrame = 26;
  const clickProgress = interpolate(frame, [clickFrame, clickFrame + 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const clicking = frame >= clickFrame && frame <= clickFrame + 6;

  // Panel appears after the click; rows light up across `appear`.
  const panelAppear = interpolate(frame, [clickFrame + 8, 110], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const activeTab = frame >= clickFrame ? "Evidence" : "Reality";

  // Cursor path: tab (≈ x 620,y 250) -> root hash row (≈ x 980, y 600).
  const cx = interpolate(frame, [0, clickFrame, 150, 200], [560, 620, 620, 980], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const cy = interpolate(frame, [0, clickFrame, 150, 200], [300, 250, 250, 620], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const onRootHash = frame >= 196;
  const hovering = frame <= clickFrame + 4 || onRootHash;

  return (
    <AbsoluteFill>
      <AmbientBackground />

      <AbsoluteFill style={{alignItems: "center", justifyContent: "center"}}>
        <ProductFrame width={FRAME_W} height={FRAME_H} appear={frameAppear} glow={COLORS.success} titlebarDots>
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
              <TabBarMock tabs={[...WS.tabs]} active={activeTab} />
              <div style={{flex: 1, display: "flex", alignItems: "center", justifyContent: "center"}}>
                <EvidenceVerificationPanelMock appear={panelAppear} rootHashGlow={onRootHash} />
              </div>
            </div>
          </div>
        </ProductFrame>
      </AbsoluteFill>

      <Caption
        text={SCRIPT.evidence.caption}
        sub={SCRIPT.evidence.sub}
        kicker="Evidence Verification"
        inAt={40}
        position="bottom"
      />

      <AnimatedCursor
        x={cx}
        y={cy}
        hovering={hovering}
        clicking={clicking}
        clickProgress={clickProgress}
        ringColor={COLORS.success}
        label={onRootHash ? "Root hash" : undefined}
      />
    </AbsoluteFill>
  );
};
