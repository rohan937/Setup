import React from "react";
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";
import {COLORS, FONT_STACK, MetricTone, SCRIPT} from "../timing";
import {AmbientBackground} from "../components/AmbientBackground";
import {AppHeaderMock} from "../components/AppHeaderMock";
import {ScoreCardMock} from "../components/ScoreCardMock";
import {LifecycleMock} from "../components/LifecycleMock";
import {TabBarMock} from "../components/TabBarMock";
import {ProductFrame} from "../components/ProductFrame";
import {AnimatedCursor} from "../components/AnimatedCursor";
import {Caption} from "./Caption";

const WS = SCRIPT.workspace;
const FRAME_W = 1320;
const FRAME_H = 760;

// Scene 4 (18-28s): the Strategy Workspace for the opened strategy. A header,
// a row of score cards that glow as the cursor sweeps across them, a lifecycle
// pipeline (current Backtest Review, blocked Paper Candidate), and the tab bar.
// The cursor finishes by clicking the "Reality" tab.
export const WorkspaceScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const appear = spring({frame, fps, config: {damping: 200, mass: 0.8}});

  const cardsAppear = interpolate(frame, [14, 40], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const pipeProgress = interpolate(frame, [40, 90], [0, 0.45], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Cursor sweeps across the 4 score cards, then drops to the "Reality" tab.
  // Score-card row x positions (approx within the 1920 frame).
  const cardXs = [560, 800, 1040, 1280];
  const sweepStart = 40;
  const sweepEnd = 150;
  const cx = interpolate(
    frame,
    [sweepStart, 70, 100, 130, sweepEnd, sweepEnd + 40],
    [cardXs[0], cardXs[1], cardXs[2], cardXs[3], cardXs[3], 760],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic)}
  );
  const cy = interpolate(
    frame,
    [sweepStart, sweepEnd, sweepEnd + 40],
    [300, 300, 470],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic)}
  );

  // Which card is "focused" by the passing cursor.
  const focusedIndex = (() => {
    if (frame < sweepStart || frame > sweepEnd) return -1;
    if (frame < 70) return 0;
    if (frame < 100) return 1;
    if (frame < 130) return 2;
    return 3;
  })();

  // Click the Reality tab near the end.
  const clickFrame = 210;
  const clickProgress = interpolate(frame, [clickFrame, clickFrame + 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const clicking = frame >= clickFrame && frame <= clickFrame + 6;
  const cursorOnTab = frame >= sweepEnd + 30;
  const activeTab = frame >= clickFrame ? "Reality" : "Overview";

  return (
    <AbsoluteFill>
      <AmbientBackground />

      <AbsoluteFill style={{alignItems: "center", justifyContent: "center"}}>
        <ProductFrame width={FRAME_W} height={FRAME_H} appear={appear} glow={COLORS.purple} titlebarDots>
          <div style={{display: "flex", flexDirection: "column", height: "100%"}}>
            <AppHeaderMock area="Strategy Workspace" />
            <div
              style={{
                flex: 1,
                minHeight: 0,
                padding: "24px 30px",
                fontFamily: FONT_STACK,
                display: "flex",
                flexDirection: "column",
                gap: 20,
              }}
            >
              {/* Strategy header. */}
              <div style={{display: "flex", alignItems: "center", justifyContent: "space-between"}}>
                <div>
                  <div style={{fontSize: 22, fontWeight: 800, color: COLORS.textPrimary, letterSpacing: "-0.02em"}}>
                    {WS.strategyName}
                  </div>
                  <div style={{marginTop: 5, fontSize: 13, color: COLORS.textMuted, fontWeight: 600}}>
                    US Equities · Backtest Review stage
                  </div>
                </div>
                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 700,
                    color: COLORS.warning,
                    background: "rgba(255,181,71,0.12)",
                    border: `1px solid rgba(255,181,71,0.3)`,
                    borderRadius: 999,
                    padding: "6px 13px",
                  }}
                >
                  Readiness: Review
                </span>
              </div>

              {/* Score cards row. */}
              <div style={{display: "flex", gap: 14}}>
                {WS.scoreCards.map((c, i) => (
                  <ScoreCardMock
                    key={c.label}
                    label={c.label}
                    value={c.value}
                    verdict={c.verdict}
                    tone={c.tone as MetricTone}
                    appear={cardsAppear}
                    focused={focusedIndex === i}
                  />
                ))}
              </div>

              {/* Lifecycle. */}
              <div
                style={{
                  padding: "18px 24px",
                  borderRadius: 14,
                  background: "rgba(255,255,255,0.02)",
                  border: `1px solid ${COLORS.border}`,
                }}
              >
                <LifecycleMock
                  currentKey={WS.currentStageKey}
                  blockedKey="paperCandidate"
                  progress={pipeProgress}
                />
                <div
                  style={{
                    marginTop: 14,
                    fontSize: 12.5,
                    color: COLORS.warning,
                    fontWeight: 600,
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  <span>⚠</span> Paper Candidate blocked — missing paper / shadow validation
                </div>
              </div>

              {/* Tab bar. */}
              <div style={{marginTop: "auto"}}>
                <TabBarMock tabs={[...WS.tabs]} active={activeTab} />
              </div>
            </div>
          </div>
        </ProductFrame>
      </AbsoluteFill>

      <Caption
        text={SCRIPT.workspace.caption}
        sub={SCRIPT.workspace.sub}
        kicker="Strategy Workspace"
        inAt={16}
        position="bottom"
      />

      <AnimatedCursor
        x={cx}
        y={cy}
        hovering={focusedIndex >= 0 || cursorOnTab}
        clicking={clicking}
        clickProgress={clickProgress}
        ringColor={COLORS.purple}
        label={cursorOnTab ? "Reality" : undefined}
      />
    </AbsoluteFill>
  );
};
