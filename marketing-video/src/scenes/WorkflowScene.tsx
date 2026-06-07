import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {AmbientBackground} from "../components/AmbientBackground";
import {WorkflowPipeline} from "../components/WorkflowPipeline";
import {COLORS, FONT_STACK, SCRIPT} from "../timing";

export const WorkflowScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();

  const headerAppear = interpolate(frame, [0, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Connector sweep across the pipeline.
  const progress = interpolate(frame, [14, durationInFrames - 24], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });

  const exit = interpolate(
    frame,
    [durationInFrames - 12, durationInFrames],
    [1, 0],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"}
  );

  return (
    <AbsoluteFill style={{opacity: exit}}>
      <AmbientBackground />
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          fontFamily: FONT_STACK,
        }}
      >
        <div
          style={{
            fontSize: 48,
            fontWeight: 700,
            color: COLORS.textPrimary,
            letterSpacing: "-0.02em",
            marginBottom: 70,
            opacity: headerAppear,
            transform: `translateY(${(1 - headerAppear) * 14}px)`,
            textAlign: "center",
          }}
        >
          One governed lifecycle.
        </div>
        <WorkflowPipeline progress={progress} steps={SCRIPT.workflow.steps} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
