import React from "react";
import {AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig} from "remotion";
import {AmbientBackground} from "../components/AmbientBackground";
import {BracketText} from "../components/BracketText";
import {SCRIPT} from "../timing";

export const HookScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();

  const enter = interpolate(frame, [0, 22], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const exit = interpolate(
    frame,
    [durationInFrames - 14, durationInFrames],
    [0, 1],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"}
  );

  return (
    <AbsoluteFill>
      <AmbientBackground />
      <BracketText text={SCRIPT.hook.text} enter={enter} exit={exit} />
    </AbsoluteFill>
  );
};
